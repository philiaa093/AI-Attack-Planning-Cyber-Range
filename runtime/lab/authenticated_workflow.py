"""Deterministic lab workflow checks; credentials and response bodies stay in memory."""
from html.parser import HTMLParser
from http.cookies import SimpleCookie
import re
import secrets
import time
import urllib.parse

from runtime.safety.discovery_gate import DiscoveryRequest
from runtime.lab.workflow_policy import AUTH_ACTION, FLOW_ACTION, CHECK_ACTION, POST_FIELDS, WorkflowPolicy


class Forms(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.forms, self.links = [], []
        self.current = None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "method": attrs.get("method", "GET").upper(), "fields": {}}
        if tag in ("input", "select", "textarea") and self.current is not None and attrs.get("name"):
            self.current["fields"][attrs["name"]] = attrs.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


class AuthenticatedWorkflow:
    def __init__(self, gate, recorder, approval, lab):
        self.gate, self.recorder, self.approval, self.lab = gate, recorder, approval, lab
        self.policy = WorkflowPolicy(lab.run_id, lambda: lab.active)
        self.cookies = {role: "" for role in "abc"}
        self.observed = {role: {} for role in "abc"}
        self.checks = []

    def request(self, role, path, action=AUTH_ACTION, fields=None):
        headers = {"Cookie": self.cookies[role]} if self.cookies[role] else {}
        response = self.gate.dispatch(DiscoveryRequest(run_id=self.lab.run_id, target_id="lab-ecommerce",
            action_id=action, url=self.gate.base_origin + path, method="POST" if fields is not None else "GET",
            headers=headers, form=fields or {}, approval=self.approval))
        if not response.durable_confirmed or not response.status_code or response.truncated:
            raise RuntimeError("WORKFLOW_REQUEST_INCOMPLETE")
        cookie_header = response.headers.get("Set-Cookie", "")
        if cookie_header:
            jar = SimpleCookie()
            jar.load(cookie_header)
            if "session" in jar:
                value = jar["session"].value
                if value and not re.fullmatch(r"[a-f0-9]{64}", value):
                    raise RuntimeError("WORKFLOW_SESSION_INVALID")
                self.cookies[role] = "session=" + value if value else ""
        return response

    def page(self, role, path, action=AUTH_ACTION):
        response = self.request(role, path, action)
        if response.status_code != 200:
            raise RuntimeError("WORKFLOW_PAGE_UNAVAILABLE")
        parsed = Forms(response.body)
        self.observed[role] = {}
        for form in parsed.forms:
            canonical = self.gate.canonicalizer.canonicalize(form["action"] or path,
                                                            current_url=self.gate.base_origin + path)
            if not canonical.is_valid or canonical.redacted:
                continue
            target = urllib.parse.urlsplit(canonical.canonical_url)
            if form["method"] == "POST" and target.path in POST_FIELDS and not target.query:
                if set(form["fields"]) <= POST_FIELDS[target.path]:
                    self.observed[role].setdefault(target.path, form["fields"])
                    self.policy.forms.add(target.path)
        return parsed

    def form(self, role, path, **values):
        if path not in self.observed[role]:
            raise RuntimeError("WORKFLOW_FORM_NOT_OBSERVED")
        result = dict(self.observed[role][path])
        if not set(values) <= result.keys():
            raise RuntimeError("WORKFLOW_FIELD_NOT_OBSERVED")
        result.update(values)
        return result

    def check(self, name, passed, **details):
        result = {"check": name, "status": "PASS" if passed else "FAIL", **details}
        artifact = self.recorder.persist_phase_artifact("workflow_check", {
            "run_id": self.lab.run_id, "source": "FIXED_AUTHENTICATED_WORKFLOW", **result})
        result["evidence_id"] = artifact["evidence_id"]
        self.checks.append(result)

    def execute(self):
        self.gate.workflow_policy = self.policy
        before = self.gate.network_dispatch_count
        try:
            # Service startup is checked through the same gate and request budget.
            for attempt in range(10):
                response = self.gate.dispatch(DiscoveryRequest(run_id=self.lab.run_id, target_id="lab-ecommerce",
                    action_id=AUTH_ACTION, url=self.gate.base_origin + "/", approval=self.approval))
                if response.status_code == 200 and response.durable_confirmed:
                    break
                if self.gate.kill_switch.is_active() or self.gate.halted_due_to_evidence:
                    raise RuntimeError("WORKFLOW_START_CANCELLED")
                time.sleep(0.3)
            else:
                raise RuntimeError("WORKFLOW_START_TIMEOUT")
            landing = Forms(response.body)
            if not {"/register", "/login", "/products"} <= set(landing.links):
                raise RuntimeError("WORKFLOW_ENTRY_LINKS_NOT_OBSERVED")
            for role in "abc":
                username = "rt_" + self.lab.key + "_" + role
                password = secrets.token_urlsafe(24)
                self.page(role, "/register")
                fields = self.form(role, "/register", username=username, password=password, email=username + "@lab.invalid")
                created = self.request(role, "/register", fields=fields)
                if created.status_code not in (302, 303) or not self.cookies[role]:
                    raise RuntimeError("WORKFLOW_REGISTRATION_FAILED")
                self.page(role, "/")
                logged_out = self.request(role, "/logout", fields=self.form(role, "/logout"))
                if logged_out.status_code not in (302, 303):
                    raise RuntimeError("WORKFLOW_LOGOUT_FAILED")
                if role == "c":
                    self.lab.promote(username)
                self.page(role, "/login")
                logged_in = self.request(role, "/login", fields=self.form(role, "/login", username=username, password=password))
                self.page(role, "/")
                if logged_in.status_code not in (302, 303) or "/logout" not in self.observed[role]:
                    raise RuntimeError("WORKFLOW_LOGIN_FAILED")
                self.check("login_" + role, True)
            self.page("a", "/products", FLOW_ACTION)
            add = self.form("a", "/cart/add", quantity="1")
            invalid_csrf = self.request("a", "/cart/add", FLOW_ACTION, {**add, "csrf_token": "0" * 64})
            self.check("csrf_rejected", invalid_csrf.status_code == 403, http_status=invalid_csrf.status_code)
            self.page("a", "/cart", FLOW_ACTION)
            self.check("csrf_has_no_cart_effect", "/checkout" not in self.observed["a"])
            self.page("a", "/products", FLOW_ACTION)
            added = self.request("a", "/cart/add", FLOW_ACTION, self.form("a", "/cart/add", quantity="1"))
            if added.status_code not in (302, 303):
                raise RuntimeError("WORKFLOW_CART_ADD_FAILED")
            self.page("a", "/cart", FLOW_ACTION)
            updated = self.request("a", "/cart/update", FLOW_ACTION, self.form("a", "/cart/update", quantity="1"))
            if updated.status_code not in (302, 303):
                raise RuntimeError("WORKFLOW_CART_UPDATE_FAILED")
            self.page("a", "/cart", FLOW_ACTION)
            checkout = self.form("a", "/checkout", full_name="Lab Assessment", address="Simulated lab address",
                                 email="assessment@lab.invalid")
            placed = self.request("a", "/checkout", FLOW_ACTION, checkout)
            if placed.status_code != 200:
                raise RuntimeError("WORKFLOW_CHECKOUT_FAILED")
            orders = self.page("a", "/orders", FLOW_ACTION)
            own_orders = {path for path in orders.links if re.fullmatch(r"/orders/[1-9][0-9]*", path)}
            if len(own_orders) != 1:
                raise RuntimeError("WORKFLOW_ORDER_NOT_IDENTIFIED")
            order_path = own_orders.pop()
            self.policy.order_paths.update({order_path, "/admin" + order_path})
            self.check("checkout_created_order", True)
            repeat = self.request("a", "/checkout", FLOW_ACTION, checkout)
            repeated_orders = self.page("a", "/orders", FLOW_ACTION)
            self.check("checkout_idempotent", repeat.status_code == 200 and
                       {p for p in repeated_orders.links if re.fullmatch(r"/orders/[1-9][0-9]*", p)} == {order_path})
            own = self.request("a", order_path, CHECK_ACTION)
            peer = self.request("b", order_path, CHECK_ACTION)
            self.check("owner_can_read_order", own.status_code == 200, http_status=own.status_code)
            self.check("peer_cannot_read_order", peer.status_code in (403, 404), http_status=peer.status_code)
            denied_admin = self.request("b", "/admin", CHECK_ACTION)
            self.check("user_cannot_read_admin", denied_admin.status_code == 403, http_status=denied_admin.status_code)
            self.page("c", "/admin" + order_path, CHECK_ACTION)
            invalid = self.request("c", "/admin/orders/status", CHECK_ACTION,
                                   self.form("c", "/admin/orders/status", status="pending"))
            self.check("backward_order_transition_rejected", invalid.status_code in (400, 409), http_status=invalid.status_code)
            self.page("c", "/admin" + order_path, CHECK_ACTION)
            shipped = self.request("c", "/admin/orders/status", CHECK_ACTION,
                                   self.form("c", "/admin/orders/status", status="shipped"))
            state = self.request("c", "/admin" + order_path, CHECK_ACTION)
            self.check("admin_can_ship_order", shipped.status_code in (302, 303) and
                       state.status_code == 200 and "badge-shipped" in state.body)
            return {"status": "COMPLETED", "executor": "FIXED_WORKFLOW_NOT_LLM", "checks": self.checks,
                    "failed_checks": sum(c["status"] == "FAIL" for c in self.checks),
                    "network_dispatches": self.gate.network_dispatch_count - before}
        finally:
            self.cookies.clear()
            self.observed.clear()
            self.gate.workflow_policy = None
