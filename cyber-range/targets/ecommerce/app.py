"""ShopLab — ứng dụng sản phẩm đang được hoàn thiện trong cyber range cô lập.

Kho SQLite chỉ được mở qua initialize_storage(), không có import side effects.
Tìm kiếm/lọc dùng SQL parameters; dữ liệu mẫu không chứa tài khoản cố định.
Thanh toán/email chỉ là mô phỏng, không kết nối dịch vụ thật.

Chưa hoàn thiện xác thực, phân quyền, transaction checkout và quản trị.
Không triển khai ngoài lab hoặc dùng dữ liệu thực. Các luồng cũ chưa được
kiểm chứng và không phải bằng chứng một cuộc pentest đã hoàn thành.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, sqlite3, uuid
import stat, threading, time, re, secrets, hmac
from datetime import datetime, timezone
from contextlib import contextmanager
from functools import wraps
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, urlencode

PORT = int(os.environ.get("PORT", "8080"))
TARGET_ID = os.environ.get("TARGET_ID", "lab-ecommerce")
DATA_DIR = pathlib.Path(os.environ.get("SHOPLAB_DATA_DIR", "/app/data"))
UPLOAD_DIR = DATA_DIR / "invoices"
_condition = threading.Condition()
_database_path: pathlib.Path | None = None
_accepting = False
_active = 0
BUSY_SECONDS = 5.0
DRAIN_SECONDS = 5.0

# Khai báo thuần dữ liệu; import không mở connection hoặc truy cập filesystem.
_SCHEMA_SCRIPT = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
            cart_key TEXT UNIQUE NOT NULL
        );
        CREATE TABLE sessions (
            token_digest TEXT PRIMARY KEY CHECK(length(token_digest)=64),
            user_id INTEGER REFERENCES users(id),
            cart_key TEXT NOT NULL,
            issued_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL CHECK(expires_at > issued_at),
            csrf_secret TEXT NOT NULL CHECK(length(csrf_secret)=64)
        );
        CREATE TABLE auth_limits (
            bucket TEXT PRIMARY KEY,
            started_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL CHECK(attempts > 0)
        );
        CREATE TABLE admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL CHECK(action IN ('promote','revoke')),
            user_id INTEGER NOT NULL REFERENCES users(id),
            old_role TEXT NOT NULL,
            new_role TEXT NOT NULL,
            created_at TEXT NOT NULL
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
        -- Seed data
        -- Không tạo tài khoản hoặc mật khẩu cố định trong dữ liệu mẫu.
        INSERT INTO categories (name) VALUES ('Electronics'), ('Books'), ('Clothing'), ('Home & Garden');
        INSERT INTO products (name, description, price, category_id, stock) VALUES
            ('Laptop Pro 15', 'High-performance laptop with 16GB RAM and 512GB SSD', 1299.99, 1, 5),
            ('Wireless Mouse', 'Ergonomic wireless mouse, 2.4GHz, 1600 DPI', 29.99, 1, 50),
            ('USB-C Hub 7-in-1', 'USB-C hub with HDMI, 3x USB-A, SD, MicroSD, PD charging', 49.99, 1, 30),
            ('Python Mastery', 'Complete guide to Python 3.11 programming', 39.99, 2, 20),
            ('Clean Code', 'A Handbook of Agile Software Craftsmanship', 34.99, 2, 15),
            ('Cotton T-Shirt (M)', 'Premium 100% organic cotton t-shirt, medium', 19.99, 3, 100),
            ('Denim Jacket', 'Classic slim-fit denim jacket, blue', 89.99, 3, 25),
            ('Plant Pot 20cm', 'Ceramic plant pot, matte white, with drainage hole', 12.99, 4, 60),
            ('Garden Trowel', 'Stainless steel hand trowel with ergonomic grip', 8.99, 4, 40),
            ('Smart LED Bulb', 'WiFi-enabled RGB LED bulb, E27, 9W, app-controlled', 15.99, 1, 80);
"""
# Tách từng statement: executescript có thể implicit-commit transaction.
_SCHEMA = tuple(s.strip() for s in _SCHEMA_SCRIPT.split(';') if s.strip())


class StorageError(RuntimeError):
    """Lỗi storage với thông điệp an toàn, không chứa SQL/path."""


def _validate_path(path: pathlib.Path, *, directory: bool) -> None:
    """Boundary giả định parent do app quản lý; không chống concurrent replacement."""
    if any(part.casefold() == 'evidence' for part in path.parts):
        raise StorageError('Storage path is not permitted')
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise StorageError('Storage links are not permitted')
        expected_dir = component != path or directory
        if not (stat.S_ISDIR(info.st_mode) if expected_dir else stat.S_ISREG(info.st_mode)):
            raise StorageError('Invalid storage object')


def _validate_storage(directory: pathlib.Path) -> None:
    _validate_path(directory, directory=True)
    _validate_path(directory / 'invoices', directory=True)
    for suffix in ('', '-journal', '-wal', '-shm'):
        _validate_path(directory / ('shoplab.sqlite3' + suffix), directory=False)


def _connect(path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=BUSY_SECONDS, isolation_level=None)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        db.execute(f'PRAGMA busy_timeout = {int(BUSY_SECONDS * 1000)}')
        return db
    except BaseException:
        db.close()
        raise


