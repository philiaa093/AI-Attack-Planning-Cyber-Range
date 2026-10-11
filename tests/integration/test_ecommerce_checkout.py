"""SL-04: Catalog, Cart, and Checkout integration tests (ShopLab).

Kiểm thử catalog, cart, checkout, money Decimal / minor units,
stock atomicity, idempotency owner semantics (Cases A, B, C, D, E),
và decoupled invoice filesystem side effect trong SQLite temp.
"""
from decimal import Decimal
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from test_ecommerce_storage import load_app


class ShopLabCheckoutTests(unittest.TestCase):
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

    def scalar(self, sql, params=()):
        with self.app.storage_transaction() as db:
            return db.execute(sql, params).fetchone()[0]

    def guest(self):
        h = self.request('/login')
        self.assertEqual(h.responses, [200])
        token = self.cookie(h)
        with self.app.storage_transaction() as db:
            row = dict(self.app.resolve_session(db, token))
        return token, row

    def cookie(self, h):
        for k, v in h.sent_headers:
            if k == 'Set-Cookie' and v.startswith('session='):
                return v.split(';')[0].split('=', 1)[1]
        return ''

    def identity(self, token):
        with self.app.storage_transaction() as db:
            row = self.app.resolve_session(db, token)
            return dict(row) if row is not None else None

    def account(self):
        token, row = self.guest()
        fields = {'username': 'user_' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24), 'email': 'fixture@example.invalid'}
        h = self.request('/register', 'POST', fields, token, row['csrf_secret'])
        self.assertEqual(h.responses, [302])
        new = self.cookie(h)
        return fields, new, self.identity(new)

    def snapshot(self):
        with self.app.storage_transaction() as db:
            state = tuple(db.iterdump())
        files = {p.name: p.read_bytes() for p in self.app.UPLOAD_DIR.iterdir()}
        return state, files

    # ── C01: Catalog Browse, Search, Detail, Missing ID, Stock Display ────
    def test_C01_catalog_browse_search_detail_missing_and_stock_display(self):
        t, s = self.guest()
        # Home page lists featured products
        h = self.request('/', token=t)
        self.assertEqual(h.responses, [200])
        self.assertIn('Featured Products', h.wfile.getvalue().decode())

        # Products list with search and category filter
        h = self.request('/products?q=Laptop&category=1', token=t)
        self.assertEqual(h.responses, [200])
        self.assertIn('Laptop Pro 15', h.wfile.getvalue().decode())

        # Detail view for existing product
        h = self.request('/products/1', token=t)
        self.assertEqual(h.responses, [200])
        out = h.wfile.getvalue().decode()
        self.assertIn('Laptop Pro 15', out)
        self.assertIn('5 in stock', out)
        self.assertIn("name='quantity'", out)

        # Missing product ID returns 404
        h = self.request('/products/99999', token=t)
        self.assertEqual(h.responses, [404])

        # Invalid product ID formats return 400
        for bad_id in ('abc', '0', '-1', '9223372036854775808', '01'):
            h = self.request('/products/' + bad_id, token=t)
            self.assertEqual(h.responses, [400])

        # Out-of-stock product display
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=0 WHERE id=1')
        h = self.request('/products/1', token=t)
        self.assertEqual(h.responses, [200])
        out = h.wfile.getvalue().decode()
        self.assertIn('Out of stock', out)
        self.assertNotIn('Add to Cart</button>', out)

        # Product card on list page shows out-of-stock badge
        h = self.request('/products?q=Laptop', token=t)
        self.assertEqual(h.responses, [200])
        self.assertIn('Out of stock', h.wfile.getvalue().decode())

    # ── C02: Cart Isolation and Ownership ────────────────────────────────
    def test_C02_cart_isolation_guest_and_user_ownership(self):
        gt1, gi1 = self.guest()
        gt2, gi2 = self.guest()
        _, ut1, ui1 = self.account()

        # Guest 1 adds Product 2 (qty 2)
        h = self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 2}, gt1, gi1['csrf_secret'])
        self.assertEqual(h.responses, [302])

        # Guest 2 adds Product 2 (qty 3)
        h = self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 3}, gt2, gi2['csrf_secret'])
        self.assertEqual(h.responses, [302])

        # User 1 adds Product 2 (qty 1)
        h = self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, ut1, ui1['csrf_secret'])
        self.assertEqual(h.responses, [302])

        # Verify quantities in isolation
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE session_id=?', (gi1['cart_key'],)), 2)
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE session_id=?', (gi2['cart_key'],)), 3)
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE session_id=?', (ui1['cart_key'],)), 1)

        # Guest 1 attempts to update Guest 2's cart item
        g2_cart_id = self.scalar('SELECT id FROM cart WHERE session_id=?', (gi2['cart_key'],))
        before = self.snapshot()
        h = self.request('/cart/update', 'POST', {'cart_id': g2_cart_id, 'quantity': 5}, gt1, gi1['csrf_secret'])
        self.assertEqual(h.responses, [404])
        self.assertEqual(self.snapshot(), before)

        # Guest 1 attempts to remove Guest 2's cart item
        h = self.request('/cart/remove', 'POST', {'cart_id': g2_cart_id}, gt1, gi1['csrf_secret'])
        self.assertEqual(h.responses, [302])
        # Guest 2's item was NOT removed
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (gi2['cart_key'],)), 1)

        # Guest 1 updates their own item to 4
        g1_cart_id = self.scalar('SELECT id FROM cart WHERE session_id=?', (gi1['cart_key'],))
        h = self.request('/cart/update', 'POST', {'cart_id': g1_cart_id, 'quantity': 4}, gt1, gi1['csrf_secret'])
        self.assertEqual(h.responses, [302])
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE id=?', (g1_cart_id,)), 4)

    # ── C03: Quantity Validation on Add and Update ────────────────────────
    def test_C03_quantity_validation_add_and_update(self):
        t, s = self.guest()
        # Invalid quantities on add
        invalid_quantities = ('0', '-1', '-99', 'abc', '1.5', '01', '00', '100', '')
        for bad_qty in invalid_quantities:
            with self.subTest(bad_qty=bad_qty):
                before = self.snapshot()
                h = self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': bad_qty}, t, s['csrf_secret'])
                self.assertEqual(h.responses, [400])
                self.assertEqual(self.snapshot(), before)

        # Add valid quantity (qty 3, stock is 5)
        h = self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 3}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [302])
        cart_id = self.scalar('SELECT id FROM cart WHERE session_id=?', (s['cart_key'],))

        # Adding 3 more exceeds stock of 5 (total would be 6)
        before = self.snapshot()
        h = self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 3}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [400])
        self.assertEqual(self.snapshot(), before)

        # Invalid quantities on update
        for bad_qty in invalid_quantities:
            with self.subTest(bad_update=bad_qty):
                before = self.snapshot()
                h = self.request('/cart/update', 'POST', {'cart_id': cart_id, 'quantity': bad_qty}, t, s['csrf_secret'])
                self.assertEqual(h.responses, [400])
                self.assertEqual(self.snapshot(), before)

        # Update to quantity exceeding stock (stock is 5, requested 6)
        before = self.snapshot()
        h = self.request('/cart/update', 'POST', {'cart_id': cart_id, 'quantity': 6}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [400])
        self.assertEqual(self.snapshot(), before)

        # Valid update (from 3 to 5)
        h = self.request('/cart/update', 'POST', {'cart_id': cart_id, 'quantity': 5}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [302])
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE id=?', (cart_id,)), 5)

        # Adding to out-of-stock product returns 409
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=0 WHERE id=3')
        before = self.snapshot()
        h = self.request('/cart/add', 'POST', {'product_id': 3, 'quantity': 1}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [409])
        self.assertEqual(self.snapshot(), before)

    # ── C04: Client Price and Owner Tampering Ignored ─────────────────────
    def test_C04_client_price_and_owner_tampering_ignored(self):
        t, s = self.guest()
        # Client sends price manipulation in cart add
        h = self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1, 'price': '0.01'}, t, s['csrf_secret'])
        self.assertEqual(h.responses, [302])

        # Cart view computes authoritative total from DB products.price (1299.99)
        h = self.request('/cart', token=t)
        self.assertIn('$1299.99', h.wfile.getvalue().decode())
        self.assertNotIn('$0.01', h.wfile.getvalue().decode())

        # Client sends tampered total and price in checkout
        shipping = {'full_name': 'Test User', 'address': '123 Test St', 'email': 'test@example.invalid',
                    'price': '0.01', 'total': '0.01', 'session_id': 'foreign', 'user_id': 999}
        h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])
        self.assertEqual(h.responses, [200])

        # Order created with authoritative total ($1299.99)
        oid = self.scalar('SELECT id FROM orders WHERE session_id=?', (s['cart_key'],))
        order_total = self.scalar('SELECT total FROM orders WHERE id=?', (oid,))
        self.assertEqual(order_total, 1299.99)
        item_price = self.scalar('SELECT unit_price FROM order_items WHERE order_id=?', (oid,))
        self.assertEqual(item_price, 1299.99)

    # ── C05: Valid Checkout Commits Atomically ────────────────────────────
    def test_C05_valid_checkout_commits_stock_order_items_and_clears_cart(self):
        _, t, s = self.account()
        # Add Product 1 (qty 2, price 1299.99) and Product 2 (qty 1, price 29.99)
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 2}, t, s['csrf_secret'])
        self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, t, s['csrf_secret'])

        stock1_before = self.scalar('SELECT stock FROM products WHERE id=1')
        stock2_before = self.scalar('SELECT stock FROM products WHERE id=2')

        shipping = {'full_name': 'Alice Smith', 'address': '456 Elm Ave', 'email': 'alice@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])
        self.assertEqual(h.responses, [200])
        self.assertIn('Order Placed Successfully!', h.wfile.getvalue().decode())

        # Stock decremented
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), stock1_before - 2)
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=2'), stock2_before - 1)

        # Cart cleared
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (s['cart_key'],)), 0)

        # Order total exact: 1299.99 * 2 + 29.99 = 2629.97
        oid = self.scalar('SELECT id FROM orders WHERE user_id=?', (s['user_id'],))
        self.assertEqual(self.scalar('SELECT total FROM orders WHERE id=?', (oid,)), 2629.97)
        self.assertEqual(self.scalar('SELECT currency FROM orders WHERE id=?', (oid,)), 'USD')
        self.assertEqual(self.scalar('SELECT status FROM orders WHERE id=?', (oid,)), 'completed')

        # Order items exact snapshots
        self.assertEqual(self.scalar("SELECT count(*) FROM order_items WHERE order_id=?", (oid,)), 2)
        self.assertEqual(self.scalar("SELECT unit_price FROM order_items WHERE order_id=? AND product_id=1", (oid,)), 1299.99)
        self.assertEqual(self.scalar("SELECT quantity FROM order_items WHERE order_id=? AND product_id=1", (oid,)), 2)

        # Invoice download serves invoice
        inv_file = self.scalar('SELECT invoice_file FROM orders WHERE id=?', (oid,))
        dl = self.request('/download/invoice?file=' + inv_file, token=t)
        self.assertEqual(dl.responses, [200])
        self.assertIn('$2629.97', dl.wfile.getvalue().decode())

    # ── C06a & C06b: Decoupled Invoice Semantics ──────────────────────────
    def test_C06a_checkout_failure_creates_no_invoice_files(self):
        # A: checkout failure → không invoice mới, không orphan file
        t, s = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 2}, t, s['csrf_secret'])

        stock_before = self.scalar('SELECT stock FROM products WHERE id=1')
        cart_count = self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (s['cart_key'],))

        # Manually alter stock to 0 to simulate stock conflict during checkout
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=0 WHERE id=1')

        shipping = {'full_name': 'Bob', 'address': '789 Oak St', 'email': 'bob@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])
        self.assertEqual(h.responses, [409])

        # Assert no orders and zero files created on filesystem
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (s['cart_key'],)), cart_count)
        self.assertEqual(len(list(self.app.UPLOAD_DIR.iterdir())), 0)

    def test_C06b_invoice_failure_does_not_rollback_committed_order(self):
        # B & C: DB commit không phụ thuộc filesystem; invoice write failure post-commit không rollback DB
        t, s = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, t, s['csrf_secret'])
        stock_before = self.scalar('SELECT stock FROM products WHERE id=1')

        shipping = {'full_name': 'Carol', 'address': '123 Tree Rd', 'email': 'carol@example.invalid'}
        with patch.object(Path, 'open', side_effect=PermissionError('disk write error')):
            h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])

        # Checkout succeeds because DB commit was independent of filesystem
        self.assertEqual(h.responses, [200])
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (s['cart_key'],)), 0)
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), stock_before - 1)

        # Dynamic fallback serves invoice even if file on disk was not created
        inv_file = self.scalar('SELECT invoice_file FROM orders')
        dl = self.request('/download/invoice?file=' + inv_file, token=t)
        self.assertEqual(dl.responses, [200])
        self.assertIn(f'Invoice: {inv_file}', dl.wfile.getvalue().decode())

    # ── C07: Idempotency Owner Semantics (Cases A, B, C, D, E) ─────────────
    def test_C07_idempotency_cases_a_b_c_d_e(self):
        # CASE A: Guest A + key K -> order 1; retry same session + key K -> same order 1
        gt_a, gi_a = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt_a, gi_a['csrf_secret'])
        shipping = {'full_name': 'GuestA', 'address': 'Lane A', 'email': 'a@example.invalid'}
        headers = [('Idempotency-Key', 'k-idem-test')]

        h_a1 = self.request('/checkout', 'POST', shipping, gt_a, gi_a['csrf_secret'], headers=headers)
        self.assertEqual(h_a1.responses, [200])
        oid_a = self.scalar('SELECT id FROM orders WHERE session_id=?', (gi_a['cart_key'],))

        # Retry with same key K in same session A
        h_a2 = self.request('/checkout', 'POST', shipping, gt_a, gi_a['csrf_secret'], headers=headers)
        self.assertEqual(h_a2.responses, [200])
        self.assertIn(f'Order #{oid_a}', h_a2.wfile.getvalue().decode())
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 1)

        # CASE B: Guest B + same key K -> does NOT collide with Guest A, creates order 2
        gt_b, gi_b = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt_b, gi_b['csrf_secret'])
        h_b = self.request('/checkout', 'POST', shipping, gt_b, gi_b['csrf_secret'], headers=headers)
        self.assertEqual(h_b.responses, [200])
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 2)
        oid_b = self.scalar('SELECT id FROM orders WHERE session_id=?', (gi_b['cart_key'],))
        self.assertNotEqual(oid_a, oid_b)

        # CASE C: Authenticated user U + key K -> creates order U
        u_fields, ut_1, ui_1 = self.account()
        self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, ut_1, ui_1['csrf_secret'])
        stock2_before = self.scalar('SELECT stock FROM products WHERE id=2')
        h_u1 = self.request('/checkout', 'POST', shipping, ut_1, ui_1['csrf_secret'], headers=headers)
        self.assertEqual(h_u1.responses, [200])
        oid_u = self.scalar('SELECT id FROM orders WHERE user_id=?', (ui_1['user_id'],))
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=2'), stock2_before - 1)

        # CASE D: Same user U after session rotation / new valid session retries with key K
        # Simulate user login to obtain a new session token for the SAME user U
        gt_new, gi_new = self.guest()
        h_login = self.request('/login', 'POST', u_fields, gt_new, gi_new['csrf_secret'])
        self.assertEqual(h_login.responses, [302])
        ut_2 = self.cookie(h_login)
        ui_2 = self.identity(ut_2)
        self.assertEqual(ui_2['user_id'], ui_1['user_id'])
        self.assertNotEqual(ui_2['token_digest'], ui_1['token_digest'])

        # User U retries same submission with key K in the new session
        h_u_retry = self.request('/checkout', 'POST', shipping, ut_2, ui_2['csrf_secret'], headers=headers)
        self.assertEqual(h_u_retry.responses, [200])
        self.assertIn(f'Order #{oid_u}', h_u_retry.wfile.getvalue().decode())
        # Stock NOT decremented again, no new order created
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=2'), stock2_before - 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM orders WHERE user_id=?', (ui_1['user_id'],)), 1)

        # CASE E: Different authenticated user U2 + same key K -> independent
        _, ut_other, ui_other = self.account()
        self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, ut_other, ui_other['csrf_secret'])
        h_other = self.request('/checkout', 'POST', shipping, ut_other, ui_other['csrf_secret'], headers=headers)
        self.assertEqual(h_other.responses, [200])
        self.assertEqual(self.scalar('SELECT count(*) FROM orders WHERE user_id=?', (ui_other['user_id'],)), 1)

        # Conflict check: same key with different payload
        tampered = {**shipping, 'full_name': 'Tampered Name'}
        h_conflict = self.request('/checkout', 'POST', tampered, ut_2, ui_2['csrf_secret'], headers=headers)
        self.assertEqual(h_conflict.responses, [409])

    # ── C08: Stale Stock Recheck and Concurrency (No Oversell) ────────────
    def test_C08_stale_stock_recheck_prevents_oversell(self):
        gt1, gi1 = self.guest()
        gt2, gi2 = self.guest()

        # Set Product 1 stock to 1
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=1 WHERE id=1')

        # Both guests add the last item to cart
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt1, gi1['csrf_secret'])
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt2, gi2['csrf_secret'])

        # Guest 1 checks out first -> succeeds
        shipping1 = {'full_name': 'Winner', 'address': '1 Lane', 'email': 'winner@example.invalid'}
        h1 = self.request('/checkout', 'POST', shipping1, gt1, gi1['csrf_secret'])
        self.assertEqual(h1.responses, [200])
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 0)

        # Guest 2 attempts checkout -> stale stock detected, 409 Conflict
        shipping2 = {'full_name': 'Loser', 'address': '2 Lane', 'email': 'loser@example.invalid'}
        h2 = self.request('/checkout', 'POST', shipping2, gt2, gi2['csrf_secret'])
        self.assertEqual(h2.responses, [409])
        # Stock remains 0, NEVER negative
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 0)
        # Exactly 1 order created
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 1)
        # Guest 2 cart item retained
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?', (gi2['cart_key'],)), 1)

    def test_C08_concurrent_checkout_last_item_has_single_winner(self):
        gt1, gi1 = self.guest()
        gt2, gi2 = self.guest()

        # Set Product 1 stock to 1
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=1 WHERE id=1')

        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt1, gi1['csrf_secret'])
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, gt2, gi2['csrf_secret'])

        start_barrier = threading.Barrier(2)
        results = []

        def buyer(token, info, name):
            start_barrier.wait()
            h = self.request('/checkout', 'POST', {'full_name': name, 'address': 'A', 'email': 'a@b.c'},
                             token, info['csrf_secret'])
            results.append((name, h.responses))

        t1 = threading.Thread(target=buyer, args=(gt1, gi1, 'Buyer1'))
        t2 = threading.Thread(target=buyer, args=(gt2, gi2, 'Buyer2'))
        t1.start()
        t2.start()
        t1.join(10)
        t2.join(10)

        statuses = [status for _, [status] in results]
        self.assertIn(200, statuses)
        self.assertIn(409, statuses)
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 1)

    # ── C09: Price Snapshot Preserved on Restart and Catalog Edit ─────────
    def test_C09_restart_and_catalog_price_change_snapshot_preservation(self):
        t, s = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, t, s['csrf_secret'])
        shipping = {'full_name': 'Snapshot Test', 'address': '100 Road', 'email': 'snap@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])
        self.assertEqual(h.responses, [200])

        oid = self.scalar('SELECT id FROM orders WHERE session_id=?', (s['cart_key'],))

        # Update product price in catalog
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET price=9999.99 WHERE id=1')

        # Restart storage
        self.app.close_storage()
        self.app.initialize_storage(self.temp.name)

        # Verify order and item snapshot did NOT change
        self.assertEqual(self.scalar('SELECT total FROM orders WHERE id=?', (oid,)), 1299.99)
        self.assertEqual(self.scalar('SELECT unit_price FROM order_items WHERE order_id=?', (oid,)), 1299.99)

        # Verify API endpoint returns snapshot price
        h = self.request('/api/orders/' + str(oid), token=t)
        self.assertEqual(h.responses, [200])
        data = json.loads(h.wfile.getvalue())
        self.assertEqual(data['order']['total'], 1299.99)
        self.assertEqual(data['items'][0]['unit_price'], 1299.99)

    # ── CSRF Protection on Cart Update and Checkout ───────────────────────
    def test_CSRF_cart_update_and_checkout_rejected_without_valid_csrf(self):
        t, s = self.guest()
        foreign_t, foreign_s = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 1, 'quantity': 1}, t, s['csrf_secret'])
        cid = self.scalar('SELECT id FROM cart WHERE session_id=?', (s['cart_key'],))

        # /cart/update without CSRF
        before = self.snapshot()
        h = self.request('/cart/update', 'POST', {'cart_id': cid, 'quantity': 2}, t, csrf=None)
        self.assertEqual(h.responses, [403])
        self.assertEqual(self.snapshot(), before)

        # /cart/update with foreign CSRF
        h = self.request('/cart/update', 'POST', {'cart_id': cid, 'quantity': 2}, t, csrf=foreign_s['csrf_secret'])
        self.assertEqual(h.responses, [403])
        self.assertEqual(self.snapshot(), before)

        # /checkout without CSRF
        shipping = {'full_name': 'Eve', 'address': 'Evil St', 'email': 'eve@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, t, csrf=None)
        self.assertEqual(h.responses, [403])
        self.assertEqual(self.snapshot(), before)

        # /checkout with foreign CSRF
        h = self.request('/checkout', 'POST', shipping, t, csrf=foreign_s['csrf_secret'])
        self.assertEqual(h.responses, [403])
        self.assertEqual(self.snapshot(), before)

    # ── Money Verification: Exact Minor Units and Round-Trip Persistence ──
    def test_money_minor_precision_and_exact_persistence(self):
        # Insert test products with specific test prices: 0.10, 0.20, 0.30, 10.01, 19.99
        with self.app.storage_transaction(write=True) as db:
            db.execute("INSERT INTO products(name, description, price, category_id, stock) VALUES "
                       "('P10', 'Desc', 0.10, 1, 10),"
                       "('P20', 'Desc', 0.20, 1, 10),"
                       "('P30', 'Desc', 0.30, 1, 10),"
                       "('P1001', 'Desc', 10.01, 1, 10),"
                       "('P1999', 'Desc', 19.99, 1, 10)")
            p10 = db.execute("SELECT id FROM products WHERE name='P10'").fetchone()[0]
            p20 = db.execute("SELECT id FROM products WHERE name='P20'").fetchone()[0]
            p1001 = db.execute("SELECT id FROM products WHERE name='P1001'").fetchone()[0]
            p1999 = db.execute("SELECT id FROM products WHERE name='P1999'").fetchone()[0]

        # Multi-line Test 1: 0.10 + 0.20 = 0.30 exactly (tests IEEE 754 float drift)
        t, s = self.guest()
        self.request('/cart/add', 'POST', {'product_id': p10, 'quantity': 1}, t, s['csrf_secret'])
        self.request('/cart/add', 'POST', {'product_id': p20, 'quantity': 1}, t, s['csrf_secret'])
        shipping = {'full_name': 'Precision User', 'address': '1 Exact Pl', 'email': 'exact@example.invalid'}
        h = self.request('/checkout', 'POST', shipping, t, s['csrf_secret'])
        self.assertEqual(h.responses, [200])

        oid1 = self.scalar('SELECT id FROM orders WHERE session_id=?', (s['cart_key'],))
        total1 = self.scalar('SELECT total FROM orders WHERE id=?', (oid1,))
        self.assertEqual(total1, 0.30)
        self.assertEqual(self.scalar('SELECT currency FROM orders WHERE id=?', (oid1,)), 'USD')
        # Check order items
        self.assertEqual(self.scalar('SELECT unit_price FROM order_items WHERE order_id=? AND product_id=?', (oid1, p10)), 0.10)
        self.assertEqual(self.scalar('SELECT unit_price FROM order_items WHERE order_id=? AND product_id=?', (oid1, p20)), 0.20)

        # Multi-line Test 2: 10.01 * 2 + 19.99 * 3 = 20.02 + 59.97 = 79.99
        t2, s2 = self.guest()
        self.request('/cart/add', 'POST', {'product_id': p1001, 'quantity': 2}, t2, s2['csrf_secret'])
        self.request('/cart/add', 'POST', {'product_id': p1999, 'quantity': 3}, t2, s2['csrf_secret'])
        h2 = self.request('/checkout', 'POST', shipping, t2, s2['csrf_secret'])
        self.assertEqual(h2.responses, [200])

        oid2 = self.scalar('SELECT id FROM orders WHERE session_id=?', (s2['cart_key'],))
        total2 = self.scalar('SELECT total FROM orders WHERE id=?', (oid2,))
        self.assertEqual(total2, 79.99)
        self.assertEqual(self.scalar('SELECT currency FROM orders WHERE id=?', (oid2,)), 'USD')

    def test_existing_database_upgrade_migrates_order_idempotency(self):
        """Preflight 0.2: Upgrade test mô phỏng existing database với schema cũ."""
        with TemporaryDirectory() as upgrade_dir:
            db_path = Path(upgrade_dir) / 'shoplab.sqlite3'
            # 1. Tạo database theo schema trước revision owner_key
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('PRAGMA foreign_keys = ON')
                for stmt in self.app._SCHEMA:
                    if 'order_idempotency' not in stmt:
                        conn.execute(stmt)
                conn.execute('''
                    CREATE TABLE order_idempotency (
                        key TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        user_id INTEGER REFERENCES users(id),
                        order_id INTEGER NOT NULL REFERENCES orders(id),
                        request_hash TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY(key, session_id)
                    )
                ''')
                conn.execute('PRAGMA user_version = 2')
                # 2. Insert dữ liệu tối thiểu
                conn.execute("INSERT INTO orders (id, session_id, total, status) VALUES (999, 'legacy_sess', 29.99, 'completed')")
                conn.execute("INSERT INTO order_idempotency VALUES ('legacy_key', 'legacy_sess', NULL, 999, 'legacy_hash', 1000)")
                conn.commit()
            finally:
                conn.close()

            # 3. Khởi động storage bằng code mới
            self.app.close_storage()
            self.app.initialize_storage(upgrade_dir)

            # 4. Verify schema mới usable và legacy row được migrate an toàn
            with self.app.storage_transaction() as db:
                cols = {c[1] for c in db.execute("PRAGMA table_info(order_idempotency)").fetchall()}
                self.assertIn('owner_key', cols)
                migrated_row = db.execute("SELECT * FROM order_idempotency WHERE key='legacy_key'").fetchone()
                self.assertIsNotNone(migrated_row)
                self.assertEqual(migrated_row['owner_key'], 'guest:legacy_sess')

            # 5. Login / authenticated checkout
            fields, token, user_session = self.account()
            self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, token, user_session['csrf_secret'])
            idem_key = 'idem_after_upgrade_001'
            shipping = {'full_name': 'Upgrade User', 'address': '101 Main St', 'email': 'up@example.invalid'}
            h1 = self.request('/checkout', 'POST', shipping, token, user_session['csrf_secret'], headers=[('Idempotency-Key', idem_key)])
            self.assertEqual(h1.responses, [200])

            # 6. Verify idempotency hoạt động
            with self.app.storage_transaction() as db:
                new_idem = db.execute("SELECT * FROM order_idempotency WHERE key=?", (idem_key,)).fetchone()
                self.assertIsNotNone(new_idem)
                self.assertEqual(new_idem['owner_key'], f"user:{user_session['user_id']}")
                stock_after_first = db.execute("SELECT stock FROM products WHERE id=2").fetchone()[0]

            # 7. Restart storage
            self.app.close_storage()
            self.app.initialize_storage(upgrade_dir)

            # 8. Retry với cùng key
            h2 = self.request('/checkout', 'POST', shipping, token, user_session['csrf_secret'], headers=[('Idempotency-Key', idem_key)])
            self.assertEqual(h2.responses, [200])

            # 9. Verify không duplicate order và không decrement stock lần hai
            with self.app.storage_transaction() as db:
                stock_after_retry = db.execute("SELECT stock FROM products WHERE id=2").fetchone()[0]
                self.assertEqual(stock_after_first, stock_after_retry)
                order_count = db.execute("SELECT count(*) FROM orders WHERE user_id=?", (user_session['user_id'],)).fetchone()[0]
                self.assertEqual(order_count, 1)

            # Restore original test storage
            self.app.close_storage()
            self.app.initialize_storage(self.temp.name)

    def test_post_commit_action_lifecycle_and_single_execution(self):
        """Preflight 0.4: Post-commit callback lifecycle và single execution guarantee."""
        token, guest_sess = self.guest()
        self.request('/cart/add', 'POST', {'product_id': 2, 'quantity': 1}, token, guest_sess['csrf_secret'])

        callback_counter = [0]
        def failing_callback(*args):
            callback_counter[0] += 1
            raise RuntimeError("fixture post-commit failure")

        shipping = {'full_name': 'Lifecycle User', 'address': '22 Park Ave', 'email': 'life@example.invalid'}

        # Request A: checkout với post-commit callback bị fail
        body = urlencode(shipping).encode()
        h = object.__new__(self.app.Handler)
        h.path = '/checkout'
        h.headers = Message()
        h.headers['Content-Length'] = str(len(body))
        h.headers['Cookie'] = 'session=' + token
        h.headers['X-CSRF-Token'] = guest_sess['csrf_secret']
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.responses, h.sent_headers = [], []
        h.send_response = h.responses.append
        h.send_header = lambda k, v: h.sent_headers.append((k, v))
        h.end_headers = lambda: None

        with patch.object(self.app.Handler, '_create_invoice_post_commit', side_effect=failing_callback):
            h.do_POST()

        self.assertEqual(h.responses, [200])
        self.assertEqual(callback_counter[0], 1)
        self.assertIsNone(h._post_commit_action)

        # Request B: GET trên cùng Handler instance (mô phỏng keep-alive connection reuse)
        h.path = '/cart'
        h.headers = Message()
        h.headers['Cookie'] = 'session=' + token
        h.rfile, h.wfile = io.BytesIO(b''), io.BytesIO()
        h.responses, h.sent_headers = [], []
        h.send_response = h.responses.append
        h.send_header = lambda k, v: h.sent_headers.append((k, v))
        h.end_headers = lambda: None

        with patch.object(self.app.Handler, '_create_invoice_post_commit', side_effect=failing_callback):
            h.do_GET()

        self.assertEqual(h.responses, [200])
        # Callback của Request A KHÔNG được chạy lại
        self.assertEqual(callback_counter[0], 1)
        self.assertIsNone(h._post_commit_action)


if __name__ == '__main__':
    unittest.main()
