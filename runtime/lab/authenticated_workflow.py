"""Deterministic lab workflow checks; credentials and response bodies stay in memory."""
from html.parser import HTMLParser
from http.cookies import SimpleCookie
import re
import secrets
import time
import urllib.parse

from runtime.safety.discovery_gate import DiscoveryRequest
from runtime.lab.workflow_policy import AUTH_ACTION, FLOW_ACTION, CHECK_ACTION, POST_FIELDS, WorkflowPolicy


# Metadata describes the fixed check, not a claim about any other route or run.
# Values are fixed labels: never persist account names, session IDs or tokens.
WORKFLOW_CHECK_CONTEXT = {
    "login_a": ("/login", "POST", "USER_A", "ANONYMOUS", "VALID_LOGIN", False, "Login succeeds"),
    "login_b": ("/login", "POST", "USER_B", "ANONYMOUS", "VALID_LOGIN", False, "Login succeeds"),
    "login_c": ("/login", "POST", "ADMIN", "ANONYMOUS", "VALID_LOGIN", False, "Admin login succeeds"),
    "csrf_rejected": ("/cart/add", "POST", "USER_A", "AUTHENTICATED", "INVALID_CSRF", True, "HTTP 403"),
    "csrf_has_no_cart_effect": ("/cart", "GET", "USER_A", "AUTHENTICATED", "INVALID_CSRF_NO_EFFECT", True, "Cart remains unchanged"),
    "checkout_created_order": ("/checkout", "POST", "USER_A", "AUTHENTICATED", "VALID_CHECKOUT", False, "One order created"),
    "checkout_missing_csrf_denied": ("/checkout", "POST", "USER_A", "AUTHENTICATED", "MISSING_CSRF", True, "HTTP 403 and no order or cart change"),
    "checkout_idempotent": ("/checkout", "POST", "USER_A", "AUTHENTICATED", "DUPLICATE_CHECKOUT", True, "No duplicate order"),
    "owner_can_read_order": ("/orders/{id}", "GET", "OWNER", "AUTHENTICATED", "OWN_ORDER", False, "HTTP 200"),
    "peer_cannot_read_order": ("/orders/{id}", "GET", "OTHER_USER", "AUTHENTICATED", "OTHER_USERS_ORDER", True, "HTTP 403 or 404"),
    "guest_order_denied": ("/orders/{id}", "GET", "GUEST", "ANONYMOUS", "OTHER_USERS_ORDER", True, "HTTP 403 or 404"),
    "user_cannot_read_admin": ("/admin", "GET", "USER_B", "AUTHENTICATED", "ADMIN_ACCESS", True, "HTTP 403"),
    "guest_admin_denied": ("/admin", "GET", "GUEST", "ANONYMOUS", "ADMIN_ACCESS", True, "HTTP 403"),
    "peer_csrf_control": ("/cart/add", "POST", "USER_B", "AUTHENTICATED", "VALID_CSRF_CONTROL", False, "HTTP 302 or 303"),
    "user_admin_order_change_denied": ("/admin/orders/status", "POST", "USER_B", "AUTHENTICATED", "ADMIN_ORDER_MUTATION", True, "HTTP 403 and order status unchanged"),
    "backward_order_transition_rejected": ("/admin/orders/status", "POST", "ADMIN", "AUTHENTICATED", "BACKWARD_TRANSITION", True, "HTTP 400 or 409"),
    "admin_can_ship_order": ("/admin/orders/status", "POST", "ADMIN", "AUTHENTICATED", "SHIP_ORDER", False, "Order becomes shipped"),
}