def _schema_snapshot(db) -> tuple:
    # sqlite_master SQL bao gồm CHECK/UNIQUE/FK/defaults; không chỉ xét products.
    return tuple(tuple(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name"))


def _create_schema(db) -> None:
    for statement in _SCHEMA:
        db.execute(statement)
    db.execute('PRAGMA user_version = 2')


def _preflight_db(database_path, *, required=False) -> None:
    """Chỉ kiểm tra DB quiescent bằng read-only; không recovery/migration."""
    if str(database_path) == ':memory:':
        return
    path = pathlib.Path(database_path)
    if not path.is_file():
        if required:
            raise StorageError('Existing storage is required')
        return
    for suffix in ('-journal', '-wal', '-shm'):
        if pathlib.Path(str(path) + suffix).exists():
            raise StorageError('Storage recovery requires a separate workflow')
    db = sqlite3.connect(path.absolute().as_uri() + '?mode=ro&immutable=1', uri=True)
    reference = None
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        objects = _schema_snapshot(db)
        if not required and version == 0 and not objects:
            return
        reference = _connect(':memory:')
        _create_schema(reference)
        if version != 2 or objects != _schema_snapshot(reference):
            raise StorageError('Unsupported storage schema')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise StorageError('Invalid storage data')
    finally:
        db.close()
        if reference is not None:
            reference.close()


def _init_db(database_path: str | pathlib.Path = ':memory:') -> sqlite3.Connection:
    """Atomic schema/catalog; schema cũ không được migrate hoặc reseed."""
    _preflight_db(database_path)
    db = _connect(database_path)
    try:
        # Kiểm tra read-only trước write transaction để không đổi DB không hợp lệ.
        version = db.execute('PRAGMA user_version').fetchone()[0]
        objects = _schema_snapshot(db)
        if version == 0 and not objects:
            db.execute('BEGIN IMMEDIATE')
            # Recheck sau khi lấy write lock (hai process startup cùng lúc).
            if db.execute('PRAGMA user_version').fetchone()[0] == 0 and not _schema_snapshot(db):
                _create_schema(db)
            db.commit()
        reference = _connect(':memory:')
        try:
            _create_schema(reference)
            expected = _schema_snapshot(reference)
        finally:
            reference.close()
        if db.execute('PRAGMA user_version').fetchone()[0] != 2 or _schema_snapshot(db) != expected:
            raise StorageError('Unsupported storage schema')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise StorageError('Invalid storage data')
        return db
    except BaseException:
        try:
            db.rollback()
        finally:
            db.close()
        raise


def initialize_storage(data_dir: str | pathlib.Path) -> None:
    """Startup sở hữu lifecycle; chỉ publish state khi init và close thành công."""
    global _database_path, _accepting, DATA_DIR, UPLOAD_DIR
    with _condition:
        if _database_path is not None:
            raise StorageError('Storage is already initialized')
        if (not isinstance(data_dir, (str, pathlib.Path)) or not str(data_dir).strip()
                or '\x00' in str(data_dir) or str(data_dir).startswith(('\\\\', '//'))):
            raise StorageError('Invalid storage path')
        raw_path = pathlib.Path(data_dir)
        if '..' in raw_path.parts:
            raise StorageError('Invalid storage path')
        directory = pathlib.Path(os.path.abspath(raw_path))
        try:
            _validate_storage(directory)
            _preflight_db(directory / 'shoplab.sqlite3')
            # Không tạo ancestor tùy ý. Parent phải tồn tại và là boundary tin cậy.
            parent = directory if directory.exists() else directory.parent
            if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
                raise StorageError('Storage parent is not writable')
            if hasattr(os, 'geteuid'):
                info = parent.stat()
                if info.st_uid != os.geteuid() or info.st_mode & stat.S_IWOTH:
                    raise StorageError('Storage parent is not app-owned')
            directory.mkdir(exist_ok=True)
            (directory / 'invoices').mkdir(exist_ok=True)
            _validate_storage(directory)
            connection = _init_db(directory / 'shoplab.sqlite3')
            connection.close()
        except (OSError, sqlite3.Error) as exc:
            raise StorageError('Storage initialization failed') from exc
        DATA_DIR, UPLOAD_DIR = directory, directory / 'invoices'
        _database_path, _accepting = directory / 'shoplab.sqlite3', True


@contextmanager
def storage_transaction(*, write: bool = False):
    """Connection riêng từng service; cleanup hoàn tất trước khi caller gửi response."""
    global _active
    with _condition:
        if _database_path is None or not _accepting:
            raise StorageError('Storage is unavailable')
        path = _database_path
        _active += 1
    db = None
    try:
        _validate_storage(path.parent)
        db = _connect(path)
        try:
            if not write:
                db.execute('PRAGMA query_only = ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
    finally:
        try:
            if db is not None:
                db.close()
        finally:
            with _condition:
                _active -= 1
                _condition.notify_all()


def quiesce_storage() -> None:
    """Chỉ chặn admission và drain; replacement/session invalidation thuộc SL-03/07.

    Timeout giữ admission đóng; không đóng connection của worker khác.
    Không có callback replacement hoặc Boolean giả cấp quyền restore.
    """
    global _accepting
    with _condition:
        _accepting = False
        deadline = time.monotonic() + DRAIN_SECONDS
        while _active:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StorageError('Storage drain timed out')
            _condition.wait(remaining)


def close_storage() -> None:
    """Idempotent, drain workers trước khi bỏ lifecycle state."""
    global _database_path
    with _condition:
        quiesce_storage()
        _database_path = None

# ─────────────────────────────── Helpers ─────────────────────────────────────
def search_products(db: sqlite3.Connection, query: str = "", category: str = "") -> list:
    """Tìm kiếm và lọc đồng thời, dùng tham số SQL và ký tự tìm kiếm literal."""
    if not isinstance(query, str) or len(query) > 200 or not isinstance(category, str):
        raise ValueError("Invalid search input")
    sql = "SELECT p.*, c.name AS cat_name FROM products p JOIN categories c ON p.category_id=c.id"
    conditions = []
    params = []
    if query:
        literal = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        conditions.append("(p.name LIKE ? ESCAPE '!' OR p.description LIKE ? ESCAPE '!')")
        params.extend([f"%{literal}%", f"%{literal}%"])
    if category:
        if len(category) > 10 or not category.isascii() or not category.isdigit() or int(category) < 1:
            raise ValueError("Invalid category")
        conditions.append("p.category_id = ?")
        params.append(int(category))
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    return db.execute(sql + " ORDER BY p.id", params).fetchall()


PASSWORD_ITERATIONS = 600_000
GUEST_TTL = 3600
AUTH_TTL = 28800
MAX_SESSIONS = 1024
MAX_USER_SESSIONS = 5
MAX_BUCKETS = 1024
PRUNE_LIMIT = 64
AUTH_WINDOW = 300


def _positive_id(value: str) -> int:
    """ID chuẩn ASCII, nằm trong miền INTEGER của SQLite."""
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', value):
        raise ValueError('Invalid identifier')
    result = int(value)
    if result > 9223372036854775807:
        raise ValueError('Invalid identifier')
    return result


def _now() -> int:
    return int(time.time())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _password_input(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or len(value.encode('utf-8')) > 512:
        raise ValueError('Invalid credentials')
    return value


def _username_input(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,32}', value):
        raise ValueError('Invalid credentials')
    return value.lower()


def _email_input(value):
    if (not isinstance(value, str) or not 3 <= len(value) <= 254
            or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value)):
        raise ValueError('Invalid credentials')
    return value


def _hash(pw: str) -> str:
    _password_input(pw)
    salt = secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, PASSWORD_ITERATIONS, 32)
    return f'pbkdf2_sha256$1${PASSWORD_ITERATIONS}${salt.hex()}${result.hex()}'


def _verify_password(password: str, encoded) -> bool:
    match = re.fullmatch(r'pbkdf2_sha256\$1\$600000\$([a-f0-9]{32})\$([a-f0-9]{64})', encoded or '') if isinstance(encoded, (str, type(None))) else None
    salt = bytes.fromhex(match[1]) if match else bytes(16)
    expected = bytes.fromhex(match[2]) if match else bytes(32)
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS, 32)
    return hmac.compare_digest(actual, expected) and match is not None


def _header(handler, name):
    headers = handler.headers
    values = headers.get_all(name, []) if hasattr(headers, 'get_all') else ([headers[name]] if name in headers else [])
    if len(values) > 1:
        raise ValueError('Ambiguous request')
    return values[0] if values else ''


def _session_token(handler) -> str:
    cookie = _header(handler, 'Cookie')
    if len(cookie) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in cookie):
        raise ValueError('Invalid cookie')
    found = {}
    for part in cookie.split(';'):
        if not part.strip():
            continue
        key, sep, value = part.strip().partition('=')
        if not sep or key in found:
            raise ValueError('Invalid cookie')
        found[key] = value
    token = found.get('session', '')
    if token and not re.fullmatch(r'[a-f0-9]{64}', token):
        return ''
    return token


