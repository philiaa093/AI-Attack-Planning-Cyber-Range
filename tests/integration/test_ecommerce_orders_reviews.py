"""SL-05: Orders and Reviews integration tests (ShopLab).

Kiểm thử order history, order detail snapshot, server-side ownership enforcement (IDOR protection),
invoice access & on-demand fallback, product reviews, rating/body validation,
stored XSS HTML escaping, và CSRF protection trong in-process HTTP layer.
"""
from email.message import Message
import io
import json
from pathlib import Path
import re
import secrets
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from test_ecommerce_storage import load_app


class ShopLabOrdersReviewsTests(unittest.TestCase):
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
        if token:
            h.headers['Cookie'] = 'session=' + token
        if csrf is not None:
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

    def scalar(self, sql, params=()):
        with self.app.storage_transaction() as db:
            return db.execute(sql, params).fetchone()[0]

    def create_order_for_user(self, token, user_session, product_id=1, quantity=1):
        """Helper thực hiện luồng checkout đầy đủ cho authenticated user."""
        self.request('/cart/add', 'POST', {'product_id': product_id, 'quantity': quantity}, token, user_session['csrf_secret'])
        shipping = {'full_name': 'Test Buyer', 'address': '123 Order St', 'email': 'buyer@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, token, user_session['csrf_secret'])
        self.assertEqual(h.responses, [200])
        with self.app.storage_transaction() as db:
            order = db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1', (user_session['user_id'],)).fetchone()
            return dict(order)

    # ── O01: User Orders List, Detail & API ────────────────────────────────
    def test_O01_user_orders_list_detail_and_api(self):
        fields, token, sess = self.account()
        # Tạo 2 đơn hàng cho User A
        order1 = self.create_order_for_user(token, sess, product_id=1, quantity=1)
        order2 = self.create_order_for_user(token, sess, product_id=2, quantity=2)

        # 1. Orders list HTML
        h_list = self.request('/orders', token=token)
        self.assertEqual(h_list.responses, [200])
        html = h_list.wfile.getvalue().decode()
        self.assertIn(f"#{order1['id']}", html)
        self.assertIn(f"#{order2['id']}", html)
        self.assertIn(f"${order1['total']:.2f}", html)
        self.assertIn(f"${order2['total']:.2f}", html)
        self.assertIn(f"/orders/{order1['id']}", html)
        self.assertIn(f"/orders/{order2['id']}", html)

        # 2. Order detail HTML
        h_det = self.request(f"/orders/{order1['id']}", token=token)
        self.assertEqual(h_det.responses, [200])
        det_html = h_det.wfile.getvalue().decode()
        self.assertIn(f"Order #{order1['id']}", det_html)
        self.assertIn(f"${order1['total']:.2f}", det_html)
        self.assertIn("Laptop Pro 15", det_html)
        self.assertIn("Download Invoice", det_html)

        # 3. Order API JSON
        h_api = self.request(f"/api/orders/{order1['id']}", token=token)
        self.assertEqual(h_api.responses, [200])
        data = json.loads(h_api.wfile.getvalue().decode())
        self.assertEqual(data['order']['id'], order1['id'])
        self.assertEqual(data['order']['total'], order1['total'])
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['product_id'], 1)
        # Preflight 0.1: Verify order API data minimization
        forbidden_keys = {
            'session_id', 'token_digest', 'cart_key', 'csrf_secret',
            'password', 'password_hash', 'user_id', 'invoice_file'
        }
        for key in forbidden_keys:
            self.assertNotIn(key, data['order'])
        self.assertEqual(set(data['order'].keys()), {'id', 'total', 'currency', 'status', 'created_at'})

    # ── O02: User B & Anonymous Denied (IDOR Protection) ───────────────────
    def test_O02_cross_user_order_access_denied(self):
        _, token_a, sess_a = self.account('user_a')
        _, token_b, sess_b = self.account('user_b')
        order_a = self.create_order_for_user(token_a, sess_a, product_id=1, quantity=1)

        # User B request Order A detail HTML -> 404 (safe enumeration protection)
        h_b = self.request(f"/orders/{order_a['id']}", token=token_b)
        self.assertEqual(h_b.responses, [404])
        self.assertNotIn('Laptop Pro 15', h_b.wfile.getvalue().decode())
        self.assertNotIn(f"${order_a['total']:.2f}", h_b.wfile.getvalue().decode())

        # User B request Order A API -> 404
        h_b_api = self.request(f"/api/orders/{order_a['id']}", token=token_b)
        self.assertEqual(h_b_api.responses, [404])

        # Anonymous request Order A detail HTML -> 404 / 403
        h_anon = self.request(f"/orders/{order_a['id']}")
        self.assertIn(h_anon.responses[0], [403, 404])
        self.assertNotIn('Laptop Pro 15', h_anon.wfile.getvalue().decode())

        # Anonymous request Order A API -> 404
        h_anon_api = self.request(f"/api/orders/{order_a['id']}")
        self.assertEqual(h_anon_api.responses, [404])

    # ── O03: Invalid/Non-numeric Order IDs ─────────────────────────────────
    def test_O03_invalid_order_ids_handled_safely(self):
        _, token, _ = self.account()
        for invalid_id in ['abc', '0', '-1', '999999', '../etc/passwd', '1 UNION SELECT']:
            h_det = self.request(f"/orders/{invalid_id}", token=token)
            self.assertEqual(h_det.responses, [404])

            h_api = self.request(f"/api/orders/{invalid_id}", token=token)
            self.assertIn(h_api.responses[0], [400, 404])

    # ── O04: Historical Price and Item Snapshot Integrity ─────────────────
    def test_O04_catalog_price_change_does_not_alter_historical_order(self):
        _, token, sess = self.account()
        # Đặt mua Laptop Pro 15 với giá gốc $1299.99
        order = self.create_order_for_user(token, sess, product_id=1, quantity=1)
        self.assertEqual(order['total'], 1299.99)

        # Sửa giá và tên sản phẩm trong catalog
        with self.app.storage_transaction(write=True) as db:
            db.execute("UPDATE products SET price=9999.99, name='Super Expensive Laptop' WHERE id=1")

        # Order detail vẫn hiển thị đúng unit price snapshot ($1299.99) và total ($1299.99)
        h_det = self.request(f"/orders/{order['id']}", token=token)
        self.assertEqual(h_det.responses, [200])
        html = h_det.wfile.getvalue().decode()
        self.assertIn("$1299.99", html)
        self.assertNotIn("$9999.99", html)

        # Order API snapshot vẫn giữ nguyên unit_price $1299.99 và total $1299.99
        h_api = self.request(f"/api/orders/{order['id']}", token=token)
        self.assertEqual(h_api.responses, [200])
        data = json.loads(h_api.wfile.getvalue().decode())
        self.assertEqual(data['order']['total'], 1299.99)
        self.assertEqual(data['items'][0]['unit_price'], 1299.99)

        # Invoice download vẫn hiển thị đúng $1299.99
        h_inv = self.request(f"/download/invoice?file={order['invoice_file']}", token=token)
        self.assertEqual(h_inv.responses, [200])
        inv_text = h_inv.wfile.getvalue().decode()
        self.assertIn("Total: $1299.99", inv_text)
        self.assertNotIn("9999.99", inv_text)

    # ── O05: Invoice Access & On-demand Synthesis ─────────────────────────
    def test_O05_invoice_access_and_dynamic_synthesis_fallback(self):
        _, token, sess = self.account()
        order = self.create_order_for_user(token, sess, product_id=2, quantity=2)
        inv_file = order['invoice_file']
        self.assertTrue(inv_file.startswith('INV-'))

        # 1. Download file khi tệp tồn tại trên đĩa
        h1 = self.request(f"/download/invoice?file={inv_file}", token=token)
        self.assertEqual(h1.responses, [200])
        self.assertIn(f"Invoice: {inv_file}", h1.wfile.getvalue().decode())
        self.assertIn("Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)", h1.wfile.getvalue().decode())

        # 2. Xóa file trên đĩa để kích hoạt fallback on-demand synthesis từ DB
        disk_path = self.app.UPLOAD_DIR / inv_file
        if disk_path.is_file():
            disk_path.unlink()

        h2 = self.request(f"/download/invoice?file={inv_file}", token=token)
        self.assertEqual(h2.responses, [200])
        content = h2.wfile.getvalue().decode()
        self.assertIn(f"Invoice: {inv_file}", content)
        self.assertIn("Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)", content)
        self.assertIn(f"Total: ${order['total']:.2f}", content)

    # ── O06: Invoice Security (IDOR & Path Traversal Prevention) ───────────
    def test_O06_invoice_idor_and_traversal_rejection(self):
        _, token_a, sess_a = self.account('user_inv_a')
        _, token_b, _ = self.account('user_inv_b')
        order_a = self.create_order_for_user(token_a, sess_a, product_id=1, quantity=1)

        # User B truy cập invoice của User A -> 404
        h_b = self.request(f"/download/invoice?file={order_a['invoice_file']}", token=token_b)
        self.assertEqual(h_b.responses, [404])

        # Anonymous truy cập invoice của User A -> 404
        h_anon = self.request(f"/download/invoice?file={order_a['invoice_file']}")
        self.assertEqual(h_anon.responses, [404])

        # Preflight 0.3: Path traversal, encoded traversal, CRLF injection inputs -> 400
        for bad_file in [
            '../secret.txt',
            '..%2f..%2fetc/passwd',
            'INV-123.txt',
            'INV-INVALID',
            'INV-00000000000000000000000000000001.txt\r\nSet-Cookie: evil=1',
            'INV-00000000000000000000000000000001.txt%0d%0aInjected: header',
            'INV-00000000000000000000000000000001.txt/../../etc/passwd',
            '/etc/passwd',
            'C:\\Windows\\win.ini'
        ]:
            h_bad = self.request(f"/download/invoice?file={bad_file}", token=token_a)
            self.assertEqual(h_bad.responses, [400])

    # ── R01: Valid Review Creation & Product Association ──────────────────
    def test_R01_valid_review_creation(self):
        fields, token, sess = self.account('reviewer_1')
        review_payload = {
            'product_id': '1',
            'rating': '5',
            'body': 'Excellent build quality and fast shipping!'
        }
        h = self.request('/reviews', 'POST', review_payload, token, sess['csrf_secret'])
        self.assertEqual(h.responses, [302])
        self.assertEqual(dict(h.sent_headers).get('Location'), '/products/1')

        # Verify DB record
        with self.app.storage_transaction() as db:
            rev = db.execute("SELECT * FROM reviews WHERE product_id=1 AND user_id=?", (sess['user_id'],)).fetchone()
            self.assertIsNotNone(rev)
            self.assertEqual(rev['rating'], 5)
            self.assertEqual(rev['username'], fields['username'])
            self.assertEqual(rev['body'], 'Excellent build quality and fast shipping!')

        # Verify rendered in product detail page
        h_prod = self.request('/products/1', token=token)
        self.assertEqual(h_prod.responses, [200])
        html = h_prod.wfile.getvalue().decode()
        self.assertIn(fields['username'], html)
        self.assertIn('Excellent build quality and fast shipping!', html)
        self.assertIn('★★★★★', html)

    # ── R02: Invalid Rating Rejection (DB Unchanged) ──────────────────────
    def test_R02_invalid_rating_rejected_and_db_unchanged(self):
        _, token, sess = self.account('reviewer_rating')
        count_before = self.scalar('SELECT count(*) FROM reviews')

        invalid_ratings = ['0', '6', '-1', '1.5', 'five', '', '999999999999', '3; DROP TABLE reviews;']
        for bad_rating in invalid_ratings:
            payload = {'product_id': '1', 'rating': bad_rating, 'body': 'Sample review body'}
            h = self.request('/reviews', 'POST', payload, token, sess['csrf_secret'])
            self.assertEqual(h.responses, [400])

        count_after = self.scalar('SELECT count(*) FROM reviews')
        self.assertEqual(count_before, count_after)

    # ── R03: Invalid / Empty / Oversized Body Rejection ────────────────────
    def test_R03_invalid_body_rejected_and_db_unchanged(self):
        _, token, sess = self.account('reviewer_body')
        count_before = self.scalar('SELECT count(*) FROM reviews')

        # Empty body
        h_empty = self.request('/reviews', 'POST', {'product_id': '1', 'rating': '4', 'body': '   '}, token, sess['csrf_secret'])
        self.assertEqual(h_empty.responses, [400])

        # Oversized body (> 4000 characters)
        oversized = 'A' * 4001
        h_over = self.request('/reviews', 'POST', {'product_id': '1', 'rating': '4', 'body': oversized}, token, sess['csrf_secret'])
        self.assertEqual(h_over.responses, [400])

        count_after = self.scalar('SELECT count(*) FROM reviews')
        self.assertEqual(count_before, count_after)

    # ── R04: Stored XSS Payload Safely Escaped ────────────────────────────
    def test_R04_stored_xss_in_review_is_html_escaped(self):
        _, token, sess = self.account('xss_author')
        xss_body = "<script>alert('xss_pwned')</script><img src=x onerror=alert(1)>"
        payload = {'product_id': '2', 'rating': '5', 'body': xss_body}
        h_post = self.request('/reviews', 'POST', payload, token, sess['csrf_secret'])
        self.assertEqual(h_post.responses, [302])

        # View product detail page
        h_view = self.request('/products/2', token=token)
        self.assertEqual(h_view.responses, [200])
        html = h_view.wfile.getvalue().decode()
        # Raw script tags must NOT be present
        self.assertNotIn("<script>alert('xss_pwned')</script>", html)
        self.assertNotIn("<img src=x onerror=alert(1)>", html)
        # Escaped entities MUST be present
        self.assertIn("&lt;script&gt;alert(&#x27;xss_pwned&#x27;)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    # ── R05: Server-side Identity Enforcement (Forged Author Ignored) ─────
    def test_R05_forged_author_in_payload_ignored(self):
        fields, token, sess = self.account('real_user')
        # Payload cố tình gửi user_id=999 và username='admin'
        payload = {
            'product_id': '1',
            'rating': '4',
            'body': 'Checking author integrity',
            'user_id': '999',
            'username': 'admin_impersonator'
        }
        h = self.request('/reviews', 'POST', payload, token, sess['csrf_secret'])
        self.assertEqual(h.responses, [302])

        with self.app.storage_transaction() as db:
            rev = db.execute("SELECT * FROM reviews WHERE body='Checking author integrity'").fetchone()
            self.assertIsNotNone(rev)
            # Tác giả lưu trong DB phải là session user thật, không phải forged input
            self.assertEqual(rev['user_id'], sess['user_id'])
            self.assertEqual(rev['username'], fields['username'])

    # ── R06: Review Non-existent Product Rejected ─────────────────────────
    def test_R06_review_nonexistent_product_rejected(self):
        _, token, sess = self.account('reviewer_prod')
        count_before = self.scalar('SELECT count(*) FROM reviews')

        # Non-existent positive product ID -> 404
        h_non = self.request('/reviews', 'POST', {'product_id': '9999', 'rating': '5', 'body': 'Great'}, token, sess['csrf_secret'])
        self.assertEqual(h_non.responses, [404])

        # Non-positive or malformed product ID -> 400
        for bad_pid in ['0', '-5', 'abc', '1; DROP TABLE products']:
            h_bad = self.request('/reviews', 'POST', {'product_id': bad_pid, 'rating': '5', 'body': 'Great'}, token, sess['csrf_secret'])
            self.assertEqual(h_bad.responses, [400])

        count_after = self.scalar('SELECT count(*) FROM reviews')
        self.assertEqual(count_before, count_after)

    # ── R07: Missing/Invalid CSRF Rejected ─────────────────────────────────
    def test_R07_review_csrf_protection(self):
        _, token, _ = self.account('reviewer_csrf')
        count_before = self.scalar('SELECT count(*) FROM reviews')

        payload = {'product_id': '1', 'rating': '5', 'body': 'CSRF test review'}
        # Missing CSRF
        h_miss = self.request('/reviews', 'POST', payload, token=token, csrf=None)
        self.assertEqual(h_miss.responses, [403])

        # Invalid CSRF
        h_inv = self.request('/reviews', 'POST', payload, token=token, csrf='0' * 64)
        self.assertEqual(h_inv.responses, [403])

        count_after = self.scalar('SELECT count(*) FROM reviews')
        self.assertEqual(count_before, count_after)

    # ── R08: Unauthenticated Review Attempt Rejected ──────────────────────
    def test_R08_unauthenticated_review_attempt_rejected(self):
        token_guest, guest_sess = self.guest()
        count_before = self.scalar('SELECT count(*) FROM reviews')

        payload = {'product_id': '1', 'rating': '5', 'body': 'Guest review attempt'}
        h = self.request('/reviews', 'POST', payload, token=token_guest, csrf=guest_sess['csrf_secret'])
        self.assertEqual(h.responses, [403])

        count_after = self.scalar('SELECT count(*) FROM reviews')
        self.assertEqual(count_before, count_after)


if __name__ == '__main__':
    unittest.main()
