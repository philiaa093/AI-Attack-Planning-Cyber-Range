"""Role/auth/negative matrix on an isolated in-process ShopLab fixture."""
import unittest

from test_ecommerce_admin import ShopLabAdminTests


class WorkflowCoverageMatrixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ShopLabAdminTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_role_auth_and_ownership_matrix(self):
        f = self.fixture
        _, owner_token, owner = f.account()
        _, peer_token, peer = f.account()
        _, admin_token, _ = f.admin_account()
        order = f.create_order(owner_token, owner)
        order_path = "/orders/" + str(order["id"])
        cases = [
            ("/admin", "GUEST", "ANONYMOUS", "ADMIN_ACCESS", "", {403}),
            ("/admin", "USER", "AUTHENTICATED", "ADMIN_ACCESS", peer_token, {403}),
            ("/admin", "ADMIN", "AUTHENTICATED", "ADMIN_ACCESS", admin_token, {200}),
            (order_path, "OWNER", "AUTHENTICATED", "OWN_ORDER", owner_token, {200}),
            (order_path, "OTHER_USER", "AUTHENTICATED", "OTHER_USERS_ORDER", peer_token, {403, 404}),
            (order_path, "GUEST", "ANONYMOUS", "OTHER_USERS_ORDER", "", {403, 404}),
        ]
        for route, role, auth_state, case, token, expected in cases:
            with self.subTest(route=route, role=role, auth_state=auth_state, case=case):
                self.assertIn(f.request(route, token=token).responses[0], expected)

        with f.app.storage_transaction() as db:
            before = tuple(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                           for name in ("cart", "orders", "products"))
        mutations = [
            ("/cart/add", {"product_id": 1, "quantity": 1}, None, "MISSING_CSRF"),
            ("/checkout", {"full_name": "Fixture", "address": "Fixture", "email": "fixture@lab.invalid"}, None, "MISSING_CSRF"),
            ("/admin/products/add", {"name": "fixture", "category_id": 1, "price": "1.00", "stock": 1},
             peer["csrf_secret"], "ADMIN_MUTATION"),
        ]
        for route, fields, csrf, case in mutations:
            with self.subTest(route=route, role="USER", auth_state="AUTHENTICATED", case=case):
                self.assertEqual(f.request(route, "POST", fields, peer_token, csrf).responses, [403])
        with f.app.storage_transaction() as db:
            after = tuple(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                          for name in ("cart", "orders", "products"))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