def resolve_session(db, token):
    if not token:
        return None
    return db.execute('SELECT s.*,u.username,u.role FROM sessions s LEFT JOIN users u ON u.id=s.user_id '
                      'WHERE token_digest=? AND expires_at>?', (_digest(token), _now())).fetchone()


def _prune(db, table, time_column, cutoff):
    db.execute(f'DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {time_column}<=? LIMIT ?)',
               (cutoff, PRUNE_LIMIT))


def create_session(db, *, user=None, cart_key=None, replacing=None):
    now = _now()
    _prune(db, 'sessions', 'expires_at', now)
    replacement = replacing['token_digest'] if replacing is not None else ''
    count = db.execute('SELECT count(*) FROM sessions WHERE token_digest!=?', (replacement,)).fetchone()[0]
    if count >= MAX_SESSIONS:
        raise StorageError('Session capacity unavailable')
    if user is not None:
        active = db.execute('SELECT count(*) FROM sessions WHERE user_id=? AND expires_at>? AND token_digest!=?',
                            (user['id'], now, replacement)).fetchone()[0]
        if active >= MAX_USER_SESSIONS:
            raise StorageError('Session capacity unavailable')
    token, csrf = secrets.token_hex(32), secrets.token_hex(32)
    key = user['cart_key'] if user is not None else (cart_key or secrets.token_hex(32))
    ttl = AUTH_TTL if user is not None else GUEST_TTL
    if replacing is not None:
        db.execute('DELETE FROM sessions WHERE token_digest=?', (replacement,))
    db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?)',
               (_digest(token), user['id'] if user is not None else None, key, now, now + ttl, csrf))
    return token, resolve_session(db, token)


def _session_headers(token, *, ttl=GUEST_TTL):
    return [('Set-Cookie', f'session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={ttl}'),
            ('Set-Cookie', 'username=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'),
            ('Set-Cookie', 'role=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')]


def _auth_attempt(db, session, username):
    now = _now()
    keys = [('global', 100), ('identity:' + _digest(username), 5), ('session:' + session['token_digest'], 5)]
    rows = {key: db.execute('SELECT * FROM auth_limits WHERE bucket=?', (key,)).fetchone() for key, _ in keys}
    if any(row is not None and row['started_at'] + AUTH_WINDOW > now and row['attempts'] >= limit
           for (key, limit) in keys for row in [rows[key]]):
        return False
    _prune(db, 'auth_limits', 'started_at', now - AUTH_WINDOW)
    missing = sum(db.execute('SELECT 1 FROM auth_limits WHERE bucket=?', (key,)).fetchone() is None for key, _ in keys)
    if db.execute('SELECT count(*) FROM auth_limits').fetchone()[0] + missing > MAX_BUCKETS:
        return False
    for key, _ in keys:
        db.execute('INSERT INTO auth_limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET '
                   'started_at=excluded.started_at,attempts=CASE WHEN auth_limits.started_at=excluded.started_at THEN auth_limits.attempts+1 ELSE 1 END', (key, rows[key]['started_at']
                   if rows[key] is not None and rows[key]['started_at'] + AUTH_WINDOW > now else now))
    return True


def _merge_guest_cart(db, session, user):
    if session['user_id'] is not None or session['cart_key'] == user['cart_key']:
        return
    rows = db.execute('SELECT c.product_id,sum(c.quantity) AS quantity,p.stock FROM cart c '
                      'JOIN products p ON p.id=c.product_id WHERE c.session_id IN (?,?) '
                      'GROUP BY c.product_id,p.stock', (session['cart_key'], user['cart_key'])).fetchall()
    if len(rows) > 50 or any(not 1 <= row['quantity'] <= min(99, row['stock']) for row in rows):
        raise ValueError('Cart merge rejected')
    for row in rows:
        db.execute('INSERT INTO cart(session_id,product_id,quantity) VALUES (?,?,?) '
                   'ON CONFLICT(session_id,product_id) DO UPDATE SET quantity=excluded.quantity',
                   (user['cart_key'], row['product_id'], row['quantity']))
    db.execute('DELETE FROM cart WHERE session_id=?', (session['cart_key'],))


def owns_order(session, order) -> bool:
    if session is None or order is None:
        return False
    if order['user_id'] is not None:
        return session['user_id'] == order['user_id']
    return session['user_id'] is None and session['cart_key'] == order['session_id']


def set_local_role(data_dir, user_id, role):
    """Máy lab/ACL là authority; không exposed qua HTTP hoặc tạo storage."""
    if type(user_id) is not int or user_id < 1 or role not in ('user', 'admin'):
        raise ValueError('Invalid administrative request')
    with _condition:
        if _database_path is not None or _active:
            raise StorageError('Storage must be closed')
        if not isinstance(data_dir, (str, pathlib.Path)) or not str(data_dir).strip() or '\x00' in str(data_dir) or '..' in pathlib.Path(data_dir).parts or str(data_dir).startswith(('\\\\', '//')):
            raise StorageError('Invalid storage path')
        directory = pathlib.Path(os.path.abspath(data_dir))
        _validate_storage(directory)
        if not directory.is_dir() or not os.access(directory, os.W_OK | os.X_OK):
            raise StorageError('Invalid storage path')
        if hasattr(os, 'geteuid') and (directory.stat().st_uid != os.geteuid() or directory.stat().st_mode & stat.S_IWOTH):
            raise StorageError('Invalid storage ownership')
        path = directory / 'shoplab.sqlite3'
        _preflight_db(path, required=True)
        db = _connect(path)
        try:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT role FROM users WHERE id=?', (user_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown account')
            if row['role'] != role:
                db.execute('UPDATE users SET role=? WHERE id=?', (role, user_id))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                db.execute('INSERT INTO admin_audit(action,user_id,old_role,new_role,created_at) VALUES (?,?,?,?,?)',
                           ('promote' if role == 'admin' else 'revoke', user_id, row['role'], role,
                            datetime.now(timezone.utc).isoformat()))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

