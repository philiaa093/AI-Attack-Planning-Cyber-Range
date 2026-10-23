"""Fixed authenticated lab actions. No scanner or planner supplies POST fields."""
import re
import urllib.parse

AUTH_ACTION = "ACTION-AUTH-001"
FLOW_ACTION = "ACTION-FLOW-001"
CHECK_ACTION = "ACTION-FLOW-002"
WORKFLOW_ACTIONS = {AUTH_ACTION, FLOW_ACTION, CHECK_ACTION}
POST_FIELDS = {
    "/register": {"username", "email", "password", "csrf_token"},
    "/login": {"username", "password", "csrf_token"},
    "/logout": {"csrf_token"},
    "/cart/add": {"product_id", "quantity", "csrf_token"},
    "/cart/update": {"cart_id", "quantity", "csrf_token"},
    "/checkout": {"full_name", "address", "email", "idempotency_key", "csrf_token"},
    "/admin/orders/status": {"order_id", "status", "csrf_token"},
}


class WorkflowPolicy:
    def __init__(self, run_id, isolated):
        self.run_id, self.isolated = run_id, isolated
        self.forms = set()
        self.order_paths = set()

    def permits(self, req):
        if not self.isolated() or req.run_id != self.run_id or req.target_id != "lab-ecommerce":
            return False
        parsed = urllib.parse.urlsplit(req.url)
        path = parsed.path
        if parsed.query or parsed.fragment or req.action_id not in WORKFLOW_ACTIONS:
            return False
        if type(req.headers) is not dict or set(req.headers) - {"Cookie"}:
            return False
        if req.headers and not re.fullmatch(r"session=[a-f0-9]{64}", req.headers.get("Cookie", "")):
            return False
        if req.method == "GET":
            return not req.form and (path in {"/", "/products", "/cart", "/register", "/login", "/orders", "/admin"}
                                     or path in self.order_paths)
        if req.method != "POST" or path not in self.forms or path not in POST_FIELDS:
            return False
        expected_action = AUTH_ACTION if path in {"/register", "/login", "/logout"} else (
            CHECK_ACTION if path == "/admin/orders/status" else FLOW_ACTION)
        if req.action_id != expected_action or type(req.form) is not dict or set(req.form) - POST_FIELDS[path]:
            return False
        if any(type(v) is not str or len(v) > 4096 for v in req.form.values()):
            return False
        if len(urllib.parse.urlencode(req.form).encode()) > 16384:
            return False
        if "quantity" in req.form and req.form["quantity"] not in {"1", "2"}:
            return False
        if "username" in req.form and not re.fullmatch(r"rt_[a-f0-9]{12}_[abc]", req.form["username"]):
            return False
        if "order_id" in req.form and "/orders/" + req.form["order_id"] not in self.order_paths:
            return False
        return True
