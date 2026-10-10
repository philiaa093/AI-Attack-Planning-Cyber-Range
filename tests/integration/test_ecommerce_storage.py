"""Kiểm thử lifecycle SQLite bằng dữ liệu giả trong temp; không socket/Docker."""
from types import ModuleType, SimpleNamespace
import builtins
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import json
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
import secrets
from urllib.parse import urlencode

APP_PATH = Path(__file__).resolve().parents[2] / "cyber-range/targets/ecommerce/app.py"


def load_app(source=None):
    code = compile(APP_PATH.read_text(encoding="utf-8") if source is None else source, str(APP_PATH), "exec")
    original_open = builtins.open

    def read_only_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            raise AssertionError("Import ghi tệp")
        return original_open(file, mode, *args, **kwargs)

    with TemporaryDirectory() as directory, ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ", {"SHOPLAB_DATA_DIR": directory}))
        stack.enter_context(patch("builtins.open", side_effect=read_only_open))
        guards = [stack.enter_context(patch(target, side_effect=AssertionError(target))) for target in (
            "pathlib.Path.mkdir", "pathlib.Path.write_text", "pathlib.Path.write_bytes",
            "pathlib.Path.open", "sqlite3.connect", "socket.socket", "socket.create_connection",
            "http.server.HTTPServer.__init__", "http.server.HTTPServer.serve_forever",
        )]
        module = ModuleType("storage_import_fixture")
        module.__file__ = str(APP_PATH)
        exec(code, module.__dict__)
        for guard in guards:
            guard.assert_not_called()
        assert not list(Path(directory).iterdir()), "Import tạo tệp"
    return module


