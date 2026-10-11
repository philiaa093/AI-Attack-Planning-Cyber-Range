"""SL-06: Product / Admin / Order Status / UI integration tests (ShopLab).

Kiểm thử quyền admin server-side, bảo vệ CSRF, validation sản phẩm/giá/kho,
product archiving (không xóa lịch sử đơn hàng), concurrency giữa admin stock và checkout,
order status state transition map & audit logging, role promotion/revocation tức thì,
UI lab notice, empty states, và offline assets.
"""
from decimal import Decimal
from email.message import Message
import io
import json
from pathlib import Path
import re
import secrets
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from test_ecommerce_storage import load_app


class ShopLabAdminTests(unittest.TestCase):
    def setUp(self):
        self.app = load_app()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.app.close_storage)
        self.app.initialize_storage(self.temp.name)

    def request(self, path, method='GET', fields=None, token='', csrf=None, raw=None, headers=None):
        body = raw if raw is not None else urlencode(fields or {}).encode()
        h = object.__new__(self.app.Handler)
        h.path = path
        h.headers = Message()
        h.headers['Content-Length'] = str(len(body))
        if token and not any(k.lower() == 'cookie' for k, v in headers or []):
            h.headers['Cookie'] = 'session=' + token
        if csrf is not None and not any(k.lower() == 'x-csrf-token' for k, v in headers or []):
            h.headers['X-CSRF-Token'] = csrf
        for k, v in headers or []:
            h.headers[k] = v
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.responses, h.sent_headers = [], []
        h.send_response = h.responses.append
        h.send_header = lambda k, v: h.sent_headers.append((k, v))
        h.end_headers = lambda: None
        getattr(h, 'do_' + method)()
        return h

    def cookie(self, h):
        for k, v in h.sent_headers:
            if k == 'Set-Cookie' and v.startswith('session='):
                return v.split(';')[0].split('=', 1)[1]
        return ''

    def identity(self, token):
        with self.app.storage_transaction() as db:
            row = self.app.resolve_session(db, token)
            return dict(row) if row is not None else None

    def guest(self):
        h = self.request('/login')
        self.assertEqual(h.responses, [200])
        token = self.cookie(h)
        with self.app.storage_transaction() as db:
            row = dict(self.app.resolve_session(db, token))
        return token, row

    def account(self, username=None):
        token, row = self.guest()
        u = username or ('user_' + secrets.token_hex(4))
        fields = {'username': u, 'password': 'Password123!', 'email': f'{u}@example.invalid'}
        h = self.request('/register', 'POST', fields, token, row['csrf_secret'])
        self.assertEqual(h.responses, [302])
        new_token = self.cookie(h)
        return fields, new_token, self.identity(new_token)

    def admin_account(self, username=None):
        fields, token, sess = self.account(username or ('admin_' + secrets.token_hex(4)))
        uid = sess['user_id']
        self.app.close_storage()
        self.app.set_local_role(self.temp.name, uid, 'admin')
        self.app.initialize_storage(self.temp.name)
        # Login sau khi được promote để nhận session mới có role admin
        gt, gs = self.guest()
        h_login = self.request('/login', 'POST', fields, gt, gs['csrf_secret'])
        self.assertEqual(h_login.responses, [302])
        admin_token = self.cookie(h_login)
        admin_sess = self.identity(admin_token)
        self.assertEqual(admin_sess['role'], 'admin')
        return fields, admin_token, admin_sess

    def create_order(self, token, sess, product_id=1, quantity=1):
        self.request('/cart/add', 'POST', {'product_id': product_id, 'quantity': quantity}, token, sess['csrf_secret'])
        shipping = {'full_name': 'Test Buyer', 'address': '123 Order St', 'email': 'buyer@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, token, sess['csrf_secret'])
        self.assertEqual(h.responses, [200])
        with self.app.storage_transaction() as db:
            order = db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1', (sess['user_id'],)).fetchone()
            return dict(order)

    # ── M01: Admin Authorization & Access Control ─────────────────────────
    def test_M01_admin_authorization_enforced_server_side(self):
        # M01-A: Anonymous GET admin page -> 403
        h_anon = self.request('/admin')
        self.assertEqual(h_anon.responses, [403])
        self.assertIn("Admin access required", h_anon.wfile.getvalue().decode())

        # M01-B: Normal user GET admin page -> 403
        _, u_token, u_sess = self.account('normal_user')
        h_user = self.request('/admin', token=u_token)
        self.assertEqual(h_user.responses, [403])

        # M01-C: Normal user POST mutation -> 403 before DB write
        h_mut = self.request(
            '/admin/products/add', 'POST',
            {'name': 'Hacker Gadget', 'description': 'Exploit', 'category_id': 1, 'price': '9.99', 'stock': 10},
            u_token, u_sess['csrf_secret']
        )
        self.assertEqual(h_mut.responses, [403])
        with self.app.storage_transaction() as db:
            prod = db.execute("SELECT 1 FROM products WHERE name='Hacker Gadget'").fetchone()
            self.assertIsNone(prod)

        # M01-D: Forged role cookie by normal user -> 403
        h_forge = self.request('/admin', token=u_token, headers=[('Cookie', f'session={u_token}; role=admin')])
        self.assertEqual(h_forge.responses, [403])

        # M01-E: Actual admin session -> 200 allowed
        _, a_token, _ = self.admin_account('legit_admin')
        h_admin = self.request('/admin', token=a_token)
        self.assertEqual(h_admin.responses, [200])
        self.assertIn("Admin Dashboard", h_admin.wfile.getvalue().decode())

    # ── M02: CSRF Protection on Admin Mutations ───────────────────────────
    def test_M02_admin_mutations_require_valid_csrf(self):
        _, a_token, a_sess = self.admin_account()
        payload = {'name': 'CSRF Protected Gadget', 'description': 'Secure', 'category_id': 1, 'price': '19.99', 'stock': 5}

        # 1. Missing CSRF -> 403
        h_missing = self.request('/admin/products/add', 'POST', payload, a_token, csrf=None)
        self.assertEqual(h_missing.responses, [403])

        # 2. Invalid CSRF -> 403
        h_invalid = self.request('/admin/products/add', 'POST', payload, a_token, csrf='0'*64)
        self.assertEqual(h_invalid.responses, [403])

        # 3. Forged admin cookie by normal user with valid normal-user CSRF -> 403
        _, u_token, u_sess = self.account()
        h_forged = self.request('/admin/products/add', 'POST', payload, u_token, u_sess['csrf_secret'], headers=[('Cookie', f'session={u_token}; role=admin')])
        self.assertEqual(h_forged.responses, [403])

        # Verify DB unchanged
        with self.app.storage_transaction() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM products WHERE name='CSRF Protected Gadget'").fetchone())

        # 4. Valid CSRF -> 302 / success
        h_valid = self.request('/admin/products/add', 'POST', payload, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_valid.responses, [302])
        with self.app.storage_transaction() as db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM products WHERE name='CSRF Protected Gadget'").fetchone())

    # ── M03: Product Validation (Price, Stock, Category, Bounds) ──────────
    def test_M03_product_creation_and_update_validation(self):
        _, a_token, a_sess = self.admin_account()

        # Valid prices: 0.10, 10.01, 19.99
        for valid_price in ['0.10', '10.01', '19.99']:
            h = self.request(
                '/admin/products/add', 'POST',
                {'name': f'P_{valid_price}', 'description': 'Test', 'category_id': 1, 'price': valid_price, 'stock': 10},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h.responses, [302])
            with self.app.storage_transaction() as db:
                row = db.execute("SELECT price FROM products WHERE name=?", (f'P_{valid_price}',)).fetchone()
                self.assertEqual(row['price'], float(valid_price))

        # Invalid prices: negative, non-numeric, excess precision, oversized
        for bad_price in ['-5', '-0.01', '0', '0.00', 'NaN', 'Infinity', '19.999', '100000000000', 'not_money']:
            h = self.request(
                '/admin/products/add', 'POST',
                {'name': f'Bad_{bad_price}', 'description': 'Test', 'category_id': 1, 'price': bad_price, 'stock': 10},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h.responses, [400])
            with self.app.storage_transaction() as db:
                self.assertIsNone(db.execute("SELECT 1 FROM products WHERE name=?", (f'Bad_{bad_price}',)).fetchone())

        # Invalid stocks: negative, float, non-numeric, oversized
        for bad_stock in ['-1', '1.5', 'abc', '1000000000']:
            h = self.request(
                '/admin/products/add', 'POST',
                {'name': f'BadStock_{bad_stock}', 'description': 'Test', 'category_id': 1, 'price': '10.00', 'stock': bad_stock},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h.responses, [400])

        # Invalid categories: missing, negative, nonexistent ID
        for bad_cat in ['', '-1', '99999', 'abc']:
            h = self.request(
                '/admin/products/add', 'POST',
                {'name': f'BadCat_{bad_cat}', 'description': 'Test', 'category_id': bad_cat, 'price': '10.00', 'stock': 10},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h.responses, [400])

        # Text bounds: empty name, oversized description
        h_empty_name = self.request(
            '/admin/products/add', 'POST',
            {'name': '   ', 'description': 'Test', 'category_id': 1, 'price': '10.00', 'stock': 10},
            a_token, a_sess['csrf_secret']
        )
        self.assertEqual(h_empty_name.responses, [400])

        h_big_desc = self.request(
            '/admin/products/add', 'POST',
            {'name': 'Big Desc', 'description': 'x' * 2001, 'category_id': 1, 'price': '10.00', 'stock': 10},
            a_token, a_sess['csrf_secret']
        )
        self.assertEqual(h_big_desc.responses, [400])

    # ── M04: Product Archive Preserves Historical Orders ──────────────────
    def test_M04_product_archive_preserves_historical_orders_and_blocks_new_purchases(self):
        _, a_token, a_sess = self.admin_account()
        _, u_token, u_sess = self.account('buyer_m04')

        # 1. Admin tạo sản phẩm mới
        self.request(
            '/admin/products/add', 'POST',
            {'name': 'Vintage Watch', 'description': 'Rare mechanical watch', 'category_id': 1, 'price': '199.99', 'stock': 5},
            a_token, a_sess['csrf_secret']
        )
        with self.app.storage_transaction() as db:
            prod = db.execute("SELECT id FROM products WHERE name='Vintage Watch'").fetchone()
            pid = prod['id']

        # 2. Khách hàng đặt mua sản phẩm
        order = self.create_order(u_token, u_sess, product_id=pid, quantity=1)
        self.assertEqual(order['total'], 199.99)

        # 3. Admin archive sản phẩm
        h_arc = self.request('/admin/products/archive', 'POST', {'product_id': pid}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_arc.responses, [302])

        # 4. Khách hàng xem lại đơn hàng cũ -> snapshot nguyên vẹn
        h_order = self.request(f"/orders/{order['id']}", token=u_token)
        self.assertEqual(h_order.responses, [200])
        self.assertIn("Vintage Watch", h_order.wfile.getvalue().decode())
        self.assertIn("$199.99", h_order.wfile.getvalue().decode())

        # 5. Khách hàng tải invoice đơn hàng cũ -> snapshot nguyên vẹn
        h_inv = self.request(f"/download/invoice?file={order['invoice_file']}", token=u_token)
        self.assertEqual(h_inv.responses, [200])
        self.assertIn("Vintage Watch", h_inv.wfile.getvalue().decode())

        # 6. Sản phẩm archived KHÔNG xuất hiện trên danh mục sản phẩm công khai
        h_list = self.request('/products')
        self.assertNotIn("Vintage Watch", h_list.wfile.getvalue().decode())
        h_home = self.request('/')
        self.assertNotIn("Vintage Watch", h_home.wfile.getvalue().decode())

        # 7. Thử thêm sản phẩm archived vào giỏ hàng -> bị từ chối (409)
        h_add = self.request('/cart/add', 'POST', {'product_id': pid, 'quantity': 1}, u_token, u_sess['csrf_secret'])
        self.assertEqual(h_add.responses, [409])

        # 8. Trang chi tiết sản phẩm hiển thị thông báo đã lưu trữ và không có nút Add to Cart
        h_det = self.request(f"/products/{pid}")
        self.assertEqual(h_det.responses, [200])
        html = h_det.wfile.getvalue().decode()
        self.assertIn("This product has been archived", html)
        self.assertNotIn("Add to Cart", html)

    # ── M05: Admin Stock Edit vs Checkout Concurrency ─────────────────────
    def test_M05_admin_stock_edit_vs_checkout_concurrency(self):
        _, a_token, a_sess = self.admin_account()
        _, u_token, u_sess = self.account('concurrency_buyer')

        # Tạo sản phẩm có stock = 1
        self.request(
            '/admin/products/add', 'POST',
            {'name': 'Limited Item', 'description': 'Only 1 left', 'category_id': 1, 'price': '50.00', 'stock': 1},
            a_token, a_sess['csrf_secret']
        )
        with self.app.storage_transaction() as db:
            pid = db.execute("SELECT id FROM products WHERE name='Limited Item'").fetchone()['id']

        # Buyer thêm vào giỏ hàng
        self.request('/cart/add', 'POST', {'product_id': pid, 'quantity': 1}, u_token, u_sess['csrf_secret'])

        # Mô phỏng stale admin stock update: admin đọc stock=1, định sửa thành stock=5 với expected_stock=1
        # Nhưng trước khi admin gửi, buyer checkout thành công làm stock giảm về 0
        shipping = {'full_name': 'Buyer One', 'address': '1 Main St', 'email': 'buyer@example.invalid'}
        h_checkout = self.request('/checkout', 'POST', shipping, u_token, u_sess['csrf_secret'])
        self.assertEqual(h_checkout.responses, [200])

        with self.app.storage_transaction() as db:
            curr_stock = db.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()['stock']
            self.assertEqual(curr_stock, 0)

        # Admin submit stale stock update với expected_stock=1 -> trả về 409 conflict
        h_stale = self.request(
            '/admin/products/stock', 'POST',
            {'product_id': pid, 'stock': 5, 'expected_stock': 1},
            a_token, a_sess['csrf_secret']
        )
        self.assertEqual(h_stale.responses, [409])
        self.assertIn("Stock has changed concurrently", h_stale.wfile.getvalue().decode())

        # Stock trong DB vẫn là 0, không bị overwrite vô tình thành 5
        with self.app.storage_transaction() as db:
            final_stock = db.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()['stock']
            self.assertEqual(final_stock, 0)

    # ── M06: Order Status Transition Map & Audit Logging ──────────────────
    def test_M06_order_status_transitions_and_audit(self):
        _, a_token, a_sess = self.admin_account()
        _, u_token, u_sess = self.account('order_buyer')
        order = self.create_order(u_token, u_sess, product_id=2, quantity=1)
        oid = order['id']
        self.assertEqual(order['status'], 'completed')

        # 1. Valid forward transition: completed -> shipped
        h_ship = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': 'shipped'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_ship.responses, [302])
        with self.app.storage_transaction() as db:
            status = db.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()['status']
            self.assertEqual(status, 'shipped')

        # 2. Repeated same status -> idempotent 302, không duplicate audit
        h_repeat = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': 'shipped'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_repeat.responses, [302])

        # 3. Invalid backward transitions: shipped -> completed, completed -> processing -> 400
        for bad_prev in ['completed', 'processing', 'pending']:
            h_back = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': bad_prev}, a_token, a_sess['csrf_secret'])
            self.assertEqual(h_back.responses, [400])

        # 4. Unknown / arbitrary status -> 400
        for bad_status in ['refunded', 'cancelled', 'foobar', '']:
            h_bad = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': bad_status}, a_token, a_sess['csrf_secret'])
            self.assertEqual(h_bad.responses, [400])

        # Verify invalid transition did not mutate order status
        with self.app.storage_transaction() as db:
            status = db.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()['status']
            self.assertEqual(status, 'shipped')

        # 5. Valid final transition: shipped -> delivered
        h_deliv = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': 'delivered'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_deliv.responses, [302])
        with self.app.storage_transaction() as db:
            status = db.execute("SELECT status FROM orders WHERE id=?", (oid,)).fetchone()['status']
            self.assertEqual(status, 'delivered')

        # 6. Terminal state: delivered không thể transition tiếp sang bất kỳ trạng thái nào
        for term_bad in ['shipped', 'processing', 'completed', 'pending', 'cancelled']:
            h_term = self.request('/admin/orders/status', 'POST', {'order_id': oid, 'status': term_bad}, a_token, a_sess['csrf_secret'])
            self.assertEqual(h_term.responses, [400])

        # 7. Audit log verification: chỉ các bước chuyển trạng thái hợp lệ được ghi lại
        with self.app.storage_transaction() as db:
            logs = db.execute(
                "SELECT * FROM admin_activity_log WHERE target_type='order' AND target_id=? ORDER BY id",
                (oid,)
            ).fetchall()
            self.assertEqual(len(logs), 2)
            self.assertEqual(logs[0]['old_value'], 'completed')
            self.assertEqual(logs[0]['new_value'], 'shipped')
            self.assertEqual(logs[1]['old_value'], 'shipped')
            self.assertEqual(logs[1]['new_value'], 'delivered')

        # 8. Order total và items không bị thay đổi bởi status update
        with self.app.storage_transaction() as db:
            o_after = db.execute("SELECT total FROM orders WHERE id=?", (oid,)).fetchone()
            self.assertEqual(o_after['total'], order['total'])

        # 9. Verify pending -> processing -> shipped flow on a fresh order with initial 'pending'
        with self.app.storage_transaction(write=True) as db:
            cur = db.execute("INSERT INTO orders (user_id, session_id, total, status) VALUES (?,?,?,?)", (u_sess['user_id'], 'sess_p', 15.00, 'pending'))
            p_oid = cur.lastrowid
        h_proc = self.request('/admin/orders/status', 'POST', {'order_id': p_oid, 'status': 'processing'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_proc.responses, [302])
        with self.app.storage_transaction() as db:
            self.assertEqual(db.execute("SELECT status FROM orders WHERE id=?", (p_oid,)).fetchone()['status'], 'processing')
        # Processing cannot go back to pending
        h_proc_back = self.request('/admin/orders/status', 'POST', {'order_id': p_oid, 'status': 'pending'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_proc_back.responses, [400])
        # Processing can go to shipped
        h_proc_ship = self.request('/admin/orders/status', 'POST', {'order_id': p_oid, 'status': 'shipped'}, a_token, a_sess['csrf_secret'])
        self.assertEqual(h_proc_ship.responses, [302])

    # ── M07: Role Promotion & Immediate Revocation Effect ─────────────────
    def test_M07_role_promotion_and_immediate_revocation(self):
        fields, u_token, u_sess = self.account('role_target')
        uid = u_sess['user_id']

        # 1. Unknown identity promotion -> ValueError
        self.app.close_storage()
        with self.assertRaises(ValueError):
            self.app.set_local_role(self.temp.name, 999999, 'admin')
        self.app.initialize_storage(self.temp.name)

        # 2. Promote existing user -> thành công
        self.app.close_storage()
        self.app.set_local_role(self.temp.name, uid, 'admin')
        self.app.initialize_storage(self.temp.name)

        # Login để lấy session admin
        gt, gs = self.guest()
        h_log = self.request('/login', 'POST', fields, gt, gs['csrf_secret'])
        adm_token = self.cookie(h_log)
        self.assertEqual(self.request('/admin', token=adm_token).responses, [200])

        # 3. Revoke admin role server-side
        self.app.close_storage()
        self.app.set_local_role(self.temp.name, uid, 'user')
        self.app.initialize_storage(self.temp.name)

        # 4. Phiên cũ (adm_token) ngay lập tức mất quyền admin trên cả GET và POST
        h_get_after = self.request('/admin', token=adm_token)
        self.assertEqual(h_get_after.responses, [403])

        h_post_after = self.request(
            '/admin/products/add', 'POST',
            {'name': 'After Revoke', 'category_id': 1, 'price': '10.00', 'stock': 5},
            adm_token, u_sess['csrf_secret']
        )
        self.assertEqual(h_post_after.responses, [403])

    # ── M08: UI Navigation, Lab Notice, Offline Assets, Empty States ──────
    def test_M08_ui_elements_and_offline_assets(self):
        _, a_token, _ = self.admin_account()
        _, u_token, _ = self.account()

        # 1. Admin link chỉ hiển thị khi đăng nhập với quyền admin
        h_user_home = self.request('/', token=u_token)
        self.assertNotIn('<a href="/admin">Admin</a>', h_user_home.wfile.getvalue().decode())

        h_admin_home = self.request('/', token=a_token)
        self.assertIn('<a href="/admin">Admin</a>', h_admin_home.wfile.getvalue().decode())

        # 2. Lab Notice hiển thị trên tất cả các trang
        for path in ['/', '/products', '/cart', '/login', '/register', '/admin']:
            h = self.request(path, token=a_token)
            self.assertIn("ShopLab — Cyber Range Lab Environment", h.wfile.getvalue().decode())

        # 3. Offline assets: Không phụ thuộc external CDN
        html_content = h_admin_home.wfile.getvalue().decode()
        for cdn in ['fonts.googleapis.com', 'cdnjs.cloudflare.com', 'bootstrapcdn.com', 'cdn.jsdelivr.net']:
            self.assertNotIn(cdn, html_content)

        # 4. Viewport meta tag present (Mobile structural check)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html_content)

        # 5. Stored XSS prevention trên Product name & description
        h_xss = self.request(
            '/admin/products/add', 'POST',
            {'name': '<script>alert("xss")</script>', 'description': '<img src=x onerror=alert(1)>', 'category_id': 1, 'price': '15.00', 'stock': 10},
            a_token, self.identity(a_token)['csrf_secret']
        )
        self.assertEqual(h_xss.responses, [302])
        h_prod_list = self.request('/products')
        list_html = h_prod_list.wfile.getvalue().decode()
        self.assertNotIn('<script>alert("xss")</script>', list_html)
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', list_html)

    # ── M09: Admin Price Scale & E2E Commercial Arithmetic ────────────────
    def test_M09_admin_price_scale_and_order_flow(self):
        _, a_token, a_sess = self.admin_account()
        _, u_token, u_sess = self.account('scale_buyer')

        # 1. Invalid price inputs are strictly rejected (400)
        for bad_price in ['-5.00', '19.999', '0.00', '0', 'abc', '', '10000000001']:
            h_bad = self.request(
                '/admin/products/add', 'POST',
                {'name': 'Bad Price', 'category_id': 1, 'price': bad_price, 'stock': 10},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h_bad.responses, [400])

        # 2. Canonical test amounts: 0.10, 10.01, 19.99
        test_prices = [('0.10', 0.10), ('10.01', 10.01), ('19.99', 19.99)]
        for price_str, expected_num in test_prices:
            prod_name = f'PScale_{price_str}'
            # Admin creates product
            h_create = self.request(
                '/admin/products/add', 'POST',
                {'name': prod_name, 'description': f'Test {price_str}', 'category_id': 1, 'price': price_str, 'stock': 5},
                a_token, a_sess['csrf_secret']
            )
            self.assertEqual(h_create.responses, [302])

            with self.app.storage_transaction() as db:
                p_row = db.execute("SELECT * FROM products WHERE name=?", (prod_name,)).fetchone()
                self.assertIsNotNone(p_row)
                pid = p_row['id']
                self.assertEqual(p_row['price'], expected_num)

            # Customer views product
            h_view = self.request(f'/products/{pid}', token=u_token)
            self.assertEqual(h_view.responses, [200])
            self.assertIn(f"${expected_num:.2f}", h_view.wfile.getvalue().decode())

            # Customer adds to cart
            h_add = self.request('/cart/add', 'POST', {'product_id': pid, 'quantity': 1}, u_token, u_sess['csrf_secret'])
            self.assertEqual(h_add.responses, [302])

            # Customer views cart
            h_cart = self.request('/cart', token=u_token)
            self.assertEqual(h_cart.responses, [200])
            self.assertIn(f"${expected_num:.2f}", h_cart.wfile.getvalue().decode())

            # Customer checks out
            h_co = self.request(
                '/checkout', 'POST',
                {'shipping_name': 'Scale Tester', 'shipping_address': '123 Lab St', 'shipping_city': 'Cyber City', 'shipping_postal': '12345'},
                u_token, u_sess['csrf_secret']
            )
            self.assertEqual(h_co.responses, [200])

            # Verify order and order_items snapshot in database
            with self.app.storage_transaction() as db:
                order = db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (u_sess['user_id'],)).fetchone()
                self.assertEqual(order['total'], expected_num)
                item = db.execute("SELECT * FROM order_items WHERE order_id=?", (order['id'],)).fetchone()
                self.assertEqual(item['unit_price'], expected_num)
                inv_file = order['invoice_file']

            # Customer views order details
            h_ord = self.request(f"/orders/{order['id']}", token=u_token)
            self.assertEqual(h_ord.responses, [200])
            self.assertIn(f"${expected_num:.2f}", h_ord.wfile.getvalue().decode())

            # Customer downloads simulated invoice
            h_inv = self.request(f"/download/invoice?file={inv_file}", token=u_token)
            self.assertEqual(h_inv.responses, [200])
            self.assertIn(f"${expected_num:.2f}", h_inv.wfile.getvalue().decode())


if __name__ == '__main__':
    unittest.main()