def _order_badge(body: str) -> str | None:
    match = re.search(r"class=['\"]badge badge-([a-z-]+)['\"]", body)
    return match.group(1) if match else None


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
        self.cookies = {role: "" for role in ("a", "b", "c", "guest")}
        self.observed = {role: {} for role in ("a", "b", "c", "guest")}
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
        context = WORKFLOW_CHECK_CONTEXT.get(name)
        if context is None:
            raise RuntimeError("WORKFLOW_CHECK_CONTEXT_UNKNOWN")
        route, method, role, auth_state, case, negative, expected = context
        result = {"check": name, "status": "PASS" if passed else "FAIL",
                  "route": route, "method": method, "role": role, "auth_state": auth_state,
                  "case": case, "negative": negative, "expected": expected, **details}
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
                home = self.page(role, "/")
                if logged_in.status_code not in (302, 303) or "/logout" not in self.observed[role]:
                    raise RuntimeError("WORKFLOW_LOGIN_FAILED")
                if role == "c" and "/admin" not in home.links:
                    raise RuntimeError("WORKFLOW_ADMIN_PROMOTION_FAILED")
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
            cart_before = self.form("a", "/cart/update")
            without_csrf = dict(checkout)
            without_csrf.pop("csrf_token", None)
            denied_checkout = self.request("a", "/checkout", FLOW_ACTION, without_csrf)
            before_orders = self.page("a", "/orders", FLOW_ACTION)
            no_order = not any(re.fullmatch(r"/orders/[1-9][0-9]*", path) for path in before_orders.links)
            self.page("a", "/cart", FLOW_ACTION)
            cart_unchanged = self.form("a", "/cart/update") == cart_before
            self.check("checkout_missing_csrf_denied", denied_checkout.status_code == 403 and no_order and cart_unchanged,
                       http_status=denied_checkout.status_code)
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
            guest_order = self.request("guest", order_path, CHECK_ACTION)
            self.check("guest_order_denied", guest_order.status_code in (403, 404), http_status=guest_order.status_code)
            denied_admin = self.request("b", "/admin", CHECK_ACTION)
            self.check("user_cannot_read_admin", denied_admin.status_code == 403, http_status=denied_admin.status_code)
            guest_admin = self.request("guest", "/admin", CHECK_ACTION)
            self.check("guest_admin_denied", guest_admin.status_code == 403, http_status=guest_admin.status_code)
            admin_page = self.request("c", "/admin" + order_path, CHECK_ACTION)
            if admin_page.status_code != 200:
                raise RuntimeError("WORKFLOW_ADMIN_PAGE_UNAVAILABLE")
            parsed_admin = Forms(admin_page.body)
            self.observed["c"] = {}
            for form in parsed_admin.forms:
                canonical = self.gate.canonicalizer.canonicalize(form["action"] or "/admin" + order_path,
                                                                current_url=self.gate.base_origin + "/admin" + order_path)
                if canonical.is_valid and not canonical.redacted:
                    target = urllib.parse.urlsplit(canonical.canonical_url)
                    if form["method"] == "POST" and target.path in POST_FIELDS and not target.query:
                        if set(form["fields"]) <= POST_FIELDS[target.path]:
                            self.observed["c"].setdefault(target.path, form["fields"])
                            self.policy.forms.add(target.path)
            self.page("b", "/products", FLOW_ACTION)
            peer_cart = self.form("b", "/cart/add", quantity="1")
            peer_control = self.request("b", "/cart/add", FLOW_ACTION, peer_cart)
            self.check("peer_csrf_control", peer_control.status_code in (302, 303), http_status=peer_control.status_code)
            if peer_control.status_code not in (302, 303):
                raise RuntimeError("WORKFLOW_PEER_CSRF_CONTROL_FAILED")
            self.page("b", "/", CHECK_ACTION)
            peer_csrf = self.form("b", "/logout").get("csrf_token", "")
            if not re.fullmatch(r"[a-f0-9]{64}", peer_csrf) or peer_csrf != peer_cart.get("csrf_token"):
                raise RuntimeError("WORKFLOW_PEER_CSRF_CONTROL_CHANGED")
            peer_change = self.form("c", "/admin/orders/status", status="shipped")
            peer_change["csrf_token"] = peer_csrf
            denied_change = self.request("b", "/admin/orders/status", CHECK_ACTION, peer_change)
            after_denied = self.request("c", "/admin" + order_path, CHECK_ACTION)
            before_badge = _order_badge(admin_page.body)
            after_badge = _order_badge(after_denied.body)
            self.check("user_admin_order_change_denied", denied_change.status_code == 403 and
                       after_denied.status_code == 200 and before_badge is not None and after_badge is not None and
                       before_badge == after_badge, http_status=denied_change.status_code)
            invalid = self.request("c", "/admin/orders/status", CHECK_ACTION,
                                   self.form("c", "/admin/orders/status", status="pending"))
            self.check("backward_order_transition_rejected", invalid.status_code in (400, 409), http_status=invalid.status_code)
            self.page("c", "/admin" + order_path, CHECK_ACTION)
            shipped = self.request("c", "/admin/orders/status", CHECK_ACTION,
                                   self.form("c", "/admin/orders/status", status="shipped"))
            state = self.request("c", "/admin" + order_path, CHECK_ACTION)
            self.check("admin_can_ship_order", shipped.status_code in (302, 303) and
                       state.status_code == 200 and _order_badge(state.body) == "shipped")
            return {"status": "COMPLETED", "executor": "FIXED_WORKFLOW_NOT_LLM", "checks": self.checks,
                    "failed_checks": sum(c["status"] == "FAIL" for c in self.checks),
                    "network_dispatches": self.gate.network_dispatch_count - before}
        finally:
            self.cookies.clear()
            self.observed.clear()
            self.gate.workflow_policy = None
