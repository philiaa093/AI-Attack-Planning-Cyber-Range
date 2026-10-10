"""SL-03: auth/authorization offline, SQLite temp, không sockets hoặc secrets logs."""
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
from test_gateway_product import load_gateway


class ShopLabAuthTests(unittest.TestCase):
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
        fields = {'username':'user_' + secrets.token_hex(4), 'password':secrets.token_urlsafe(24), 'email':'fixture@example.invalid'}
        h = self.request('/register', 'POST', fields, token, row['csrf_secret'])
        self.assertEqual(h.responses, [302])
        new = self.cookie(h)
        return fields, new, self.identity(new)

    def snapshot(self):
        with self.app.storage_transaction() as db:
            state = tuple(db.iterdump())
        files = {p.name:p.read_bytes() for p in self.app.UPLOAD_DIR.iterdir()}
        return state, files

    def test_A01_register_login_logout_duplicate_and_cookie_flags(self):
        fields, token, row = self.account()
        self.assertEqual(row['role'], 'user')
        old = token
        before = self.snapshot()
        h = self.request('/logout', token=token)
        self.assertEqual(h.responses, [405])
        self.assertEqual(self.snapshot(), before)
        h = self.request('/logout', 'POST', token=token, csrf=row['csrf_secret'])
        self.assertEqual(h.responses, [302])
        self.assertIsNone(self.identity(old))
        token, row = self.guest()
        h = self.request('/login', 'POST', fields, token, row['csrf_secret'])
        self.assertEqual(h.responses, [302])
        value = next(v for k,v in h.sent_headers if k=='Set-Cookie' and v.startswith('session='))
        for flag in ('HttpOnly','SameSite=Lax','Path=/','Max-Age=28800'):
            self.assertIn(flag,value)
        self.assertNotIn('Secure',value)
        self.assertIn(('Cache-Control','no-store'),h.sent_headers)
        self.assertIsNone(self.identity(token))
        t,s = self.guest()
        h = self.request('/register','POST',fields,t,s['csrf_secret'])
        self.assertEqual(h.responses,[409])
        self.assertFalse(self.cookie(h))
        self.assertEqual(self.scalar('SELECT count(*) FROM users'),1)

    def test_A02_client_identity_and_admin_denied(self):
        fields,t,row=self.account()
        for token in ('',t,fields['username']):
            h=self.request('/admin',token=token,headers=[('Cookie','role=admin; username='+fields['username'])] if not token else [])
            self.assertEqual(h.responses,[403])
        h=self.request('/admin',token=t,headers=[('Cookie','role=admin')])
        self.assertEqual(h.responses,[400])
        h=self.request('/admin',headers=[('Cookie','session='+t+'; role=admin; username=other')])
        self.assertEqual(h.responses,[403])
        self.assertEqual(self.scalar("SELECT count(*) FROM users WHERE role='admin'"),0)

    def test_A03_invalid_sessions_and_no_raw_cart_fallback(self):
        t,s=self.guest()
        with self.app.storage_transaction(write=True) as db:
            db.execute("INSERT INTO cart(session_id,product_id,quantity) VALUES ('raw_identity',1,1)")
        for token in ('raw_identity',secrets.token_hex(32),t):
            with patch.object(self.app,'_now',return_value=s['expires_at'] if token==t else s['issued_at']):
                before=self.snapshot()
                h=self.request('/cart/add','POST',{'product_id':1},token,s['csrf_secret'])
                self.assertEqual(h.responses,[403])
                self.assertEqual(self.snapshot(),before)
        h=self.request('/orders',headers=[('Cookie','session='+t+'; session='+t)])
        self.assertEqual(h.responses,[400])
        h=self.request('/orders',headers=[('Cookie','session='+t),('Cookie','role=admin')])
        self.assertEqual(h.responses,[400])
        self.assertEqual(self.scalar('SELECT count(*) FROM cart'),1)

    def test_A04_every_mutation_csrf_rejects_without_writes(self):
        fields,t,s=self.account()
        foreign,fs=self.guest()
        routes=['/login','/register','/logout','/cart/add','/cart/remove','/checkout','/reviews']
        for route in routes:
            for csrf in (None,secrets.token_hex(32),fs['csrf_secret']):
                with self.subTest(route=route,csrf_case='missing' if csrf is None else 'foreign'):
                    before=self.snapshot()
                    h=self.request(route,'POST',{'product_id':1,'quantity':1,'cart_id':1,**fields},t,csrf)
                    self.assertEqual(h.responses,[403])
                    self.assertEqual(self.snapshot(),before)
                    self.assertFalse(self.cookie(h))
        before=self.snapshot()
        h=self.request('/reviews','POST',{'product_id':1,'rating':3,'body':'text'},foreign,fs['csrf_secret'])
        self.assertEqual(h.responses,[403])
        self.assertEqual(self.snapshot(),before)

    def test_A04_ambiguous_input_and_encoding_rejected(self):
        t,s=self.guest()
        cases=[({'raw':b'product_id=1&product_id=2'},400),({'raw':b'product_id=%GG'},400),({'raw':b'product_id=%FF'},400),
               ({'headers':[('X-CSRF-Token',s['csrf_secret'])]},400),
               ({'fields':{'product_id':1,'csrf_token':secrets.token_hex(32)}},403)]
        for overrides,status in cases:
            before=self.snapshot()
            args=dict(fields={'product_id':1},token=t,csrf=s['csrf_secret']);args.update(overrides)
            h=self.request('/cart/add','POST',**args)
            self.assertEqual(h.responses,[status])
            self.assertEqual(self.snapshot(),before)

    def test_A05_rotation_guest_merge_shared_cart_and_switch(self):
        a,at,ai=self.account();b,bt,bi=self.account()
        gt,gi=self.guest()
        self.assertEqual(self.request('/cart/add','POST',{'product_id':1,'quantity':2},gt,gi['csrf_secret']).responses,[302])
        h=self.request('/login','POST',a,gt,gi['csrf_secret']);self.assertEqual(h.responses,[302])
        new=self.cookie(h);ni=self.identity(new)
        self.assertIsNone(self.identity(gt));self.assertNotEqual(ni['csrf_secret'],gi['csrf_secret'])
        self.assertEqual(ni['cart_key'],ai['cart_key'])
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE session_id=?',(ai['cart_key'],)),2)
        before=self.snapshot()
        self.assertEqual(self.request('/logout','POST',token=new,csrf=gi['csrf_secret']).responses,[403])
        self.assertEqual(self.snapshot(),before)
        h=self.request('/login','POST',b,new,ni['csrf_secret']);self.assertEqual(h.responses,[302])
        self.assertEqual(self.identity(self.cookie(h))['cart_key'],bi['cart_key'])
        self.assertEqual(self.scalar('SELECT count(*) FROM cart WHERE session_id=?',(bi['cart_key'],)),0)
        self.assertEqual(self.scalar('SELECT quantity FROM cart WHERE session_id=?',(ai['cart_key'],)),2)

    def test_A05_merge_limit_failure_rolls_back_login(self):
        a,at,ai=self.account();gt,gi=self.guest()
        with self.app.storage_transaction(write=True) as db:
            db.execute('INSERT INTO cart(session_id,product_id,quantity) VALUES (?,1,5)',(ai['cart_key'],))
            db.execute('INSERT INTO cart(session_id,product_id,quantity) VALUES (?,1,1)',(gi['cart_key'],))
        before=self.snapshot()
        h=self.request('/login','POST',a,gt,gi['csrf_secret'])
        self.assertEqual(h.responses,[400]);self.assertEqual(self.snapshot(),before)
        self.assertIsNotNone(self.identity(gt));self.assertFalse(self.cookie(h))

    def order(self,row,guest=False):
        name='INV-'+secrets.token_hex(16).upper()+'.txt'
        with self.app.storage_transaction(write=True) as db:
            cur=db.execute('INSERT INTO orders(user_id,session_id,total,invoice_file) VALUES (?,?,10,?)',
                           (None if guest else row['user_id'],row['cart_key'],name))
            oid=cur.lastrowid
        (self.app.UPLOAD_DIR/name).write_text('Lab invoice fixture',encoding='utf-8')
        return oid,name

    def test_A06_owner_guest_and_api_projection(self):
        a,at,ai=self.account();b,bt,bi=self.account();gt,gi=self.guest()
        oid,name=self.order(ai);gid,gname=self.order(gi,True)
        for token,status in ((at,200),(bt,404),(gt,404),('',404)):
            h=self.request('/api/orders/'+str(oid),token=token)
            self.assertEqual(h.responses,[status])
            if status==200:
                data=json.loads(h.wfile.getvalue())
                self.assertNotIn('session_id',data['order']);self.assertNotIn('user_id',data['order'])
            if status!=200:
                with patch.object(Path,'read_text',side_effect=AssertionError('Không đọc invoice denied')):
                    self.assertEqual(self.request('/download/invoice?file='+name,token=token).responses,[404])
        self.assertEqual(self.request('/download/invoice?file='+name,token=at).responses,[200])
        self.assertEqual(self.request('/api/orders/'+str(gid),token=gt).responses,[200])
        h=self.request('/login','POST',a,gt,gi['csrf_secret']);nt=self.cookie(h)
        self.assertEqual(self.request('/api/orders/'+str(gid),token=nt).responses,[404])
        self.assertIsNone(self.scalar('SELECT user_id FROM orders WHERE id=?',(gid,)))
        # user_id có ưu tiên cao hơn matching cart association.
        with self.app.storage_transaction(write=True) as db:
            db.execute('UPDATE orders SET session_id=? WHERE id=?',(bi['cart_key'],oid))
        self.assertEqual(self.request('/api/orders/'+str(oid),token=bt).responses,[404])

    def test_A07_password_metadata_salts_validation_and_dummy_work(self):
        password=secrets.token_urlsafe(24)
        one,two=self.app._hash(password),self.app._hash(password)
        self.assertNotEqual(one,two)
        self.assertTrue(self.app._verify_password(password,one))
        self.assertFalse(self.app._verify_password(password,None))
        self.assertFalse(self.app._verify_password(password,hashlib.sha256(password.encode()).hexdigest()))
        self.assertNotIn(password,one)
        for value in ('short','a'*129):
            with self.assertRaises(ValueError):self.app._hash(value)
        for fields in ({'username':'ab','password':password,'email':'a@b'},
                       {'username':'user_ok','password':'short','email':'a@b'},
                       {'username':'user_ok','password':password,'email':'bad'}):
            t,s=self.guest();before=self.snapshot()
            self.assertEqual(self.request('/register','POST',fields,t,s['csrf_secret']).responses,[400])
            self.assertEqual(self.snapshot(),before)
        real=self.app.hashlib.pbkdf2_hmac
        with patch.object(self.app.hashlib,'pbkdf2_hmac',wraps=real) as kdf:
            self.app._verify_password(password,'pbkdf2_sha256$1$99999999$bad$bad')
            self.assertEqual(kdf.call_args.args[3],600000)

    def test_A07_throttle_persistence_window_and_cookie_renewal(self):
        fields,t,s=self.account()
        wrong={**fields,'password':secrets.token_urlsafe(24)}
        with patch.object(self.app,'_now',return_value=s['issued_at']):
            for _ in range(4):
                self.assertEqual(self.request('/login','POST',wrong,t,s['csrf_secret']).responses,[403])
            self.assertEqual(self.request('/login','POST',wrong,t,s['csrf_secret']).responses,[429])
            nt,ns=self.guest()
            self.assertEqual(self.request('/login','POST',wrong,nt,ns['csrf_secret']).responses,[429])
        counters=self.scalar('SELECT sum(attempts) FROM auth_limits')
        self.app.close_storage();self.app.initialize_storage(self.temp.name)
        self.assertEqual(self.scalar('SELECT sum(attempts) FROM auth_limits'),counters)
        with patch.object(self.app,'_now',return_value=s['issued_at']+300):
            self.assertEqual(self.request('/login','POST',wrong,t,s['csrf_secret']).responses,[403])

    def test_A07_generic_login_failures_no_business_changes(self):
        fields,t,s=self.account()
        messages=[]
        for username in (fields['username'],'missing_'+secrets.token_hex(3)):
            before=self.scalar('SELECT count(*) FROM sessions')
            h=self.request('/login','POST',{'username':username,'password':secrets.token_urlsafe(24)},t,s['csrf_secret'])
            messages.append((h.responses,h.wfile.getvalue()))
            self.assertEqual(self.scalar('SELECT count(*) FROM sessions'),before)
            self.assertFalse(self.cookie(h))
        self.assertEqual(messages[0],messages[1])

    def test_A07_absolute_expiry_no_get_refresh_or_api_bootstrap(self):
        t,s=self.guest();before=self.snapshot()
        self.request('/products',token=t)
        self.assertEqual(self.snapshot(),before)
        for path in ('/health','/api/products','/api/orders/1','/orders','/admin','/download/invoice?file=INV-'+('A'*32)+'.txt'):
            before=self.snapshot();h=self.request(path)
            self.assertEqual(self.snapshot(),before);self.assertFalse(self.cookie(h))
        with patch.object(self.app,'_now',return_value=s['expires_at']):
            self.assertIsNone(self.identity(t))
        self.assertEqual(s['expires_at']-s['issued_at'],3600)
        _,at,ai=self.account();self.assertEqual(ai['expires_at']-ai['issued_at'],28800)

    def test_A07_session_capacity_user_limit_replacement_and_prune(self):
        fields,t,s=self.account()
        with patch.object(self.app,'MAX_USER_SESSIONS',1):
            gt,gs=self.guest()
            before=self.snapshot()
            self.assertEqual(self.request('/login','POST',fields,gt,gs['csrf_secret']).responses,[503])
            self.assertEqual(self.snapshot(),before)
            h=self.request('/login','POST',fields,t,s['csrf_secret'])
            self.assertEqual(h.responses,[302])
        with patch.object(self.app,'MAX_SESSIONS',self.scalar('SELECT count(*) FROM sessions')):
            self.assertEqual(self.request('/login').responses,[503])
        with self.app.storage_transaction(write=True) as db:
            for _ in range(70):
                db.execute('INSERT INTO sessions VALUES (?,NULL,?,1,2,?)',(secrets.token_hex(32),secrets.token_hex(32),secrets.token_hex(32)))
            self.app.create_session(db)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE expires_at=2').fetchone()[0],6)

    def test_A07_throttle_global_capacity_and_prune(self):
        t,s=self.guest()
        with self.app.storage_transaction(write=True) as db:
            db.execute('INSERT INTO auth_limits VALUES (?,?,100)',('global',self.app._now()))
        before=self.snapshot()
        fields={'username':'unknown_user','password':secrets.token_urlsafe(24)}
        self.assertEqual(self.request('/login','POST',fields,t,s['csrf_secret']).responses,[429])
        self.assertEqual(self.snapshot(),before)
        with self.app.storage_transaction(write=True) as db:
            db.execute('DELETE FROM auth_limits')
            for n in range(70):db.execute('INSERT INTO auth_limits VALUES (?,0,1)',('old'+str(n),))
            self.assertTrue(self.app._auth_attempt(db,s,'unknown_user'))
            self.assertEqual(db.execute("SELECT count(*) FROM auth_limits WHERE bucket LIKE 'old%'").fetchone()[0],6)
        with self.app.storage_transaction(write=True) as db:
            db.execute("UPDATE auth_limits SET started_at=? WHERE bucket LIKE 'old%'",(self.app._now(),))
        with patch.object(self.app,'MAX_BUCKETS',self.scalar('SELECT count(*) FROM auth_limits')):
            self.assertEqual(self.request('/login','POST',{'username':'different_user','password':fields['password']},t,s['csrf_secret']).responses,[429])

    def test_admin_closed_only_promote_revoke_invalidate_audit(self):
        fields,t,s=self.account()
        with self.assertRaises(self.app.StorageError):self.app.set_local_role(self.temp.name,s['user_id'],'admin')
        self.app.close_storage()
        self.app.set_local_role(self.temp.name,s['user_id'],'admin')
        self.app.initialize_storage(self.temp.name)
        self.assertIsNone(self.identity(t))
        gt,gs=self.guest();h=self.request('/login','POST',fields,gt,gs['csrf_secret']);at=self.cookie(h)
        self.assertEqual(self.request('/admin',token=at).responses,[200])
        self.assertEqual(self.scalar('SELECT count(*) FROM admin_audit'),1)
        self.app.close_storage();self.app.set_local_role(self.temp.name,s['user_id'],'user');self.app.initialize_storage(self.temp.name)
        self.assertIsNone(self.identity(at));self.assertEqual(self.scalar('SELECT count(*) FROM admin_audit'),2)
        with self.app.storage_transaction() as db:
            audit=' '.join(str(tuple(r)) for r in db.execute('SELECT * FROM admin_audit'))
        for secret in (fields['password'],t,at,s['csrf_secret'],fields['email'],fields['username']):self.assertNotIn(secret,audit)

    def test_admin_missing_unknown_and_audit_failure_rollback(self):
        fields,t,s=self.account();self.app.close_storage()
        path=Path(self.temp.name)/'shoplab.sqlite3';before=path.read_bytes()
        with self.assertRaises(ValueError):self.app.set_local_role(self.temp.name,999999,'admin')
        self.assertEqual(path.read_bytes(),before)
        connect=self.app._connect
        class AuditFail:
            def __init__(self,p):self.db=connect(p)
            def __getattr__(self,k):return getattr(self.db,k)
            def execute(self,sql,*args):
                if sql.startswith('INSERT INTO admin_audit'):raise sqlite3.OperationalError('fixture audit failure')
                return self.db.execute(sql,*args)
        with patch.object(self.app,'_connect',side_effect=AuditFail),self.assertRaises(sqlite3.OperationalError):
            self.app.set_local_role(self.temp.name,s['user_id'],'admin')
        self.app.initialize_storage(self.temp.name)
        self.assertIsNotNone(self.identity(t));self.assertEqual(self.scalar('SELECT role FROM users'),'user')
        self.assertEqual(self.scalar('SELECT count(*) FROM admin_audit'),0)
        self.app.close_storage()
        with TemporaryDirectory() as directory:
            with self.assertRaises(self.app.StorageError):self.app.set_local_role(directory,1,'admin')
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_admin_lifecycle_lock_prevents_concurrent_initialize(self):
        fields,t,s=self.account();self.app.close_storage()
        entered,release=threading.Event(),threading.Event();errors=[]
        original=self.app._preflight_db
        def blocked(path,**kwargs):
            if kwargs.get('required'):
                entered.set();release.wait(5)
            return original(path,**kwargs)
        def promote():
            try:self.app.set_local_role(self.temp.name,s['user_id'],'admin')
            except BaseException as exc:errors.append(type(exc).__name__)
        with patch.object(self.app,'_preflight_db',side_effect=blocked):
            worker=threading.Thread(target=promote);worker.start()
            self.assertTrue(entered.wait(5))
            self.assertFalse(self.app._condition.acquire(blocking=False))
            release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
        self.app.initialize_storage(self.temp.name)
        self.assertEqual(self.scalar('SELECT role FROM users'),'admin')

    def test_real_legacy_v1_rejected_before_any_writes(self):
        # Fixture v1 exact từ baseline schema đã được kiểm chứng SL-02, không đổi version v2 giả.
        legacy = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user'
        );
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL NOT NULL CHECK(typeof(price) IN ('integer', 'real') AND price >= 0),
            currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
            category_id INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 10 CHECK(typeof(stock) = 'integer' AND stock >= 0),
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );
        CREATE TABLE cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(typeof(quantity) = 'integer' AND quantity > 0),
            UNIQUE(session_id, product_id)
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            session_id TEXT NOT NULL,
            total REAL NOT NULL CHECK(typeof(total) IN ('integer', 'real') AND total >= 0),
            currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
            status TEXT DEFAULT 'pending',
            invoice_file TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL CHECK(typeof(quantity) = 'integer' AND quantity > 0),
            unit_price REAL NOT NULL CHECK(typeof(unit_price) IN ('integer', 'real') AND unit_price >= 0),
            currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
            UNIQUE(order_id, product_id)
        );
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            user_id INTEGER REFERENCES users(id),
            username TEXT,
            rating INTEGER,
            body TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO categories(name) VALUES ('Lab fixture');
        INSERT INTO products(name,price,category_id,stock) VALUES ('Lab fixture',1,1,2);
        """
        for sidecars in (False,True):
            with TemporaryDirectory() as directory:
                root=Path(directory);p=root/'shoplab.sqlite3';db=sqlite3.connect(p)
                db.executescript(legacy);db.execute('PRAGMA user_version=1');db.execute('UPDATE products SET stock=2 WHERE id=1');db.commit();db.close()
                if sidecars:(root/'shoplab.sqlite3-wal').write_bytes(b'fixture preserved sidecar')
                before={f.name:f.read_bytes() for f in root.iterdir()}
                with self.assertRaises(self.app.StorageError):self.app._init_db(p)
                other=load_app()
                with self.assertRaises(other.StorageError):other.initialize_storage(directory)
                self.assertEqual({f.name:f.read_bytes() for f in root.iterdir()},before)
                self.assertIsNone(other._database_path)

    def test_stored_review_and_titles_escaped_without_payload(self):
        fields,t,s=self.account();text='Lab <note> & "quotation"'
        h=self.request('/reviews','POST',{'product_id':1,'rating':3,'body':text},t,s['csrf_secret'])
        self.assertEqual(h.responses,[302])
        h=self.request('/products/1',token=t);output=h.wfile.getvalue().decode()
        self.assertIn('Lab &lt;note&gt; &amp; &quot;quotation&quot;',output)
        self.assertNotIn(text,output)
        self.assertIn('&lt;title&gt;',self.app._render('<title>','text'))

    def test_admin_customer_endpoints_stay_owner_only_and_redundant_role_is_noop(self):
        fields,t,s=self.account();other,ot,os=self.account()
        oid,name=self.order(os)
        self.app.close_storage();self.app.set_local_role(self.temp.name,s['user_id'],'admin')
        self.app.initialize_storage(self.temp.name)
        gt,gs=self.guest()
        h=self.request('/login','POST',fields,gt,gs['csrf_secret']);at=self.cookie(h)
        self.assertEqual(self.request('/admin',token=at).responses,[200])
        before=self.snapshot()
        self.assertEqual(self.request('/api/orders/'+str(oid),token=at).responses,[404])
        with patch.object(Path,'read_text',side_effect=AssertionError('Không đọc invoice denied')):
            self.assertEqual(self.request('/download/invoice?file='+name,token=at).responses,[404])
        self.assertEqual(self.snapshot(),before)
        self.app.quiesce_storage()
        with self.assertRaises(self.app.StorageError):
            self.app.set_local_role(self.temp.name,s['user_id'],'user')
        self.app.close_storage();self.app.set_local_role(self.temp.name,s['user_id'],'admin')
        self.app.initialize_storage(self.temp.name)
        self.assertEqual(self.snapshot(),before)
        self.assertIsNotNone(self.identity(at))

    def test_csrf_forms_digest_storage_and_replay_on_every_mutation(self):
        fields,t,s=self.account()
        self.request('/cart/add','POST',{'product_id':1,'quantity':1},t,s['csrf_secret'])
        for path in ('/','/products','/products/1','/cart','/login','/register'):
            h=self.request(path,token=t)
            self.assertIn("name='csrf_token'",h.wfile.getvalue().decode())
            self.assertIn(s['csrf_secret'],h.wfile.getvalue().decode())
        self.assertNotIn(t,str(self.snapshot()[0]))
        self.assertEqual(s['token_digest'],hashlib.sha256(t.encode()).hexdigest())
        self.assertNotEqual(s['cart_key'],t)
        # Hidden form token là đường dùng của browser, không chỉ custom header.
        h=self.request('/cart/remove','POST',{'cart_id':999999,'csrf_token':s['csrf_secret']},t)
        self.assertEqual(h.responses,[302])
        h=self.request('/login','POST',fields,t,s['csrf_secret']);new=self.cookie(h)
        for route in ('/login','/register','/logout','/cart/add','/cart/remove','/checkout','/reviews'):
            before=self.snapshot()
            for token in (t,new):
                h=self.request(route,'POST',fields,token,s['csrf_secret'])
                self.assertEqual(h.responses,[403]);self.assertFalse(self.cookie(h))
            self.assertEqual(self.snapshot(),before)

    def test_identifier_bounds_and_query_rejection_preserve_state(self):
        t,s=self.guest()
        for value in ('9223372036854775808', '0', '-1', '01', '１２'):
            with self.assertRaises(ValueError):
                self.app._positive_id(value)
            before=self.snapshot()
            for route,field in (('/cart/add','product_id'),('/cart/remove','cart_id')):
                h=self.request(route,'POST',{field:value},t,s['csrf_secret'])
                self.assertEqual(h.responses,[400])
            for prefix in ('/products/','/api/orders/'):
                self.assertEqual(self.request(prefix+value,token=t).responses,[400])
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.app._positive_id('9223372036854775807'),9223372036854775807)
        for query in ('q=one&q=two','q=%GG','q=%FF','q='+('a'*8193),'&'.join('k'+str(n)+'=x' for n in range(31))):
            before=self.snapshot()
            h=self.request('/products?'+query)
            self.assertEqual(h.responses,[400]);self.assertFalse(self.cookie(h))
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.request('/products?q=',token=t).responses,[200])

    def test_auth_success_cookie_withheld_on_commit_failure(self):
        t,s=self.guest();fields={'username':'user_'+secrets.token_hex(4),'password':secrets.token_urlsafe(24),'email':'fixture@example.invalid'}
        connect=self.app._connect
        class CommitFail:
            def __init__(self,p):self.db=connect(p)
            def __getattr__(self,k):return getattr(self.db,k)
            def commit(self):raise sqlite3.OperationalError('fixture commit failure')
        with patch.object(self.app,'_connect',side_effect=CommitFail):h=self.request('/register','POST',fields,t,s['csrf_secret'])
        self.assertEqual(h.responses,[503]);self.assertFalse(self.cookie(h));self.assertEqual(self.scalar('SELECT count(*) FROM users'),0)
        self.assertIsNotNone(self.identity(t))

    def test_A08_mock_gateway_actual_handler_business_cookie_flow(self):
        gateway=load_gateway();jar={}
        class Connection:
            def __init__(self,*args,**kwargs):self.response=None
            def request(conn,method,path,body=None,headers=None):
                h=object.__new__(self.app.Handler);h.path=path;h.headers=Message()
                for k,v in (headers or {}).items():h.headers[k]=v
                h.headers['Content-Length']=str(len(body or b''));h.rfile=io.BytesIO(body or b'');h.wfile=io.BytesIO()
                h.responses=[];h.sent_headers=[];h.send_response=h.responses.append
                h.send_header=lambda k,v:h.sent_headers.append((k,v));h.end_headers=lambda:None
                getattr(h,'do_'+method)();conn.response=h
            def getresponse(conn):
                h=conn.response
                return type('Response',(),{'status':h.responses[0],'read':lambda _,n:h.wfile.getvalue(),'getheaders':lambda _:h.sent_headers})()
            def close(self):pass
        def proxy(path,method='GET',fields=None,csrf=None):
            g=object.__new__(gateway.Gateway);g.path=path;g.command=method;g.headers=Message()
            body=urlencode(fields or {}).encode();g.headers['Content-Length']=str(len(body))
            g.headers['Cookie']='; '.join(k+'='+v for k,v in jar.items())
            if csrf:g.headers['X-CSRF-Token']=csrf
            g.rfile=io.BytesIO(body);g.wfile=io.BytesIO();g.connection=Mock();g.responses=[];g.sent_headers=[]
            g.send_response=g.responses.append;g.send_header=lambda k,v:g.sent_headers.append((k,v));g.end_headers=lambda:None
            g.send_error=lambda status,*_:g.responses.append(status)
            with patch.object(gateway,'HTTPConnection',Connection), patch.object(gateway,'TARGET_HOST','lab-ecommerce'):
                g._proxy()
            for k,v in g.sent_headers:
                if k=='Set-Cookie':
                    name,value=v.split(';')[0].split('=',1)
                    if value:jar[name]=value
                    else:jar.pop(name,None)
            return g
        g=proxy('/register');self.assertEqual(g.responses,[200])
        csrf=self.identity(jar['session'])['csrf_secret']
        fields={'username':'gateway_'+secrets.token_hex(3),'password':secrets.token_urlsafe(24),'email':'fixture@example.invalid'}
        g=proxy('/register','POST',fields,csrf);self.assertEqual(g.responses,[302])
        self.assertEqual(sum(k=='Set-Cookie' for k,v in g.sent_headers),3)
        csrf=self.identity(jar['session'])['csrf_secret']
        self.assertEqual(proxy('/cart/add','POST',{'product_id':1,'quantity':1},csrf).responses,[302])
        self.assertEqual(proxy('/checkout','POST',{'full_name':'Lab fixture','address':'Lab fixture','email':'fixture@example.invalid'},csrf).responses,[200])
        oid=self.scalar('SELECT id FROM orders');name=self.scalar('SELECT invoice_file FROM orders')
        self.assertEqual(proxy('/api/orders/'+str(oid)).responses,[200])
        self.assertEqual(proxy('/download/invoice?file='+name).responses,[200])
        self.assertEqual(proxy('/reviews','POST',{'product_id':1,'rating':4,'body':'Lab fixture'},csrf).responses,[302])
        old=jar['session'];self.assertEqual(proxy('/logout','POST',{},csrf).responses,[302]);self.assertIsNone(self.identity(old))
        self.assertNotIn('session',jar)