# ─────────────────────────────── Templates ───────────────────────────────────
_BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title} — ShopLab</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#f5f5f5;color:#222}}
.nav{{background:#1a1a2e;color:#fff;padding:14px 32px;display:flex;align-items:center;gap:24px}}
.nav a{{color:#eee;text-decoration:none;font-size:15px}}
.nav a:hover{{color:#e94560}}
.nav .brand{{font-size:22px;font-weight:700;color:#e94560;margin-right:auto}}
.container{{max-width:1100px;margin:32px auto;padding:0 20px}}
.card{{background:#fff;border-radius:8px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:20px}}
.btn{{display:inline-block;padding:10px 22px;border-radius:6px;border:none;cursor:pointer;font-size:15px;text-decoration:none}}
.btn-primary{{background:#e94560;color:#fff}}.btn-primary:hover{{background:#c73652}}
.btn-secondary{{background:#1a1a2e;color:#fff}}.btn-secondary:hover{{background:#16213e}}
.btn-sm{{padding:6px 14px;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:20px}}
.product-card{{background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.product-card img{{width:100%;height:160px;object-fit:cover;background:#e0e0e0}}
.product-card .info{{padding:16px}}
.product-card .name{{font-weight:600;font-size:16px;margin-bottom:6px}}
.product-card .price{{color:#e94560;font-size:18px;font-weight:700;margin-bottom:12px}}
.product-card .cat{{font-size:12px;color:#888;margin-bottom:8px}}
.alert{{padding:12px 18px;border-radius:6px;margin-bottom:16px}}
.alert-error{{background:#fee;border:1px solid #f99;color:#c00}}
.alert-success{{background:#efe;border:1px solid #9f9;color:#060}}
input,textarea,select{{width:100%;padding:10px;border:1px solid #ddd;border-radius:6px;font-size:15px;margin-bottom:12px}}
label{{display:block;margin-bottom:4px;font-weight:600;font-size:14px}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:10px 14px;border-bottom:1px solid #eee}}
th{{background:#f0f0f0;font-weight:600}}
.badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600}}
.badge-pending{{background:#fff3cd;color:#856404}}
.badge-completed{{background:#d4edda;color:#155724}}
.stars{{color:#f5a623;font-size:18px}}
footer{{text-align:center;padding:32px;color:#888;font-size:14px;margin-top:48px}}
</style>
</head>
<body>
<nav class="nav">
  <span class="brand">🛒 ShopLab</span>
  <a href="/">Home</a>
  <a href="/products">Products</a>
  <a href="/cart">Cart</a>
  {nav_extra}
</nav>
<div class="container">
{body}
</div>
<footer>ShopLab &copy; 2024 — Lab-isolated demo store</footer>
</body></html>"""

def _render(title: str, body: str, nav_user: str = "") -> str:
    nav_extra = nav_user or '<a href="/login">Login</a> <a href="/register">Register</a>'
    return _BASE.format(title=html_escape(title), body=body, nav_extra=nav_extra)

# ─────────────────────────────── Handler ─────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "ShopLab/1.0"

    # ── low-level send helpers ────────────────────────────────────────────
    def _send(self, status: int, body: str, ct: str = "text/html; charset=utf-8",
              extra_headers: list | None = None) -> None:
        self._pending_response = (status, body.encode('utf-8'), [('Content-Type', ct), *(extra_headers or [])])

    def _flush_response(self) -> None:
        status, encoded, headers = self._pending_response
        self.send_response(status)
        for key, value in [*headers, *getattr(self, '_security_headers', [])]:
            self.send_header(key, value)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _request(self, dispatch, *, write: bool) -> None:
        self._pending_response = None
        self._cached_body = None
        self._identity = None
        self._security_headers = []
        try:
            self._params()  # Từ chối query mơ hồ trước cả session bootstrap.
            token = _session_token(self)
            if write:
                self._cached_body = self._read_body()
                self._cached_form = self._parse_form(self._cached_body)
            elif self._form_page():
                with storage_transaction() as db:
                    current = resolve_session(db, token)
                if current is None:
                    with storage_transaction(write=True) as db:
                        token, current = create_session(db)
                    self._security_headers = _session_headers(token)
            with storage_transaction(write=write) as db:
                self._identity = resolve_session(db, token)
                if write and not self._csrf_valid():
                    self._send_json(403, {'error': 'Request is not authorized'})
                else:
                    dispatch(db)
        except sqlite3.IntegrityError:
            self._send_json(409, {'error': 'Storage constraint rejected'})
        except (StorageError, sqlite3.Error, OSError):
            self._send_json(503, {'error': 'Storage is unavailable'})
        except ValueError:
            self._send_json(400, {'error': 'Invalid request'})
        if self._pending_response is not None:
            self._flush_response()

    def _send_json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj, sort_keys=True), "application/json")

    def _redirect(self, location: str, extra_headers: list | None = None) -> None:
        self._pending_response = (302, b'', [('Location', location), *(extra_headers or [])])

    def _params(self) -> dict[str, list[str]]:
        query = urlsplit(self.path).query
        if len(query) > 8192:
            raise ValueError('Invalid query')
        return {key: [value] for key, value in self._parse_form(query.encode('utf-8')).items()}

    def _p(self, key: str, default: str = "") -> str:
        return self._params().get(key, [default])[0]

    def _read_body(self) -> bytes:
        if self._cached_body is not None:
            return self._cached_body
        length_header = _header(self, 'Content-Length') or '0'
        if not length_header.isascii() or not length_header.isdigit() or _header(self, 'Transfer-Encoding'):
            raise ValueError('Invalid request length')
        length = int(length_header)
        if not 0 <= length <= 16 * 1024:
            raise ValueError('Invalid request length')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('Incomplete request body')
        return raw

    @staticmethod
    def _parse_form(raw: bytes) -> dict[str, str]:
        text = raw.decode('utf-8')
        if re.search(r'%(?![A-Fa-f0-9]{2})', text):
            raise ValueError('Invalid form encoding')
        parsed = parse_qs(text, keep_blank_values=True, strict_parsing=True, errors='strict', max_num_fields=30)
        if any(len(v) != 1 or len(k) > 64 for k, v in parsed.items()):
            raise ValueError('Ambiguous form')
        return {k: v[0] for k, v in parsed.items()}

    def _form(self) -> dict[str, str]:
        return self._cached_form

    def _form_page(self):
        path = urlsplit(self.path).path
        return path in ('/', '/products', '/cart', '/login', '/register') or bool(re.fullmatch(r'/products/[0-9]+', path))

    def _csrf_valid(self):
        if self._identity is None:
            return False
        header = _header(self, 'X-CSRF-Token')
        form = self._cached_form.get('csrf_token', '')
        if header and form and header != form:
            return False
        token = header or form
        return bool(re.fullmatch(r'[a-f0-9]{64}', token)) and hmac.compare_digest(token, self._identity['csrf_secret'])

    def _csrf_field(self):
        return f"<input type='hidden' name='csrf_token' value='{self._identity['csrf_secret']}'>" if self._identity is not None else ''

    def _session(self) -> str:
        return self._identity['cart_key'] if self._identity is not None else ''

    def _role(self) -> str:
        return self._identity['role'] if self._identity is not None and self._identity['user_id'] is not None else 'user'

    def _username(self) -> str | None:
        return self._identity['username'] if self._identity is not None else None

    def _require_user(self):
        if self._identity is None or self._identity['user_id'] is None:
            self._send_json(403, {'error': 'Request is not authorized'})
            return False
        return True

    # ── GET dispatcher ────────────────────────────────────────────────────
    def do_GET(self) -> None:
        self._request(self._dispatch_get, write=False)

    def _dispatch_get(self, db) -> None:
        path = urlsplit(self.path).path
        routes = {
            "/":           self._home,
            "/products":   self._products_list,
            "/cart":       self._cart_view,
            "/login":      self._login_form,
            "/register":   self._register_form,
            "/logout":     self._logout_read,
            "/orders":     self._orders_list,
            "/admin":      self._admin_panel,
            "/health":     self._health,
        }
        if path in routes:
            routes[path](db)
        elif path.startswith("/products/"):
            self._product_detail(db, path)
        elif path.startswith("/download/invoice"):
            self._download_invoice(db)
        elif path.startswith("/api/"):
            self._api_dispatch(db, path)
        else:
            self._send(404, _render("Not Found", "<div class='card'><h2>404 — Page not found</h2><p><a href='/'>← Home</a></p></div>"))

    def do_POST(self) -> None:
        if urlsplit(self.path).path == '/reset':
            self._reset(None)
            self._flush_response()
            return
        self._request(self._dispatch_post, write=True)

    def _dispatch_post(self, db) -> None:
        path = urlsplit(self.path).path
        routes = {
            "/login":         self._login_submit,
            "/register":      self._register_submit,
            "/logout":        self._logout,
            "/cart/add":      self._cart_add,
            "/cart/remove":   self._cart_remove,
            "/checkout":      self._checkout,
            "/reviews":       self._review_submit,
            "/reset":         self._reset,
        }
        if path in routes:
            routes[path](db)
        else:
            self._send(404, _render("Not Found", "<div class='card'><h2>404</h2></div>"))

    # ── Health ────────────────────────────────────────────────────────────
    def _health(self, db) -> None:
        self._send_json(200, {"status": "ok", "target_id": TARGET_ID})

    # ── Home ─────────────────────────────────────────────────────────────
    def _home(self, db) -> None:
        rows = db.execute("SELECT p.*, c.name AS cat_name FROM products p JOIN categories c ON p.category_id=c.id LIMIT 6").fetchall()
        cards = "".join(self._product_card(r) for r in rows)
        body = f"""
        <div class='card' style='background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;margin-bottom:24px'>
          <h1 style='font-size:32px;margin-bottom:10px'>Welcome to ShopLab 🛒</h1>
          <p style='color:#ccc;font-size:17px'>Your one-stop lab store. Browse, add to cart, checkout and review products.</p>
          <a href='/products' class='btn btn-primary' style='margin-top:16px'>Shop Now →</a>
        </div>
        <h2 style='margin-bottom:16px'>Featured Products</h2>
        <div class='grid'>{cards}</div>
        """
        self._send(200, _render("Home", body, self._nav()))

    def _nav(self) -> str:
        u = self._username()
        if not u:
            return ''
        admin = '<a href="/admin">Admin</a>' if self._role() == 'admin' else ''
        return (f'<a href="/orders">My Orders</a> {admin} '
                f'<form method="POST" action="/logout">{self._csrf_field()}'
                f'<button>Logout ({html_escape(u)})</button></form>')

    def _product_card(self, row) -> str:
        pid = row["id"]
        name = html_escape(row["name"])
        price = f"${row['price']:.2f}"
        cat = html_escape(row["cat_name"])
        return f"""
        <div class='product-card'>
          <div class='info'>
            <div class='cat'>{cat}</div>
            <div class='name'>{name}</div>
            <div class='price'>{price}</div>
            <a href='/products/{pid}' class='btn btn-secondary btn-sm'>View Details</a>
            &nbsp;
            <form method='POST' action='/cart/add' style='display:inline'>
              {self._csrf_field()}
              <input type='hidden' name='product_id' value='{pid}'>
              <input type='hidden' name='quantity' value='1'>
              <button class='btn btn-primary btn-sm'>Add to Cart</button>
            </form>
          </div>
        </div>"""

    # ── Products ──────────────────────────────────────────────────────────
    def _products_list(self, db) -> None:
        q = self._p("q")
        cat_id = self._p("category")
        try:
            rows = search_products(db, q, cat_id)
            error_html = ""
        except ValueError:
            self._send(400, _render("Error", "<div class='alert alert-error'>Invalid search or category.</div>"))
            return

        cats = db.execute("SELECT * FROM categories").fetchall()
        cat_options = "".join(f'<option value="{c["id"]}"{"selected" if str(c["id"])==cat_id else ""}>{html_escape(c["name"])}</option>' for c in cats)
        cards = "".join(self._product_card(r) for r in rows)
        body = f"""
        <div class='card'>
          <h2 style='margin-bottom:16px'>Products ({len(rows)} found)</h2>
          <form method='GET' action='/products' style='display:flex;gap:12px;flex-wrap:wrap'>
            <input name='q' placeholder='Search products...' value='{html_escape(q)}' style='flex:1;min-width:200px'>
            <select name='category' style='flex:0;min-width:160px'>
              <option value=''>All Categories</option>{cat_options}
            </select>
            <button class='btn btn-primary'>Search</button>
          </form>
        </div>
        {error_html}
        <div class='grid'>{cards if cards else "<div class='card'><p>No products found.</p></div>"}</div>
        """
        self._send(200, _render("Products", body, self._nav()))

    def _product_detail(self, db, path: str) -> None:
        try:
            pid = _positive_id(path.split("/")[-1])
        except ValueError:
            self._send(400, _render("Error", "<div class='card'><p>Invalid product ID.</p></div>")); return
        row = db.execute("SELECT p.*, c.name AS cat_name FROM products p JOIN categories c ON p.category_id=c.id WHERE p.id=?", (pid,)).fetchone()
        if not row:
            self._send(404, _render("Not Found", "<div class='card'><h2>Product not found</h2></div>")); return

        # Nội dung review luôn escape, kể cả dữ liệu đã lưu từ trước.
        reviews = db.execute("SELECT * FROM reviews WHERE product_id=? ORDER BY id DESC", (pid,)).fetchall()
        review_html = ""
        for rev in reviews:
            stars = "★" * rev["rating"] + "☆" * (5 - rev["rating"])
            # Không để nội dung không tin cậy chạy trong origin của session.
            review_html += f"""
            <div class='card' style='margin-bottom:12px'>
              <b>{html_escape(rev["username"])}</b>
              <span class='stars' style='margin-left:8px'>{stars}</span>
              <p style='margin-top:8px'>{html_escape(rev["body"] or '')}</p>
            </div>"""

        u = self._username()
        review_form = ""
        if u:
            review_form = f"""
            <div class='card'>
              <h3>Write a Review</h3>
              <form method='POST' action='/reviews'>
                {self._csrf_field()}
                <input type='hidden' name='product_id' value='{pid}'>
                <label>Rating</label>
                <select name='rating'>
                  {''.join(f'<option value="{i}">{i} star{"s" if i>1 else ""}</option>' for i in range(5,0,-1))}
                </select>
                <label>Review</label>
                <textarea name='body' rows='4' placeholder='Share your experience...'></textarea>
                <button class='btn btn-primary'>Submit Review</button>
              </form>
            </div>"""

        body = f"""
        <a href='/products' style='color:#e94560;text-decoration:none;font-size:14px'>← Back to Products</a>
        <div class='card' style='margin-top:16px'>
          <div style='display:flex;gap:24px;flex-wrap:wrap'>
            <div style='flex:1;min-width:200px;background:#e0e0e0;height:250px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:48px'>🛍️</div>
            <div style='flex:2;min-width:280px'>
              <p style='color:#888;font-size:13px'>{html_escape(row["cat_name"])}</p>
              <h1 style='margin:8px 0'>{html_escape(row["name"])}</h1>
              <p style='margin:12px 0;color:#555'>{html_escape(row["description"])}</p>
              <div style='font-size:28px;color:#e94560;font-weight:700;margin:16px 0'>${row["price"]:.2f}</div>
              <p style='color:#888;font-size:14px;margin-bottom:16px'>{row["stock"]} in stock</p>
              <form method='POST' action='/cart/add'>
                {self._csrf_field()}
                <input type='hidden' name='product_id' value='{pid}'>
                <div style='display:flex;gap:12px;align-items:center;flex-wrap:wrap'>
                  <input name='quantity' type='number' value='1' min='1' max='{row["stock"]}' style='width:80px'>
                  <button class='btn btn-primary'>Add to Cart</button>
                </div>
              </form>
            </div>
          </div>
        </div>
        <h2 style='margin:24px 0 12px'>Customer Reviews ({len(reviews)})</h2>
        {review_html if review_html else "<div class='card'><p>No reviews yet. Be the first!</p></div>"}
        {review_form}
        """
        self._send(200, _render(row["name"], body, self._nav()))

    # ── Cart ─────────────────────────────────────────────────────────────
    def _cart_view(self, db) -> None:
        sid = self._session()
        rows = db.execute("""
            SELECT c.id, c.quantity, p.name, p.price, p.id AS pid
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.session_id=?""", (sid,)).fetchall()
        if not rows:
            body = "<div class='card'><h2>Your Cart</h2><p>Your cart is empty. <a href='/products'>Shop now →</a></p></div>"
        else:
            total = sum(r["price"] * r["quantity"] for r in rows)
            items_html = "".join(f"""
            <tr>
              <td><a href='/products/{r["pid"]}'>{html_escape(r["name"])}</a></td>
              <td>${r["price"]:.2f}</td>
              <td>{r["quantity"]}</td>
              <td>${r["price"]*r["quantity"]:.2f}</td>
              <td>
                <form method='POST' action='/cart/remove' style='display:inline'>
                  {self._csrf_field()}
                  <input type='hidden' name='cart_id' value='{r["id"]}'>
                  <button class='btn btn-secondary btn-sm'>Remove</button>
                </form>
              </td>
            </tr>""" for r in rows)
            body = f"""
            <div class='card'>
              <h2>Your Cart</h2>
              <table style='margin:16px 0'>
                <tr><th>Product</th><th>Price</th><th>Qty</th><th>Subtotal</th><th></th></tr>
                {items_html}
              </table>
              <div style='text-align:right;font-size:20px;font-weight:700;margin:16px 0'>
                Total: <span style='color:#e94560'>${total:.2f}</span>
              </div>
              <form method='POST' action='/checkout'>
                {self._csrf_field()}
                <h3 style='margin-bottom:12px'>Shipping Information</h3>
                <label>Full Name</label><input name='full_name' placeholder='John Doe' required>
                <label>Address</label><input name='address' placeholder='123 Main St, City' required>
                <label>Email</label><input name='email' type='email' placeholder='you@example.com' required>
                <button class='btn btn-primary' style='margin-top:8px'>Place Order (${total:.2f})</button>
              </form>
            </div>"""
        self._send(200, _render("Cart", body, self._nav()))

    def _cart_add(self, db) -> None:
        f = self._form()
        sid = self._session()
        pid = _positive_id(f.get('product_id', '0'))
        qty = int(f.get('quantity', '1'))
        product = db.execute('SELECT stock FROM products WHERE id=?', (pid,)).fetchone()
        if product is None:
            self._send_json(409, {'error': 'Product unavailable'}); return
        existing = db.execute('SELECT id, quantity FROM cart WHERE session_id=? AND product_id=?', (sid, pid)).fetchone()
        total = qty + (existing['quantity'] if existing else 0)
        if not 1 <= qty <= 99 or not 1 <= total <= min(99, product['stock']):
            raise ValueError('Invalid quantity')
        if not existing and db.execute('SELECT count(*) FROM cart WHERE session_id=?', (sid,)).fetchone()[0] >= 50:
            raise ValueError('Cart limit')
        if existing:
            db.execute("UPDATE cart SET quantity=? WHERE id=?", (existing["quantity"] + qty, existing["id"]))
        else:
            db.execute("INSERT INTO cart (session_id, product_id, quantity) VALUES (?,?,?)", (sid, pid, qty))
        self._redirect('/cart')

    def _cart_remove(self, db) -> None:
        f = self._form()
        sid = self._session()
        cart_id = _positive_id(f.get("cart_id", "0"))
        db.execute("DELETE FROM cart WHERE id=? AND session_id=?", (cart_id, sid))
        self._redirect("/cart")

    # ── Checkout ─────────────────────────────────────────────────────────
    def _checkout(self, db) -> None:
        sid = self._session()
        items = db.execute("""
            SELECT c.quantity, p.price, p.id AS pid, p.name
            FROM cart c JOIN products p ON c.product_id=p.id
            WHERE c.session_id=?""", (sid,)).fetchall()
        if not items:
            self._redirect("/cart"); return
        total = sum(r["price"] * r["quantity"] for r in items)
        uid = self._identity['user_id']
        inv_name = f"INV-{uuid.uuid4().hex.upper()}.txt"
        inv_path = UPLOAD_DIR / inv_name
        _validate_path(inv_path, directory=False)
        f = self._form()
        # File và SQLite không atomic chung: commit failure có thể giữ orphan.
        # Không xóa orphan tùy ý; reconciliation cần workflow SL-04/SL-07.
        with inv_path.open('x', encoding='utf-8') as invoice:
            invoice.write(
                f"Invoice: {inv_name}\nName: {f.get('full_name','')}\n"
                f"Address: {f.get('address','')}\nTotal: ${total:.2f}\n"
                + "\n".join(f"  {r['name']} x{r['quantity']} @ ${r['price']:.2f}" for r in items)
            )
        cur = db.execute("INSERT INTO orders (user_id, session_id, total, status, invoice_file) VALUES (?,?,?,?,?)",
                         (uid, sid, total, "completed", inv_name))
        order_id = cur.lastrowid
        for r in items:
            db.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)",
                       (order_id, r["pid"], r["quantity"], r["price"]))
        db.execute("DELETE FROM cart WHERE session_id=?", (sid,))
        body = f"""
        <div class='card' style='text-align:center;padding:48px'>
          <div style='font-size:64px'>✅</div>
          <h2 style='margin:16px 0'>Order Placed Successfully!</h2>
          <p>Order #{order_id} &bull; Total: <strong>${total:.2f}</strong></p>
          <p style='margin:12px 0;color:#555'>Lab order only: no payment was charged and no email was sent. Contact: {html_escape(f.get("email",""))}.</p>
          <a href='/download/invoice?file={inv_name}' class='btn btn-secondary' style='margin-top:16px'>Download Invoice</a>
          &nbsp;
          <a href='/products' class='btn btn-primary' style='margin-top:16px'>Continue Shopping</a>
        </div>"""
        self._send(200, _render("Order Confirmed", body, self._nav()))

    # ── Reviews ───────────────────────────────────────────────────────────
    def _review_submit(self, db) -> None:
        f = self._form()
        u = self._username()
        if not self._require_user():
            return
        try:
            pid = _positive_id(f.get("product_id", "0"))
            rating = max(1, min(5, int(f.get("rating", "3"))))
        except ValueError:
            self._redirect("/products"); return
        body_text = f.get("body", "")
        uid = self._identity['user_id']
        if len(body_text) > 4000:
            raise ValueError('Review is too long')
        # Lưu text; output escape khi render.
        db.execute("INSERT INTO reviews (product_id, user_id, username, rating, body) VALUES (?,?,?,?,?)",
                   (pid, uid, u, rating, body_text))
        self._redirect(f"/products/{pid}")

    # ── Invoice download ──────────────────────────────────────────────────
    def _download_invoice(self, db) -> None:
        filename = self._p('file')
        if not re.fullmatch(r'INV-[A-F0-9]{32}\.txt', filename):
            self._send_json(400, {'error': 'Invalid invoice name'}); return
        order = db.execute('SELECT user_id,session_id FROM orders WHERE invoice_file=?', (filename,)).fetchone()
        if not owns_order(self._identity, order):
            self._send_json(404, {'error': 'Not found'}); return
        filepath = UPLOAD_DIR / filename
        _validate_path(filepath, directory=False)
        try:
            content = filepath.read_text()
            self._send(200, content, "text/plain")
        except FileNotFoundError:
            self._send(404, _render("Not Found", "<div class='card'><p>Invoice not found.</p></div>"))
        except OSError:
            self._send_json(503, {'error': 'Storage is unavailable'})

    # ── Orders ────────────────────────────────────────────────────────────
    def _orders_list(self, db) -> None:
        if self._identity is None:
            self._send_json(403, {'error': 'Request is not authorized'}); return
        if self._identity['user_id'] is not None:
            orders = db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC', (self._identity['user_id'],)).fetchall()
        else:
            orders = db.execute('SELECT * FROM orders WHERE user_id IS NULL AND session_id=? ORDER BY id DESC', (self._session(),)).fetchall()
        rows_html = "".join(f"""
        <tr>
          <td>#{r["id"]}</td>
          <td>${r["total"]:.2f}</td>
          <td><span class='badge badge-{html_escape(r["status"] or '')}'>{html_escape(r["status"] or '')}</span></td>
          <td>{html_escape(r["created_at"] or '')}</td>
          <td><a href='/download/invoice?file={html_escape(urlencode({'file': r['invoice_file'] or ''})[5:])}' class='btn btn-secondary btn-sm'>Invoice</a></td>
        </tr>""" for r in orders)
        body = f"""
        <div class='card'>
          <h2>My Orders</h2>
          {"<table style='margin-top:16px'><tr><th>#</th><th>Total</th><th>Status</th><th>Date</th><th></th></tr>" + rows_html + "</table>" if orders else "<p>No orders yet.</p>"}
        </div>"""
        self._send(200, _render("My Orders", body, self._nav()))

    # ── Admin panel ───────────────────────────────────────────────────────
    def _admin_panel(self, db) -> None:
        # Role đọc từ DB-backed identity của request hiện tại.
        role = self._role()
        if role != "admin":
            self._send(403, _render("Forbidden", "<div class='card'><h2>403 Forbidden</h2><p>Admin access required. <a href='/login'>Login</a></p></div>"))
            return
        users = db.execute("SELECT id, username, email, role FROM users").fetchall()
        orders = db.execute("SELECT o.*, u.username FROM orders o LEFT JOIN users u ON o.user_id=u.id ORDER BY o.id DESC").fetchall()
        # Customer order endpoints vẫn owner-only, không bypass bởi admin.
        user_rows = "".join(f"<tr><td>{r['id']}</td><td>{html_escape(r['username'])}</td><td>{html_escape(r['email'] or '')}</td><td>{r['role']}</td></tr>" for r in users)
        order_rows = "".join(f"<tr><td>#{r['id']}</td><td>{html_escape(r['username'] or 'guest')}</td><td>${r['total']:.2f}</td><td>{html_escape(r['status'] or '')}</td></tr>" for r in orders)
        body = f"""
        <div class='card'>
          <h2>🔑 Admin Panel</h2>
          <p style='color:#888;margin-bottom:24px'>Logged in as admin</p>
          <h3>Users ({len(users)})</h3>
          <table style='margin:12px 0 24px'><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th></tr>{user_rows}</table>
          <h3>All Orders ({len(orders)})</h3>
          <table style='margin:12px 0'><tr><th>#</th><th>User</th><th>Total</th><th>Status</th></tr>{order_rows}</table>
        </div>"""
        self._send(200, _render("Admin", body, self._nav()))

    # ── Auth ──────────────────────────────────────────────────────────────
    def _login_form(self, db) -> None:
        msg = self._p("msg")
        alert = f"<div class='alert alert-error'>{html_escape(msg)}</div>" if msg else ""
        body = f"""
        <div style='max-width:420px;margin:0 auto'>
          <div class='card'>
            <h2 style='margin-bottom:20px'>Sign In</h2>
            {alert}
            <form method='POST' action='/login'>
              {self._csrf_field()}
              <label>Username</label><input name='username' required autofocus>
              <label>Password</label><input name='password' type='password' required>
              <button class='btn btn-primary' style='width:100%'>Sign In</button>
            </form>
            <p style='margin-top:16px;text-align:center;color:#888'>Don't have an account? <a href='/register'>Register</a></p>
          </div>
        </div>"""
        self._send(200, _render("Login", body))

    def _login_submit(self, db) -> None:
        f = self._form()
        u = _username_input(f.get('username', ''))
        p = _password_input(f.get('password', ''))
        if not _auth_attempt(db, self._identity, u):
            self._send_json(429, {'error': 'Authentication temporarily unavailable'}); return
        row = db.execute('SELECT * FROM users WHERE username=?', (u,)).fetchone()
        if not _verify_password(p, row['password_hash'] if row else None):
            self._send_json(403, {'error': 'Invalid username or password'}); return
        _merge_guest_cart(db, self._identity, row)
        token, self._identity = create_session(db, user=row, replacing=self._identity)
        self._redirect('/', _session_headers(token, ttl=AUTH_TTL))

    def _register_form(self, db) -> None:
        msg = self._p("msg")
        alert = f"<div class='alert alert-error'>{html_escape(msg)}</div>" if msg else ""
        body = f"""
        <div style='max-width:420px;margin:0 auto'>
          <div class='card'>
            <h2 style='margin-bottom:20px'>Create Account</h2>
            {alert}
            <form method='POST' action='/register'>
              {self._csrf_field()}
              <label>Username</label><input name='username' required autofocus>
              <label>Email</label><input name='email' type='email' required>
              <label>Password</label><input name='password' type='password' required>
              <button class='btn btn-primary' style='width:100%'>Create Account</button>
            </form>
            <p style='margin-top:16px;text-align:center;color:#888'>Already have an account? <a href='/login'>Sign In</a></p>
          </div>
        </div>"""
        self._send(200, _render("Register", body))

    def _register_submit(self, db) -> None:
        f = self._form()
        u = _username_input(f.get('username', ''))
        e = _email_input(f.get('email', ''))
        p = _password_input(f.get('password', ''))
        if not _auth_attempt(db, self._identity, u):
            self._send_json(429, {'error': 'Authentication temporarily unavailable'}); return
        if db.execute('SELECT 1 FROM users WHERE username=?', (u,)).fetchone():
            self._send_json(409, {'error': 'Account registration rejected'}); return
        cur = db.execute('INSERT INTO users(username,email,password_hash,cart_key) VALUES (?,?,?,?)',
                         (u, e, _hash(p), secrets.token_hex(32)))
        row = db.execute('SELECT * FROM users WHERE id=?', (cur.lastrowid,)).fetchone()
        _merge_guest_cart(db, self._identity, row)
        token, self._identity = create_session(db, user=row, replacing=self._identity)
        self._redirect('/', _session_headers(token, ttl=AUTH_TTL))

    def _logout_read(self, db):
        self._send_json(405, {'error': 'Use POST with CSRF'})

    def _logout(self, db) -> None:
        db.execute('DELETE FROM sessions WHERE token_digest=?', (self._identity['token_digest'],))
        self._redirect('/', _session_headers('', ttl=0))

    # ── API (JSON) ────────────────────────────────────────────────────────
    def _api_dispatch(self, db, path: str) -> None:
        if path == "/api/products":
            rows = db.execute("SELECT id, name, price FROM products").fetchall()
            self._send_json(200, {"products": [dict(r) for r in rows]}); return
        if path == "/api/categories":
            rows = db.execute("SELECT * FROM categories").fetchall()
            self._send_json(200, {"categories": [dict(r) for r in rows]}); return
        if path.startswith("/api/orders/"):
            # Ownership trước projection; không lộ server association identifiers.
            try:
                oid = _positive_id(path.split("/")[-1])
            except ValueError:
                self._send_json(400, {"error": "invalid order id"}); return
            row = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
            if not owns_order(self._identity, row):
                self._send_json(404, {'error': 'not found'}); return
            items = db.execute('SELECT oi.product_id,oi.quantity,oi.unit_price,oi.currency,p.name FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?', (oid,)).fetchall()
            safe = {key: row[key] for key in ('id', 'total', 'currency', 'status', 'created_at')}
            self._send_json(200, {'order': safe, 'items': [dict(i) for i in items]}); return
        if path == "/api/reviews":
            pid = self._p("product_id")
            if pid:
                rows = db.execute("SELECT * FROM reviews WHERE product_id=?", (pid,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM reviews").fetchall()
            self._send_json(200, {"reviews": [dict(r) for r in rows]}); return
        self._send_json(404, {"error": "not found"})

    # ── Reset (for test repeatability) ───────────────────────────────────
    def _reset(self, db) -> None:
        # Không xóa dữ liệu lưu trữ qua một endpoint HTTP không có phê duyệt.
        self._send_json(403, {"error": "Reset requires an approved local administrative workflow"})

    def log_message(self, format: str, *args: object) -> None:
        return  # suppress access log


if __name__ == "__main__":
    initialize_storage(DATA_DIR)
    try:
        print(f"ShopLab starting on port {PORT} (isolated lab only)...")
        with ThreadingHTTPServer(("0.0.0.0", PORT), Handler) as server:
            server.serve_forever()
    finally:
        close_storage()