class ShopLabStorageTests(unittest.TestCase):
    def setUp(self):
        self.app = load_app()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.app.close_storage)

    def start(self):
        self.app.initialize_storage(self.directory.name)

    def scalar(self, sql):
        with self.app.storage_transaction() as db:
            return db.execute(sql).fetchone()[0]

    def handler(self, path, body=b'', cookie=''):
        handler = object.__new__(self.app.Handler)
        handler.path = path
        handler.headers = {'Content-Length': str(len(body)), 'Cookie': cookie}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.responses = []
        handler.sent_headers = []
        handler.send_response = handler.responses.append
        handler.send_header = lambda k, v: handler.sent_headers.append((k, v))
        handler.end_headers = lambda: None
        return handler

    def guest(self):
        with self.app.storage_transaction(write=True) as db:
            token, row = self.app.create_session(db)
            return token, dict(row)

    def authorized_handler(self, path, body=b'', *, token=None, row=None):
        if token is None:
            token, row = self.guest()
        handler = self.handler(path, body, 'session=' + token)
        handler.headers['X-CSRF-Token'] = row['csrf_secret']
        return handler

    def test_import_does_not_open_storage(self):
        self.assertIsNone(self.app._database_path)
        self.assertIsNone(load_app()._database_path)

    def test_import_guards_detect_side_effects(self):
        for source in (
            "open('fixture.txt', 'w')",
            "from pathlib import Path; Path('fixture').mkdir()",
            "import sqlite3; sqlite3.connect(':memory:')",
            "import socket; socket.socket()",
            "from http.server import HTTPServer; HTTPServer(('127.0.0.1', 0), None)",
            "from http.server import HTTPServer; HTTPServer.serve_forever(None)",
        ):
            with self.subTest(source=source), self.assertRaises(AssertionError):
                load_app(source)

    def test_reopen_preserves_stock_and_does_not_reseed(self):
        self.start()
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=3 WHERE id=1')
        self.app.close_storage()
        self.app.close_storage()
        self.start()
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 3)
        self.assertEqual(self.scalar('SELECT count(*) FROM products'), 10)
        self.assertEqual(self.scalar('PRAGMA user_version'), 2)
        self.assertTrue((Path(self.directory.name) / 'shoplab.sqlite3').is_file())
        self.assertTrue((Path(self.directory.name) / 'invoices').is_dir())

    def test_sample_data_has_no_fixed_user_accounts(self):
        self.start()
        self.assertEqual(self.scalar('SELECT count(*) FROM users'), 0)
        self.assertEqual(self.scalar('PRAGMA foreign_keys'), 1)

    def test_each_connection_enables_foreign_keys_and_configured_busy_timeout(self):
        self.start()
        connections = []
        with patch.object(self.app, 'BUSY_SECONDS', .05):
            for write in (False, True, False):
                with self.app.storage_transaction(write=write) as db:
                    connections.append(db)
                    self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
                    self.assertEqual(db.execute('PRAGMA busy_timeout').fetchone()[0], 50)
        self.assertEqual(len({id(db) for db in connections}), 3)
        self.assertEqual(self.app._active, 0)

    def test_double_initialization_is_rejected(self):
        self.start()
        with self.assertRaises(self.app.StorageError):
            self.start()

    def test_search_and_category_filters_combine(self):
        self.start()
        with self.app.storage_transaction() as db:
            self.assertEqual([r['name'] for r in self.app.search_products(db, 'Python', '2')], ['Python Mastery'])
            self.assertEqual(self.app.search_products(db, 'Python', '1'), [])

    def test_literal_search_characters_do_not_become_wildcards(self):
        self.start()
        with self.app.storage_transaction() as db:
            self.assertEqual([r['name'] for r in self.app.search_products(db, '%')], ['Cotton T-Shirt (M)'])
            for query in ('_', '!', "O'Reilly"):
                self.assertEqual(self.app.search_products(db, query), [])
            self.assertEqual(len(self.app.search_products(db)), 10)

    def test_invalid_category_and_long_search_are_rejected(self):
        self.start()
        with self.app.storage_transaction() as db:
            for category in ('abc', '-1', '0', '9' * 11):
                with self.subTest(category=category), self.assertRaises(ValueError):
                    self.app.search_products(db, '', category)
            with self.assertRaises(ValueError):
                self.app.search_products(db, 'a' * 201)

    def test_uninitialized_and_closed_admission_reject(self):
        for initialized in (False, True):
            if initialized:
                self.start()
                self.app.close_storage()
            with self.assertRaises(self.app.StorageError):
                with self.app.storage_transaction():
                    self.fail('Không được admit')

    def test_rollback_on_exception_and_base_exception(self):
        self.start()
        for error in (ValueError, KeyboardInterrupt):
            with self.assertRaises(error):
                with self.app.storage_transaction(write=True) as db:
                    db.execute('UPDATE products SET stock=99 WHERE id=1')
                    db.execute("INSERT INTO categories(name) VALUES ('synthetic')")
                    raise error('fixture')
            self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 5)
            self.assertEqual(self.scalar('SELECT count(*) FROM categories'), 4)
            self.assertEqual(self.app._active, 0)

    def failing_connection(self):
        app = self.app
        connect = app._connect
        class FailingCommit:
            def __init__(self, path):
                self.db = connect(path)
                self.closed = False
                self.rolled_back = False
            def __getattr__(self, name):
                return getattr(self.db, name)
            def commit(self):
                raise sqlite3.OperationalError('synthetic SQL/path detail')
            def rollback(self):
                self.rolled_back = True
                self.db.rollback()
            def close(self):
                self.closed = True
                self.db.close()
        return FailingCommit

    def test_commit_failure_rolls_back_and_closes(self):
        self.start()
        connections = []
        factory = self.failing_connection()
        def connect(path):
            connection = factory(path)
            connections.append(connection)
            return connection
        with patch.object(self.app, '_connect', side_effect=connect), self.assertRaises(sqlite3.Error):
            with self.app.storage_transaction(write=True) as db:
                db.execute('UPDATE products SET stock=99 WHERE id=1')
        self.assertTrue(connections[0].closed)
        self.assertTrue(connections[0].rolled_back)
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 5)

    def test_read_transactions_cannot_mutate(self):
        self.start()
        with self.assertRaises(sqlite3.OperationalError):
            with self.app.storage_transaction() as db:
                db.execute('UPDATE products SET stock=0')
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 5)

    def test_constraints_rollback_prior_write(self):
        self.start()
        statements = (
            "INSERT INTO cart(session_id,product_id,quantity) VALUES ('s',99999,1)",
            "INSERT INTO cart(session_id,product_id,quantity) VALUES ('s',1,0)",
            "INSERT INTO cart(session_id,product_id,quantity) VALUES ('s',1,1.5)",
            'UPDATE products SET stock=-1 WHERE id=1',
            'UPDATE products SET stock=1.5 WHERE id=1',
            'UPDATE products SET price=-1 WHERE id=1',
            "UPDATE products SET price='not-money' WHERE id=1",
            "UPDATE products SET currency='EUR' WHERE id=1",
            "INSERT INTO categories(name) VALUES ('Books')",
            "INSERT INTO orders(session_id,total) VALUES ('s',-1)",
            "INSERT INTO orders(user_id,session_id,total) VALUES (999,'s',1)",
            "INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES (999,1,1,1)",
        )
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                with self.app.storage_transaction(write=True) as db:
                    db.execute('UPDATE products SET stock=44 WHERE id=2')
                    db.execute(statement)
            self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=2'), 50)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.app.storage_transaction(write=True) as db:
                for _ in range(2):
                    db.execute("INSERT INTO cart(session_id,product_id) VALUES ('s',1)")
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'), 0)

    def test_schema_mismatch_preserves_existing_bytes(self):
        path = Path(self.directory.name) / 'shoplab.sqlite3'
        for variant in ('partial', 'legacy', 'unsupported', 'mismatch', 'corrupt'):
            with TemporaryDirectory() as directory:
                path = Path(directory) / 'shoplab.sqlite3'
                if variant == 'corrupt':
                    path.write_bytes(b'synthetic non-SQLite fixture')
                else:
                    db = self.app._init_db(path) if variant in ('legacy', 'unsupported', 'mismatch') else sqlite3.connect(path)
                    if variant == 'partial':
                        db.execute('CREATE TABLE products(value TEXT)')
                        db.execute("INSERT INTO products VALUES ('preserve')")
                    elif variant == 'legacy':
                        db.execute('PRAGMA user_version=0')
                    elif variant == 'unsupported':
                        db.execute('PRAGMA user_version=99')
                    else:
                        db.execute('ALTER TABLE products ADD COLUMN unexpected TEXT')
                    db.commit()
                    db.close()
                before = path.read_bytes()
                with self.assertRaises(self.app.StorageError):
                    self.app.initialize_storage(directory)
                self.assertEqual(path.read_bytes(), before)
                self.assertIsNone(self.app._database_path)

    def test_schema_rejects_user_objects_with_internal_prefix_lookalike(self):
        for version in (0, 2):
            with self.subTest(version=version), TemporaryDirectory() as directory:
                path = Path(directory) / 'shoplab.sqlite3'
                db = self.app._init_db(path) if version == 2 else sqlite3.connect(path)
                try:
                    db.execute('CREATE TABLE sqliteXfixture(value TEXT)')
                    db.execute("INSERT INTO sqliteXfixture VALUES ('preserve')")
                    db.commit()
                finally:
                    db.close()
                before = path.read_bytes()
                try:
                    with self.assertRaises(self.app.StorageError):
                        self.app.initialize_storage(directory)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertIsNone(self.app._database_path)
                    self.assertFalse(self.app._accepting)
                finally:
                    self.app.close_storage()

    def test_initialization_failure_is_atomic_and_retryable(self):
        with patch.object(self.app, '_SCHEMA', (*self.app._SCHEMA[:2], 'INVALID SQL')):
            with self.assertRaises(self.app.StorageError):
                self.start()
        self.assertIsNone(self.app._database_path)
        db = sqlite3.connect(Path(self.directory.name) / 'shoplab.sqlite3')
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
        finally:
            db.close()
        self.start()
        self.assertEqual(self.scalar('SELECT count(*) FROM products'), 10)

    def test_deterministic_concurrency_and_rollback_isolation(self):
        self.start()
        first_entered, second_attempted, release = (threading.Event() for _ in range(3))
        errors, connections = [], []
        connect = self.app._connect

        class ObserveWriteLock:
            def __init__(self, path):
                self.db = connect(path)
            def __getattr__(self, name):
                return getattr(self.db, name)
            def execute(self, sql, *args):
                if sql == 'BEGIN IMMEDIATE' and threading.current_thread().name == 'second-writer':
                    second_attempted.set()
                return self.db.execute(sql, *args)

        def first():
            try:
                with self.app.storage_transaction(write=True) as db:
                    connections.append(db)
                    db.execute('UPDATE products SET stock=99 WHERE id=1')
                    first_entered.set()
                    if not release.wait(3):
                        raise AssertionError('fixture timeout')
                    raise ValueError('rollback fixture')
            except ValueError:
                pass
            except BaseException as exc:
                errors.append(exc)
        def second():
            try:
                if not first_entered.wait(3):
                    raise AssertionError('fixture timeout')
                with self.app.storage_transaction(write=True) as db:
                    connections.append(db)
                    stock = db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]
                    self.assertEqual(stock, 5)
                    db.execute('UPDATE products SET stock=? WHERE id=1', (stock-1,))
            except BaseException as exc:
                errors.append(exc)
        threads = [threading.Thread(target=first), threading.Thread(target=second, name='second-writer')]
        with patch.object(self.app, '_connect', side_effect=ObserveWriteLock):
            for thread in threads:
                thread.start()
            try:
                self.assertTrue(second_attempted.wait(3))
                # Reader riêng không được thấy stock=99 chưa commit của writer đầu.
                self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 5)
            finally:
                release.set()
                for thread in threads:
                    thread.join(7)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(connections), 2)
        self.assertIsNot(connections[0], connections[1])
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 4)

    def test_busy_failure_is_bounded_and_not_committed(self):
        self.start()
        lock = sqlite3.connect(Path(self.directory.name) / 'shoplab.sqlite3')
        lock.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                with self.app.storage_transaction(write=True):
                    self.fail('Locked mutation được admit')
        finally:
            lock.rollback()
            lock.close()
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 4.5)
        self.assertLess(elapsed, 7)
        self.assertEqual(self.app._active, 0)

    def test_readonly_and_permission_failure_are_safe(self):
        self.start()
        connect = self.app._connect
        def readonly(path):
            db = connect(path)
            db.execute('PRAGMA query_only=ON')
            return db
        handler = self.authorized_handler('/cart/add', b'product_id=1')
        with patch.object(self.app, '_connect', side_effect=readonly):
            handler.do_POST()
        self.assertEqual(handler.responses, [503])
        self.assertNotIn('Set-Cookie', [k for k, _ in handler.sent_headers])
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'), 0)
        self.app.close_storage()
        with patch.object(self.app.os, 'access', return_value=False), self.assertRaises(self.app.StorageError):
            self.start()
        self.assertIsNone(self.app._database_path)

    def test_paths_reject_evidence_bad_types_and_links(self):
        root = Path(self.directory.name)
        for path in (root / 'evidence' / 'data', root / '..' / 'data', ''):
            with self.subTest(path=path), self.assertRaises(self.app.StorageError):
                self.app.initialize_storage(path)
        (root / 'shoplab.sqlite3-wal').mkdir()
        with self.assertRaises(self.app.StorageError):
            self.start()
        with TemporaryDirectory() as directory:
            link = Path(directory) / 'linked'
            try:
                link.symlink_to(root, target_is_directory=True)
            except OSError:
                # Windows không phải account nào cũng được tạo symlink; test reparse bên dưới.
                pass
            else:
                with self.assertRaises(self.app.StorageError):
                    self.app.initialize_storage(link)
        info = SimpleNamespace(st_mode=0o40700, st_file_attributes=0x400)
        with patch.object(Path, 'lstat', return_value=info), self.assertRaises(self.app.StorageError):
            self.app._validate_path(root, directory=True)

    def test_quiesce_drains_and_timeout_never_closes_foreign_connection(self):
        self.start()
        entered, release = threading.Event(), threading.Event()
        errors = []
        def worker():
            try:
                with self.app.storage_transaction(write=True) as db:
                    entered.set()
                    if not release.wait(3):
                        raise AssertionError('fixture timeout')
                    db.execute('UPDATE products SET stock=4 WHERE id=1')
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            with patch.object(self.app, 'DRAIN_SECONDS', .05), self.assertRaises(self.app.StorageError):
                self.app.quiesce_storage()
            with self.assertRaises(self.app.StorageError):
                with self.app.storage_transaction():
                    self.fail('Admission phải đóng')
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.app.close_storage()
        self.start()
        self.assertEqual(self.scalar('SELECT stock FROM products WHERE id=1'), 4)

    def test_http_success_and_cookies_are_withheld_until_commit_cleanup(self):
        self.start()
        token, row = self.guest()
        handler = self.authorized_handler('/cart/add', b'product_id=1&quantity=2', token=token, row=row)
        connect = self.app._connect
        app = self.app
        class ObserveCommit:
            def __init__(self, path):
                self.db = connect(path)
            def __getattr__(self, key):
                return getattr(self.db, key)
            def commit(self):
                self_test.assertEqual(handler.responses, [])
                self.db.commit()
            def close(self):
                self_test.assertEqual(handler.responses, [])
                self.db.close()
        self_test = self
        with patch.object(app, '_connect', side_effect=ObserveCommit):
            handler.do_POST()
        self.assertEqual(handler.responses, [302])
        self.assertEqual(app._active, 0)
        self.assertEqual(self.scalar('SELECT quantity FROM cart'), 2)
        failed = self.authorized_handler('/cart/add', b'product_id=1', token=token, row=row)
        with patch.object(app, '_connect', side_effect=self.failing_connection()):
            failed.do_POST()
        self.assertEqual(failed.responses, [503])
        self.assertNotIn('Set-Cookie', [k for k, _ in failed.sent_headers])
        self.assertNotIn(b'synthetic SQL/path', failed.wfile.getvalue())
        self.assertEqual(self.scalar('SELECT quantity FROM cart'), 2)

    def test_http_constraint_and_registration_rollback(self):
        self.start()
        handler = self.authorized_handler('/cart/add', b'product_id=99999')
        handler.do_POST()
        self.assertEqual(handler.responses, [409])
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'), 0)
        password = secrets.token_urlsafe(24)
        username = 'fixture_' + secrets.token_hex(4)
        for expected in (302, 409):
            handler = self.authorized_handler('/register', urlencode({'username':username, 'email':'fixture@example.invalid', 'password':password}).encode())
            handler.do_POST()
            self.assertEqual(handler.responses, [expected])
            if expected == 409:
                self.assertNotIn('Set-Cookie', [k for k, _ in handler.sent_headers])
        self.assertEqual(self.scalar('SELECT count(*) FROM users'), 1)

    def test_body_is_parsed_before_write_transaction(self):
        self.start()
        handler = self.authorized_handler('/cart/add', b'product_id=1')
        read = handler.rfile.read
        def guarded_read(size):
            self.assertEqual(self.app._active, 0)
            return read(size)
        handler.rfile.read = guarded_read
        handler.do_POST()
        self.assertEqual(handler.responses, [302])
        malformed = self.handler('/cart/add', b'\xff')
        with patch.object(self.app, '_connect', side_effect=AssertionError('Không mở DB')):
            malformed.do_POST()
        self.assertEqual(malformed.responses, [400])

    def test_invoice_write_failure_rolls_back_and_commit_failure_retains_orphan(self):
        self.start()
        token, row = self.guest()
        with self.app.storage_transaction(write=True) as db:
            db.execute('INSERT INTO cart(session_id,product_id,quantity) VALUES (?,1,1)', (row['cart_key'],))
        failed = self.authorized_handler('/checkout', token=token, row=row)
        with patch.object(Path, 'open', side_effect=PermissionError('fixture private path')):
            failed.do_POST()
        self.assertEqual(failed.responses, [503])
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'), 1)
        failed = self.authorized_handler('/checkout', token=token, row=row)
        with patch.object(self.app, '_connect', side_effect=self.failing_connection()):
            failed.do_POST()
        self.assertEqual(failed.responses, [503])
        self.assertEqual(self.scalar('SELECT count(*) FROM orders'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'), 1)
        invoices = list(self.app.UPLOAD_DIR.iterdir())
        self.assertEqual(len(invoices), 1)
        before = invoices[0].read_bytes()
        invoice_id = invoices[0].stem.removeprefix('INV-').lower()
        collided = self.authorized_handler('/checkout', token=token, row=row)
        with patch.object(self.app.uuid, 'uuid4', return_value=SimpleNamespace(hex=invoice_id)):
            collided.do_POST()
        self.assertEqual(collided.responses, [503])
        self.assertEqual(invoices[0].read_bytes(), before)

    def test_reset_remains_refused_and_download_rejects_path_input(self):
        handler = self.handler('/reset')
        handler.do_POST()
        self.assertEqual(handler.responses, [403])
        self.start()
        handler = self.handler('/download/invoice?file=../shoplab.sqlite3')
        handler.do_GET()
        self.assertEqual(handler.responses, [400])

    def test_two_process_restart_preserves_products_orders_without_reseed(self):
        source = '''import json,sys
from pathlib import Path
from types import ModuleType
app=ModuleType('restart_fixture'); app.__file__=sys.argv[1]
exec(compile(Path(sys.argv[1]).read_text(encoding='utf-8'),sys.argv[1],'exec'),app.__dict__)
app.initialize_storage(sys.argv[2])
try:
    if sys.argv[3]=='write':
        with app.storage_transaction(write=True) as db:
            db.execute('UPDATE products SET stock=3 WHERE id=1')
            cur=db.execute("INSERT INTO orders(session_id,total) VALUES ('synthetic',12.5)")
            db.execute('INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES (?,1,1,12.5)',(cur.lastrowid,))
    with app.storage_transaction() as db:
        print(json.dumps({'stock':db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],
        'products':db.execute('SELECT count(*) FROM products').fetchone()[0],
        'orders':db.execute('SELECT count(*) FROM orders').fetchone()[0],
        'total':db.execute('SELECT total FROM orders').fetchone()[0],
        'items':[list(row) for row in db.execute('SELECT order_id,product_id,quantity,unit_price FROM order_items ORDER BY id')],
        'users':db.execute('SELECT count(*) FROM users').fetchone()[0]}))
finally:
    app.close_storage()
'''
        results = []
        for mode in ('write', 'read'):
            result = subprocess.run([sys.executable, '-I', '-B', '-c', source, str(APP_PATH), self.directory.name, mode], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            results.append(json.loads(result.stdout))
        self.assertEqual(results, [{'stock':3, 'products':10, 'orders':1, 'total':12.5,
                                    'items':[[1,1,1,12.5]], 'users':0}]*2)


if __name__ == '__main__':
    unittest.main()
