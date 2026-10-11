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
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from functools import wraps
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, urlencode

PORT = int(os.environ.get("PORT", "8080"))
TARGET_ID = os.environ.get("TARGET_ID", "lab-ecommerce")
SHOPLAB_CURRENCY = "USD"
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
        CREATE TABLE order_idempotency (
            key TEXT NOT NULL,
            owner_key TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            session_id TEXT NOT NULL,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            request_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(key, owner_key)
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
        CREATE TABLE product_archives (
            product_id INTEGER PRIMARY KEY REFERENCES products(id),
            archived_at TEXT NOT NULL
        );
        CREATE TABLE admin_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT NOT NULL
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


def _can_upgrade_schema(db, reference) -> bool:
    """Kiểm tra DB có thể upgrade an toàn sang new schema (order_idempotency missing hoặc new tables)."""
    ref_objects = {row[1]: tuple(row) for row in reference.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'")}
    db_objects = {row[1]: tuple(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'")}
    upgrade_allowed = {'order_idempotency', 'product_archives', 'admin_activity_log'}
    for name, row in ref_objects.items():
        if name in upgrade_allowed:
            continue
        if name not in db_objects or db_objects[name] != row:
            return False
    for name, row in db_objects.items():
        if name in upgrade_allowed:
            continue
        if name not in ref_objects or ref_objects[name] != row:
            return False
    if 'order_idempotency' in db_objects:
        cols = {col[1] for col in db.execute("PRAGMA table_info(order_idempotency)").fetchall()}
        if not {'key', 'session_id', 'order_id', 'request_hash'}.issubset(cols):
            return False
    return True


def _migrate_order_idempotency(db) -> None:
    """Migrate order_idempotency sang (key, owner_key) deterministic và an toàn."""
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    needs_migration = False
    has_old_data = False
    if 'order_idempotency' not in tables:
        needs_migration = True
    else:
        cols = {col[1] for col in db.execute("PRAGMA table_info(order_idempotency)").fetchall()}
        if 'owner_key' not in cols:
            needs_migration = True
            has_old_data = True

    if not needs_migration:
        return

    create_stmt = None
    for stmt in _SCHEMA:
        if 'CREATE TABLE order_idempotency' in stmt:
            create_stmt = stmt
            break

    if has_old_data:
        db.execute("CREATE TEMP TABLE _old_idem AS SELECT key, session_id, user_id, order_id, request_hash, created_at FROM order_idempotency")
        db.execute("DROP TABLE order_idempotency")
        db.execute(create_stmt)
        db.execute("""
            INSERT OR IGNORE INTO order_idempotency (key, owner_key, user_id, session_id, order_id, request_hash, created_at)
            SELECT key, CASE WHEN user_id IS NOT NULL THEN 'user:' || user_id ELSE 'guest:' || session_id END,
                   user_id, session_id, order_id, request_hash, created_at
            FROM _old_idem
        """)
        db.execute("DROP TABLE _old_idem")
    else:
        db.execute(create_stmt)


def _migrate_new_tables(db) -> None:
    """Tạo product_archives và admin_activity_log nếu DB cũ chưa có."""
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for table_name in ('product_archives', 'admin_activity_log'):
        if table_name not in tables:
            for stmt in _SCHEMA:
                if f'CREATE TABLE {table_name}' in stmt:
                    db.execute(stmt)
                    break


def _preflight_db(database_path, *, required=False) -> None:
    """Chỉ kiểm tra DB quiescent bằng read-only; cho phép upgradable schema hợp lệ."""
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
        is_exact = (version == 2 and objects == _schema_snapshot(reference))
        is_upgradable = (version == 2 and _can_upgrade_schema(db, reference))
        if not (is_exact or is_upgradable):
            raise StorageError('Unsupported storage schema')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise StorageError('Invalid storage data')
    finally:
        db.close()
        if reference is not None:
            reference.close()


def _init_db(database_path: str | pathlib.Path = ':memory:') -> sqlite3.Connection:
    """Atomic schema/catalog; schema cũ được migrate deterministic nếu upgradable."""
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
            if db.execute('PRAGMA user_version').fetchone()[0] == 2 and _schema_snapshot(db) != expected:
                if _can_upgrade_schema(db, reference):
                    db.execute('BEGIN IMMEDIATE')
                    _migrate_order_idempotency(db)
                    _migrate_new_tables(db)
                    db.commit()
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

ORDER_TRANSITIONS = {
    'pending': {'processing', 'shipped'},
    'processing': {'shipped'},
    'completed': {'shipped'},
    'shipped': {'delivered'},
    'delivered': set(),
}


def _validate_price(value: str) -> float:
    """Validate product price (positive, bounded, minor-unit accurate)."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,8}(\.[0-9]{1,2})?', value.strip()):
        raise ValueError('Invalid price')
    cents = _to_minor(value.strip())
    if cents <= 0 or cents > 100_000_000_00:
        raise ValueError('Price out of bounds')
    return _from_minor(cents)


def _validate_stock(value: str) -> int:
    """Validate stock count (integer, >= 0, bounded)."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,8}', value.strip()):
        raise ValueError('Invalid stock')
    stk = int(value.strip())
    if stk < 0 or stk > 1_000_000:
        raise ValueError('Stock out of bounds')
    return stk


# ─────────────────────────────── Helpers ─────────────────────────────────────
def search_products(db: sqlite3.Connection, query: str = "", category: str = "", *, include_archived: bool = False) -> list:
    """Tìm kiếm và lọc đồng thời, dùng tham số SQL và ký tự tìm kiếm literal."""
    if not isinstance(query, str) or len(query) > 200 or not isinstance(category, str):
        raise ValueError("Invalid search input")
    sql = "SELECT p.*, c.name AS cat_name FROM products p JOIN categories c ON p.category_id=c.id"
    conditions = []
    params = []
    if not include_archived:
        sql += " LEFT JOIN product_archives pa ON p.id=pa.product_id"
        conditions.append("pa.product_id IS NULL")
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


def _validate_quantity(value: str) -> int:
    """Số lượng hợp lệ: số nguyên dương từ 1 đến 99, không có ký tự lạ hay leading zero."""
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,1}', value):
        raise ValueError('Invalid quantity')
    qty = int(value)
    if not 1 <= qty <= 99:
        raise ValueError('Invalid quantity')
    return qty


def _to_minor(amount: float | str | Decimal) -> int:
    """Chuyển đổi số tiền sang integer minor units (cents) chính xác, không dùng float division."""
    return int(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)


def _from_minor(cents: int) -> float:
    """Chuyển integer cents về float với 2 chữ số thập phân chuẩn xác cho SQLite storage."""
    return round(cents / 100, 2)


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


def restore_baseline(data_dir: str | pathlib.Path) -> None:
    """Restore ShopLab state to approved seed baseline. Operates strictly within data_dir."""
    with _condition:
        if _database_path is not None or _active:
            raise StorageError('Storage must be closed before restore')
        if not isinstance(data_dir, (str, pathlib.Path)) or not str(data_dir).strip() or '\x00' in str(data_dir) or '..' in pathlib.Path(data_dir).parts or str(data_dir).startswith(('\\\\', '//')):
            raise StorageError('Invalid storage path')
        directory = pathlib.Path(os.path.abspath(data_dir))
        _validate_storage(directory)
        if not directory.is_dir() or not os.access(directory, os.W_OK | os.X_OK):
            raise StorageError('Invalid storage path')
        if hasattr(os, 'geteuid') and (directory.stat().st_uid != os.geteuid() or directory.stat().st_mode & stat.S_IWOTH):
            raise StorageError('Invalid storage ownership')
        for f in directory.glob('shoplab.*'):
            try:
                f.unlink()
            except OSError:
                pass
        inv_dir = directory / 'invoices'
        if inv_dir.is_dir():
            for f in inv_dir.glob('INV-*.txt'):
                try:
                    f.unlink()
                except OSError:
                    pass
        db_path = directory / 'shoplab.sqlite3'
        _preflight_db(db_path, required=False)
        db = _connect(db_path)
        try:
            db.execute('BEGIN IMMEDIATE')
            _create_schema(db)
            db.commit()
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
.badge-processing{{background:#cce5ff;color:#004085}}
.badge-shipped{{background:#d1ecf1;color:#0c5460}}
.badge-delivered{{background:#d4edda;color:#155724}}
.badge-archived{{background:#e2e3e5;color:#383d41}}
.badge-active{{background:#d4edda;color:#155724}}
.stars{{color:#f5a623;font-size:18px}}
footer{{text-align:center;padding:32px;color:#888;font-size:14px;margin-top:48px}}
</style>
</head>
<body>
<div style="background:#2a2b3d;color:#ffc107;text-align:center;padding:6px 12px;font-size:13px;font-weight:600">⚠️ ShopLab — Cyber Range Lab Environment (Simulated / Educational Store)</div>
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

    def _create_invoice_post_commit(self, inv_name: str, full_name: str, address: str, total: float, items_data: list) -> None:
        try:
            inv_path = UPLOAD_DIR / inv_name
            _validate_path(inv_path, directory=False)
            with inv_path.open('x', encoding='utf-8') as invoice:
                invoice.write(
                    f"Invoice: {inv_name}\n"
                    f"Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)\n"
                    f"Name: {full_name}\n"
                    f"Address: {address}\nTotal: ${total:.2f}\n"
                    + "\n".join(f"  {r['name']} x{r['quantity']} @ ${r['price']:.2f}" for r in items_data)
                    + "\n"
                )
        except OSError:
            # Post-commit invoice write failure never rolls back the committed order
            pass

    def _request(self, dispatch, *, write: bool) -> None:
        self._pending_response = None
        self._cached_body = None
        self._identity = None
        self._security_headers = []
        self._post_commit_action = None
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
            action_info = self._post_commit_action
            self._post_commit_action = None
            if action_info is not None:
                action, args = action_info
                try:
                    action(*args)
                except Exception:
                    pass
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

    def _require_admin(self) -> bool:
        if self._role() != "admin":
            self._send_json(403, {'error': 'Admin access required'})
            return False
        return True

    # ── GET dispatcher ────────────────────────────────────────────────────
    def do_GET(self) -> None:
        self._request(self._dispatch_get, write=False)

    def _dispatch_get(self, db) -> None:
        path = urlsplit(self.path).path
        routes = {
            "/":               self._home,
            "/products":       self._products_list,
            "/cart":           self._cart_view,
            "/login":          self._login_form,
            "/register":       self._register_form,
            "/logout":         self._logout_read,
            "/orders":         self._orders_list,
            "/admin":          self._admin_panel,
            "/admin/products": self._admin_panel,
            "/health":         self._health,
        }
        if path in routes:
            routes[path](db)
        elif path.startswith("/admin/orders/"):
            self._admin_order_detail(db, path)
        elif path.startswith("/products/"):
            self._product_detail(db, path)
        elif path.startswith("/orders/"):
            self._order_detail(db, path)
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
            "/login":                  self._login_submit,
            "/register":               self._register_submit,
            "/logout":                 self._logout,
            "/cart/add":               self._cart_add,
            "/cart/update":            self._cart_update,
            "/cart/remove":            self._cart_remove,
            "/checkout":               self._checkout,
            "/reviews":                self._review_submit,
            "/admin/products/add":     self._admin_product_add,
            "/admin/products/update":  self._admin_product_update,
            "/admin/products/archive": self._admin_product_archive,
            "/admin/products/stock":   self._admin_product_stock,
            "/admin/orders/status":    self._admin_order_status,
            "/reset":                  self._reset,
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
        rows = db.execute("SELECT p.*, c.name AS cat_name FROM products p JOIN categories c ON p.category_id=c.id LEFT JOIN product_archives pa ON p.id=pa.product_id WHERE pa.product_id IS NULL LIMIT 6").fetchall()
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
        stock = row["stock"]
        if stock <= 0:
            action_btn = "<span class='badge' style='background:#e0e0e0;color:#666;padding:6px 12px'>Out of stock</span>"
        else:
            action_btn = f"""
            <form method='POST' action='/cart/add' style='display:inline'>
              {self._csrf_field()}
              <input type='hidden' name='product_id' value='{pid}'>
              <input type='hidden' name='quantity' value='1'>
              <button class='btn btn-primary btn-sm'>Add to Cart</button>
            </form>"""
        return f"""
        <div class='product-card'>
          <div class='info'>
            <div class='cat'>{cat}</div>
            <div class='name'>{name}</div>
            <div class='price'>{price}</div>
            <a href='/products/{pid}' class='btn btn-secondary btn-sm'>View Details</a>
            &nbsp;
            {action_btn}
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
        archived = db.execute("SELECT 1 FROM product_archives WHERE product_id=?", (pid,)).fetchone() is not None
        if archived:
            purchase_html = "<div class='alert' style='background:#f0f0f0;color:#666'>This product has been archived and is no longer available for purchase.</div>"
            review_form = ""
        elif row["stock"] <= 0:
            purchase_html = "<p style='color:#888'>This product is currently out of stock.</p>"
        else:
            purchase_html = f"""<form method='POST' action='/cart/add'>
                {self._csrf_field()}
                <input type='hidden' name='product_id' value='{pid}'>
                <div style='display:flex;gap:12px;align-items:center;flex-wrap:wrap'>
                  <input name='quantity' type='number' value='1' min='1' max='{row["stock"]}' style='width:80px'>
                  <button class='btn btn-primary'>Add to Cart</button>
                </div>
              </form>"""

        if u and not archived:
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
              <p style='color:#888;font-size:14px;margin-bottom:16px'>{"<span class='badge badge-archived'>Archived</span>" if archived else ("<span style='color:#c00;font-weight:600'>Out of stock</span>" if row["stock"] <= 0 else f"{row['stock']} in stock")}</p>
              {purchase_html}
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
            SELECT c.id, c.quantity, p.name, p.price, p.id AS pid, p.stock, pa.product_id AS is_archived
            FROM cart c JOIN products p ON c.product_id=p.id
            LEFT JOIN product_archives pa ON p.id=pa.product_id
            WHERE c.session_id=?""", (sid,)).fetchall()
        if not rows:
            body = "<div class='card'><h2>Your Cart</h2><p>Your cart is empty. <a href='/products'>Shop now →</a></p></div>"
        else:
            total_cents = 0
            items_html = []
            has_stale_stock = False
            for r in rows:
                unit_cents = _to_minor(r["price"])
                sub_cents = unit_cents * r["quantity"]
                total_cents += sub_cents
                sub_float = _from_minor(sub_cents)
                stale_msg = ""
                if r["is_archived"] is not None:
                    has_stale_stock = True
                    stale_msg = "<div style='color:#c00;font-size:12px'>⚠️ Product archived / unavailable</div>"
                elif r["stock"] < r["quantity"]:
                    has_stale_stock = True
                    stale_msg = f"<div style='color:#c00;font-size:12px'>⚠️ Only {r['stock']} available</div>" if r['stock'] > 0 else "<div style='color:#c00;font-size:12px'>⚠️ Out of stock</div>"
                items_html.append(f"""
                <tr>
                  <td><a href='/products/{r["pid"]}'>{html_escape(r["name"])}</a>{stale_msg}</td>
                  <td>${r["price"]:.2f}</td>
                  <td>
                    <form method='POST' action='/cart/update' style='display:flex;align-items:center;gap:6px'>
                      {self._csrf_field()}
                      <input type='hidden' name='cart_id' value='{r["id"]}'>
                      <input type='number' name='quantity' value='{r["quantity"]}' min='1' max='{min(99, max(1, r["stock"]))}' style='width:65px;margin-bottom:0'>
                      <button class='btn btn-secondary btn-sm'>Update</button>
                    </form>
                  </td>
                  <td>${sub_float:.2f}</td>
                  <td>
                    <form method='POST' action='/cart/remove' style='display:inline'>
                      {self._csrf_field()}
                      <input type='hidden' name='cart_id' value='{r["id"]}'>
                      <button class='btn btn-secondary btn-sm'>Remove</button>
                    </form>
                  </td>
                </tr>""")
            total = _from_minor(total_cents)
            items_rows = "".join(items_html)
            checkout_btn = f"<button class='btn btn-primary' style='margin-top:8px'>Place Order (${total:.2f})</button>" if not has_stale_stock else "<div class='alert alert-error' style='margin-top:8px'>Some items have insufficient stock. Please update quantities before checkout.</div>"
            body = f"""
            <div class='card'>
              <h2>Your Cart</h2>
              <table style='margin:16px 0'>
                <tr><th>Product</th><th>Price</th><th>Qty</th><th>Subtotal</th><th></th></tr>
                {items_rows}
              </table>
              <div style='text-align:right;font-size:20px;font-weight:700;margin:16px 0'>
                Total: <span style='color:#e94560'>${total:.2f}</span>
              </div>
              <form method='POST' action='/checkout'>
                {self._csrf_field()}
                <input type='hidden' name='idempotency_key' value='{secrets.token_hex(16)}'>
                <h3 style='margin-bottom:12px'>Shipping Information</h3>
                <label>Full Name</label><input name='full_name' placeholder='John Doe' required>
                <label>Address</label><input name='address' placeholder='123 Main St, City' required>
                <label>Email</label><input name='email' type='email' placeholder='you@example.com' required>
                {checkout_btn}
              </form>
            </div>"""
        self._send(200, _render("Cart", body, self._nav()))

    def _cart_add(self, db) -> None:
        f = self._form()
        sid = self._session()
        pid = _positive_id(f.get('product_id', '0'))
        qty = _validate_quantity(f.get('quantity', '1'))
        product = db.execute(
            'SELECT p.stock, pa.product_id AS is_archived FROM products p '
            'LEFT JOIN product_archives pa ON p.id=pa.product_id WHERE p.id=?', (pid,)
        ).fetchone()
        if product is None or product['is_archived'] is not None:
            self._send_json(409, {'error': 'Product unavailable'}); return
        if product['stock'] <= 0:
            self._send_json(409, {'error': 'Product is out of stock'}); return
        existing = db.execute('SELECT id, quantity FROM cart WHERE session_id=? AND product_id=?', (sid, pid)).fetchone()
        total = qty + (existing['quantity'] if existing else 0)
        if total > min(99, product['stock']):
            raise ValueError('Invalid quantity')
        if not existing and db.execute('SELECT count(*) FROM cart WHERE session_id=?', (sid,)).fetchone()[0] >= 50:
            raise ValueError('Cart limit')
        if existing:
            db.execute("UPDATE cart SET quantity=? WHERE id=?", (total, existing["id"]))
        else:
            db.execute("INSERT INTO cart (session_id, product_id, quantity) VALUES (?,?,?)", (sid, pid, qty))
        self._redirect('/cart')

    def _cart_update(self, db) -> None:
        f = self._form()
        sid = self._session()
        cart_id = _positive_id(f.get('cart_id', '0'))
        qty = _validate_quantity(f.get('quantity', ''))
        item = db.execute(
            "SELECT c.id, c.product_id, p.stock FROM cart c JOIN products p ON c.product_id=p.id WHERE c.id=? AND c.session_id=?",
            (cart_id, sid)
        ).fetchone()
        if item is None:
            self._send_json(404, {'error': 'Cart item not found'}); return
        if qty > min(99, item['stock']):
            raise ValueError('Invalid quantity')
        db.execute("UPDATE cart SET quantity=? WHERE id=? AND session_id=?", (qty, cart_id, sid))
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
        f = self._form()
        uid = self._identity['user_id']
        owner_key = f"user:{uid}" if uid is not None else f"guest:{sid}"

        idem_key = (
            _header(self, 'Idempotency-Key')
            or _header(self, 'X-Idempotency-Key')
            or f.get('idempotency_key', '')
        ).strip()
        if idem_key and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', idem_key):
            raise ValueError('Invalid idempotency key')

        full_name = f.get('full_name', '').strip()
        address = f.get('address', '').strip()
        email = f.get('email', '').strip()
        if len(full_name) > 100 or len(address) > 200:
            raise ValueError('Invalid shipping details')
        if email and not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', email):
            raise ValueError('Invalid email')

        req_hash = hashlib.sha256(f"{full_name}|{address}|{email}".encode('utf-8')).hexdigest()

        if idem_key:
            existing_record = db.execute(
                "SELECT order_id, request_hash FROM order_idempotency WHERE key=? AND owner_key=?",
                (idem_key, owner_key)
            ).fetchone()
            if existing_record is not None:
                if existing_record['request_hash'] == req_hash:
                    order = db.execute("SELECT * FROM orders WHERE id=?", (existing_record['order_id'],)).fetchone()
                    if order is None:
                        self._send_json(404, {'error': 'Order not found'}); return
                    body = f"""
                    <div class='card' style='text-align:center;padding:48px'>
                      <div style='font-size:64px'>✅</div>
                      <h2 style='margin:16px 0'>Order Placed Successfully!</h2>
                      <p>Order #{order['id']} &bull; Total: <strong>${order['total']:.2f}</strong></p>
                      <p style='margin:12px 0;color:#555'>Lab order only: no payment was charged and no email was sent. Contact: {html_escape(email)}.</p>
                      <a href='/download/invoice?file={order["invoice_file"]}' class='btn btn-secondary' style='margin-top:16px'>Download Invoice</a>
                      &nbsp;
                      <a href='/products' class='btn btn-primary' style='margin-top:16px'>Continue Shopping</a>
                    </div>"""
                    self._send(200, _render("Order Confirmed", body, self._nav()))
                    return
                else:
                    self._send_json(409, {'error': 'Idempotency key conflict: different request payload'})
                    return

        items = db.execute("""
            SELECT c.quantity, p.price, p.id AS pid, p.name, p.stock, pa.product_id AS is_archived
            FROM cart c JOIN products p ON c.product_id=p.id
            LEFT JOIN product_archives pa ON p.id=pa.product_id
            WHERE c.session_id=?""", (sid,)).fetchall()
        if not items:
            self._redirect("/cart"); return

        for r in items:
            if r['is_archived'] is not None:
                self._send_json(409, {'error': f"Product '{r['name']}' is no longer available"}); return
            if r['stock'] < r['quantity']:
                self._send_json(409, {'error': f"Insufficient stock for '{r['name']}': {r['stock']} available, {r['quantity']} requested"})
                return

        total_cents = 0
        for r in items:
            unit_cents = _to_minor(r["price"])
            subtotal_cents = unit_cents * r["quantity"]
            total_cents += subtotal_cents
        total = _from_minor(total_cents)

        inv_name = f"INV-{uuid.uuid4().hex.upper()}.txt"

        for r in items:
            cur = db.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (r['quantity'], r['pid'], r['quantity'])
            )
            if cur.rowcount != 1:
                raise sqlite3.IntegrityError(f"Insufficient stock for product {r['pid']}")

        cur = db.execute(
            "INSERT INTO orders (user_id, session_id, total, currency, status, invoice_file) VALUES (?,?,?,?,?,?)",
            (uid, sid, total, SHOPLAB_CURRENCY, "completed", inv_name)
        )
        order_id = cur.lastrowid

        for r in items:
            db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, currency) VALUES (?,?,?,?,?)",
                (order_id, r["pid"], r["quantity"], _from_minor(_to_minor(r["price"])), SHOPLAB_CURRENCY)
            )

        if idem_key:
            db.execute(
                "INSERT INTO order_idempotency (key, owner_key, user_id, session_id, order_id, request_hash, created_at) VALUES (?,?,?,?,?,?,?)",
                (idem_key, owner_key, uid, sid, order_id, req_hash, _now())
            )

        db.execute("DELETE FROM cart WHERE session_id=?", (sid,))

        # Post-commit invoice generation: filesystem side effect tách biệt khỏi DB transaction
        items_data = [{'name': r['name'], 'quantity': r['quantity'], 'price': r['price']} for r in items]
        self._post_commit_action = (self._create_invoice_post_commit, (inv_name, full_name, address, total, items_data))

        body = f"""
        <div class='card' style='text-align:center;padding:48px'>
          <div style='font-size:64px'>✅</div>
          <h2 style='margin:16px 0'>Order Placed Successfully!</h2>
          <p>Order #{order_id} &bull; Total: <strong>${total:.2f}</strong></p>
          <p style='margin:12px 0;color:#555'>Lab order only: no payment was charged and no email was sent. Contact: {html_escape(email)}.</p>
          <a href='/download/invoice?file={inv_name}' class='btn btn-secondary' style='margin-top:16px'>Download Invoice</a>
          &nbsp;
          <a href='/products' class='btn btn-primary' style='margin-top:16px'>Continue Shopping</a>
        </div>"""
        self._send(200, _render("Order Confirmed", body, self._nav()))

    # ── Reviews ───────────────────────────────────────────────────────────
    def _review_submit(self, db) -> None:
        if not self._require_user():
            return
        f = self._form()
        u = self._username()
        raw_pid = f.get("product_id", "")
        try:
            pid = _positive_id(raw_pid)
        except ValueError:
            self._send_json(400, {'error': 'Invalid product ID'}); return
        prod = db.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()
        if prod is None:
            self._send_json(404, {'error': 'Product not found'}); return

        raw_rating = f.get("rating", "")
        try:
            rating = int(raw_rating)
            if rating < 1 or rating > 5 or str(rating) != raw_rating.strip():
                raise ValueError()
        except (ValueError, TypeError):
            self._send_json(400, {'error': 'Rating must be an integer between 1 and 5'}); return

        body_text = f.get("body", "").strip()
        if not body_text:
            self._send_json(400, {'error': 'Review body cannot be empty'}); return
        if len(body_text) > 4000:
            self._send_json(400, {'error': 'Review is too long'}); return

        uid = self._identity['user_id']
        db.execute("INSERT INTO reviews (product_id, user_id, username, rating, body) VALUES (?,?,?,?,?)",
                   (pid, uid, u, rating, body_text))
        self._redirect(f"/products/{pid}")

    # ── Invoice download ──────────────────────────────────────────────────
    def _download_invoice(self, db) -> None:
        filename = self._p('file')
        if not re.fullmatch(r'INV-[A-F0-9]{32}\.txt', filename):
            self._send_json(400, {'error': 'Invalid invoice name'}); return
        order = db.execute('SELECT * FROM orders WHERE invoice_file=?', (filename,)).fetchone()
        if not owns_order(self._identity, order):
            self._send_json(404, {'error': 'Not found'}); return
        filepath = UPLOAD_DIR / filename
        if filepath.is_file():
            _validate_path(filepath, directory=False)
            try:
                content = filepath.read_text(encoding='utf-8')
                self._send(200, content, "text/plain")
                return
            except OSError:
                self._send_json(503, {'error': 'Storage is unavailable'})
                return
        # Dynamic on-demand fallback từ DB order items nếu file chưa ghi
        order_items = db.execute(
            'SELECT oi.quantity, oi.unit_price, p.name FROM order_items oi '
            'JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?', (order['id'],)
        ).fetchall()
        content = (
            f"Invoice: {filename}\n"
            f"Notice: ShopLab — Lab / Simulated Order Receipt (No payment charged)\n"
            f"Total: ${order['total']:.2f}\n"
            + "\n".join(f"  {r['name']} x{r['quantity']} @ ${r['unit_price']:.2f}" for r in order_items)
            + "\n"
        )
        self._send(200, content, "text/plain")

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
          <td><a href='/orders/{r["id"]}'>#{r["id"]}</a></td>
          <td>${r["total"]:.2f}</td>
          <td><span class='badge badge-{html_escape(r["status"] or '')}'>{html_escape(r["status"] or '')}</span></td>
          <td>{html_escape(r["created_at"] or '')}</td>
          <td>
            <a href='/orders/{r["id"]}' class='btn btn-secondary btn-sm'>Detail</a>
            <a href='/download/invoice?file={html_escape(urlencode({'file': r['invoice_file'] or ''})[5:])}' class='btn btn-secondary btn-sm'>Invoice</a>
          </td>
        </tr>""" for r in orders)
        body = f"""
        <div class='card'>
          <h2>My Orders</h2>
          {"<table style='margin-top:16px'><tr><th>#</th><th>Total</th><th>Status</th><th>Date</th><th>Actions</th></tr>" + rows_html + "</table>" if orders else "<p>No orders yet.</p>"}
        </div>"""
        self._send(200, _render("My Orders", body, self._nav()))

    def _order_detail(self, db, path: str) -> None:
        if self._identity is None:
            self._send_json(403, {'error': 'Request is not authorized'}); return
        raw_id = path.removeprefix("/orders/").strip()
        try:
            oid = _positive_id(raw_id)
        except ValueError:
            self._send(404, _render("Not Found", "<div class='card'><h2>Order not found</h2></div>")); return
        order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if order is None or not owns_order(self._identity, order):
            self._send(404, _render("Not Found", "<div class='card'><h2>Order not found</h2></div>")); return
        items = db.execute(
            "SELECT oi.quantity, oi.unit_price, oi.currency, p.name FROM order_items oi "
            "JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ).fetchall()
        items_html = "".join(f"""
        <tr>
          <td>{html_escape(item['name'])}</td>
          <td>${item['unit_price']:.2f}</td>
          <td>{item['quantity']}</td>
          <td>${item['unit_price'] * item['quantity']:.2f}</td>
        </tr>""" for item in items)
        inv_link = ""
        if order['invoice_file']:
            inv_link = f"<a href='/download/invoice?file={html_escape(order['invoice_file'])}' class='btn btn-secondary' style='margin-right:8px'>Download Invoice</a>"
        body = f"""
        <div class='card'>
          <h2>Order #{order['id']}</h2>
          <p style='color:#666;margin:8px 0'>Date: {html_escape(order['created_at'] or '')} &bull; Status: <span class='badge badge-{html_escape(order['status'] or '')}'>{html_escape(order['status'] or '')}</span></p>
          <table style='margin:16px 0'>
            <tr><th>Product</th><th>Unit Price</th><th>Quantity</th><th>Subtotal</th></tr>
            {items_html}
          </table>
          <p style='font-size:18px;margin-top:16px'><strong>Total: ${order['total']:.2f} {html_escape(order['currency'] or 'USD')}</strong></p>
          <p style='color:#888;font-size:13px;margin-top:8px'>Lab order snapshot: amounts and items are immutable historical records.</p>
          <div style='margin-top:16px'>
            {inv_link}
            <a href='/orders' class='btn btn-secondary'>← Back to Orders</a>
          </div>
        </div>"""
        self._send(200, _render(f"Order #{order['id']}", body, self._nav()))

    # ── Admin panel ───────────────────────────────────────────────────────
    def _admin_panel(self, db) -> None:
        if self._role() != "admin":
            self._send(403, _render("Forbidden", "<div class='card'><h2>403 Forbidden</h2><p>Admin access required. <a href='/login'>Login</a></p></div>"))
            return
        categories = db.execute("SELECT id, name FROM categories ORDER BY id").fetchall()
        products = db.execute("""
            SELECT p.*, c.name AS cat_name, pa.archived_at
            FROM products p
            JOIN categories c ON p.category_id=c.id
            LEFT JOIN product_archives pa ON p.id=pa.product_id
            ORDER BY p.id DESC
        """).fetchall()
        orders = db.execute("SELECT o.*, u.username FROM orders o LEFT JOIN users u ON o.user_id=u.id ORDER BY o.id DESC").fetchall()
        users = db.execute("SELECT id, username, email, role FROM users ORDER BY id").fetchall()
        activity = db.execute("""
            SELECT a.*, u.username
            FROM admin_activity_log a
            LEFT JOIN users u ON a.user_id=u.id
            ORDER BY a.id DESC LIMIT 30
        """).fetchall()

        cat_options = "".join(f'<option value="{c["id"]}">{html_escape(c["name"])}</option>' for c in categories)

        prod_rows = []
        for p in products:
            status_badge = "<span class='badge badge-archived'>Archived</span>" if p['archived_at'] else "<span class='badge badge-active'>Active</span>"
            archive_action = ""
            if not p['archived_at']:
                archive_action = f"""
                <form method='POST' action='/admin/products/archive' style='display:inline'>
                  {self._csrf_field()}
                  <input type='hidden' name='product_id' value='{p["id"]}'>
                  <button class='btn btn-secondary btn-sm'>Archive</button>
                </form>"""
            stock_form = f"""
            <form method='POST' action='/admin/products/stock' style='display:flex;align-items:center;gap:6px'>
              {self._csrf_field()}
              <input type='hidden' name='product_id' value='{p["id"]}'>
              <input type='hidden' name='expected_stock' value='{p["stock"]}'>
              <input type='number' name='stock' value='{p["stock"]}' min='0' max='1000000' style='width:65px;margin-bottom:0'>
              <button class='btn btn-secondary btn-sm'>Set</button>
            </form>"""
            prod_rows.append(f"""
            <tr>
              <td>#{p['id']}</td>
              <td><strong>{html_escape(p['name'])}</strong></td>
              <td>{html_escape(p['cat_name'])}</td>
              <td>${p['price']:.2f}</td>
              <td>{stock_form}</td>
              <td>{status_badge}</td>
              <td>{archive_action}</td>
            </tr>""")

        order_rows = []
        for o in orders:
            order_rows.append(f"""
            <tr>
              <td><a href='/admin/orders/{o["id"]}'>#{o["id"]}</a></td>
              <td>{html_escape(o['username'] or 'guest')}</td>
              <td>${o['total']:.2f}</td>
              <td><span class='badge badge-{html_escape(o["status"] or "")}'>{html_escape(o["status"] or "")}</span></td>
              <td>{html_escape(o['created_at'] or '')}</td>
              <td><a href='/admin/orders/{o["id"]}' class='btn btn-secondary btn-sm'>Manage</a></td>
            </tr>""")

        user_rows = [f"<tr><td>{u['id']}</td><td>{html_escape(u['username'])}</td><td>{html_escape(u['email'] or '')}</td><td><span class='badge badge-{u['role']}'>{u['role']}</span></td></tr>" for u in users]
        act_rows = [f"<tr><td>{html_escape(a['created_at'])}</td><td>{html_escape(a['username'] or 'system')}</td><td><code>{html_escape(a['action'])}</code></td><td>{html_escape(a['target_type'])} #{a['target_id']}</td><td>{html_escape(a['old_value'] or '')} → {html_escape(a['new_value'] or '')}</td></tr>" for a in activity]

        body = f"""
        <div class='card'>
          <h2>🔑 Admin Dashboard</h2>
          <p style='color:#666;margin-bottom:20px'>Logged in as administrator &bull; Lab simulated operations</p>
          <div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px'>
            <a href='#products' class='btn btn-secondary btn-sm'>Products ({len(products)})</a>
            <a href='#add-product' class='btn btn-primary btn-sm'>+ Add Product</a>
            <a href='#orders' class='btn btn-secondary btn-sm'>Orders ({len(orders)})</a>
            <a href='#users' class='btn btn-secondary btn-sm'>Users ({len(users)})</a>
            <a href='#activity' class='btn btn-secondary btn-sm'>Audit Log ({len(activity)})</a>
          </div>
        </div>

        <div class='card' id='add-product' style='margin-bottom:24px'>
          <h3>+ Add New Product</h3>
          <form method='POST' action='/admin/products/add' style='margin-top:16px'>
            {self._csrf_field()}
            <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px'>
              <div>
                <label for='prod_name'>Product Name</label>
                <input id='prod_name' name='name' required placeholder='e.g. Ergonomic Keyboard'>
              </div>
              <div>
                <label for='prod_cat'>Category</label>
                <select id='prod_cat' name='category_id' required>
                  {cat_options}
                </select>
              </div>
              <div>
                <label for='prod_price'>Price (USD)</label>
                <input id='prod_price' name='price' type='text' required placeholder='49.99'>
              </div>
              <div>
                <label for='prod_stock'>Initial Stock</label>
                <input id='prod_stock' name='stock' type='number' min='0' max='1000000' value='10' required>
              </div>
            </div>
            <label for='prod_desc'>Description</label>
            <textarea id='prod_desc' name='description' rows='3' placeholder='Product details...'></textarea>
            <button class='btn btn-primary'>Create Product</button>
          </form>
        </div>

        <div class='card' id='products' style='margin-bottom:24px'>
          <h3>Catalog Products ({len(products)})</h3>
          {"<table style='margin-top:16px'><tr><th>ID</th><th>Name</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Actions</th></tr>" + "".join(prod_rows) + "</table>" if products else "<p style='color:#666;margin-top:12px'>No products in catalog.</p>"}
        </div>

        <div class='card' id='orders' style='margin-bottom:24px'>
          <h3>All Orders ({len(orders)})</h3>
          {"<table style='margin-top:16px'><tr><th>#</th><th>User</th><th>Total</th><th>Status</th><th>Date</th><th>Actions</th></tr>" + "".join(order_rows) + "</table>" if orders else "<p style='color:#666;margin-top:12px'>No orders recorded yet.</p>"}
        </div>

        <div class='card' id='users' style='margin-bottom:24px'>
          <h3>Users ({len(users)})</h3>
          {"<table style='margin-top:16px'><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th></tr>" + "".join(user_rows) + "</table>" if users else "<p style='color:#666;margin-top:12px'>No registered users yet.</p>"}
        </div>

        <div class='card' id='activity'>
          <h3>Recent Admin Activity Log ({len(activity)})</h3>
          {"<table style='margin-top:16px'><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Target</th><th>Details</th></tr>" + "".join(act_rows) + "</table>" if activity else "<p style='color:#666;margin-top:12px'>No admin activity recorded yet.</p>"}
        </div>"""
        self._send(200, _render("Admin", body, self._nav()))

    def _admin_order_detail(self, db, path: str) -> None:
        if self._role() != "admin":
            self._send(403, _render("Forbidden", "<div class='card'><h2>403 Forbidden</h2><p>Admin access required.</p></div>")); return
        raw_id = path.removeprefix("/admin/orders/").strip()
        try:
            oid = _positive_id(raw_id)
        except ValueError:
            self._send(404, _render("Not Found", "<div class='card'><h2>Order not found</h2></div>")); return
        order = db.execute("SELECT o.*, u.username, u.email FROM orders o LEFT JOIN users u ON o.user_id=u.id WHERE o.id=?", (oid,)).fetchone()
        if order is None:
            self._send(404, _render("Not Found", "<div class='card'><h2>Order not found</h2></div>")); return

        items = db.execute(
            "SELECT oi.quantity, oi.unit_price, oi.currency, p.name FROM order_items oi "
            "JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ).fetchall()
        items_html = "".join(f"""
        <tr>
          <td>{html_escape(item['name'])}</td>
          <td>${item['unit_price']:.2f}</td>
          <td>{item['quantity']}</td>
          <td>${item['unit_price'] * item['quantity']:.2f}</td>
        </tr>""" for item in items)

        curr_status = order['status'] or 'pending'
        valid_next = ORDER_TRANSITIONS.get(curr_status, set())
        options_html = "".join(f"<option value='{s}'>{s.title()}</option>" for s in sorted(valid_next))

        status_form = ""
        if valid_next:
            status_form = f"""
            <form method='POST' action='/admin/orders/status' style='margin-top:16px'>
              {self._csrf_field()}
              <input type='hidden' name='order_id' value='{oid}'>
              <label>Update Status</label>
              <div style='display:flex;gap:12px;align-items:center'>
                <select name='status' style='max-width:200px;margin-bottom:0'>
                  {options_html}
                </select>
                <button class='btn btn-primary btn-sm'>Update Status</button>
              </div>
            </form>"""
        else:
            status_form = "<p style='color:#666;margin-top:12px'>Terminal state: no further transitions allowed.</p>"

        history = db.execute(
            "SELECT * FROM admin_activity_log WHERE target_type='order' AND target_id=? ORDER BY id DESC",
            (oid,)
        ).fetchall()
        history_rows = "".join(f"<tr><td>{html_escape(h['created_at'])}</td><td>{html_escape(h['old_value'] or '')} → {html_escape(h['new_value'] or '')}</td></tr>" for h in history)
        history_table = f"<h4 style='margin-top:20px'>Status History</h4><table style='margin-top:8px'><tr><th>Timestamp</th><th>Change</th></tr>{history_rows}</table>" if history else ""

        body = f"""
        <div class='card'>
          <a href='/admin#orders' style='color:#e94560;text-decoration:none;font-size:14px'>← Back to Admin Orders</a>
          <h2 style='margin:16px 0 8px'>Admin Order #{order['id']}</h2>
          <p style='color:#555'>Customer: <strong>{html_escape(order['username'] or 'guest')}</strong> ({html_escape(order['email'] or 'N/A')})</p>
          <p style='color:#666;margin:8px 0'>Date: {html_escape(order['created_at'] or '')} &bull; Status: <span class='badge badge-{html_escape(curr_status)}'>{html_escape(curr_status)}</span></p>
          <table style='margin:16px 0'>
            <tr><th>Product</th><th>Unit Price</th><th>Quantity</th><th>Subtotal</th></tr>
            {items_html}
          </table>
          <p style='font-size:18px;margin-top:16px'><strong>Total: ${order['total']:.2f} {html_escape(order['currency'] or 'USD')}</strong></p>
          {status_form}
          {history_table}
        </div>"""
        self._send(200, _render(f"Admin Order #{oid}", body, self._nav()))

    def _admin_product_add(self, db) -> None:
        if not self._require_admin():
            return
        f = self._form()
        name = f.get('name', '').strip()
        if not name or len(name) > 200:
            self._send_json(400, {'error': 'Product name must be between 1 and 200 characters'}); return
        desc = f.get('description', '').strip()
        if len(desc) > 2000:
            self._send_json(400, {'error': 'Description must be at most 2000 characters'}); return
        raw_cat = f.get('category_id', '')
        try:
            cat_id = _positive_id(raw_cat)
        except ValueError:
            self._send_json(400, {'error': 'Invalid category ID'}); return
        cat = db.execute("SELECT id FROM categories WHERE id=?", (cat_id,)).fetchone()
        if cat is None:
            self._send_json(400, {'error': 'Category does not exist'}); return
        raw_price = f.get('price', '')
        try:
            price = _validate_price(raw_price)
        except ValueError:
            self._send_json(400, {'error': 'Invalid price'}); return
        raw_stock = f.get('stock', '')
        try:
            stock = _validate_stock(raw_stock)
        except ValueError:
            self._send_json(400, {'error': 'Invalid stock'}); return

        cur = db.execute(
            "INSERT INTO products (name, description, price, currency, category_id, stock) VALUES (?,?,?,?,?,?)",
            (name, desc, price, SHOPLAB_CURRENCY, cat_id, stock)
        )
        new_id = cur.lastrowid
        db.execute(
            "INSERT INTO admin_activity_log (user_id, action, target_type, target_id, new_value, created_at) VALUES (?,?,?,?,?,?)",
            (self._identity['user_id'], 'create_product', 'product', new_id, f"name={name}, price={price}, stock={stock}", datetime.now(timezone.utc).isoformat())
        )
        self._redirect('/admin#products')

    def _admin_product_update(self, db) -> None:
        if not self._require_admin():
            return
        f = self._form()
        try:
            pid = _positive_id(f.get('product_id', ''))
        except ValueError:
            self._send_json(400, {'error': 'Invalid product ID'}); return
        prod = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if prod is None:
            self._send_json(404, {'error': 'Product not found'}); return

        name = f.get('name', prod['name']).strip()
        if not name or len(name) > 200:
            self._send_json(400, {'error': 'Product name must be between 1 and 200 characters'}); return
        desc = f.get('description', prod['description'] or '').strip()
        if len(desc) > 2000:
            self._send_json(400, {'error': 'Description must be at most 2000 characters'}); return

        cat_id = prod['category_id']
        if 'category_id' in f and f['category_id'].strip():
            try:
                cat_id = _positive_id(f['category_id'])
            except ValueError:
                self._send_json(400, {'error': 'Invalid category ID'}); return
            if db.execute("SELECT id FROM categories WHERE id=?", (cat_id,)).fetchone() is None:
                self._send_json(400, {'error': 'Category does not exist'}); return

        price = prod['price']
        if 'price' in f and f['price'].strip():
            try:
                price = _validate_price(f['price'])
            except ValueError:
                self._send_json(400, {'error': 'Invalid price'}); return

        stock = prod['stock']
        expected_stock = None
        if 'expected_stock' in f and f['expected_stock'].strip():
            try:
                expected_stock = _validate_stock(f['expected_stock'])
            except ValueError:
                self._send_json(400, {'error': 'Invalid expected stock'}); return

        if 'stock' in f and f['stock'].strip():
            try:
                stock = _validate_stock(f['stock'])
            except ValueError:
                self._send_json(400, {'error': 'Invalid stock'}); return

        if expected_stock is not None:
            cur = db.execute(
                "UPDATE products SET name=?, description=?, price=?, category_id=?, stock=? WHERE id=? AND stock=?",
                (name, desc, price, cat_id, stock, pid, expected_stock)
            )
            if cur.rowcount == 0:
                self._send_json(409, {'error': 'Stock has changed concurrently, please refresh and retry'}); return
        else:
            db.execute(
                "UPDATE products SET name=?, description=?, price=?, category_id=?, stock=? WHERE id=?",
                (name, desc, price, cat_id, stock, pid)
            )

        db.execute(
            "INSERT INTO admin_activity_log (user_id, action, target_type, target_id, old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?)",
            (self._identity['user_id'], 'update_product', 'product', pid, f"stock={prod['stock']}, price={prod['price']}", f"stock={stock}, price={price}", datetime.now(timezone.utc).isoformat())
        )
        self._redirect('/admin#products')

    def _admin_product_archive(self, db) -> None:
        if not self._require_admin():
            return
        f = self._form()
        try:
            pid = _positive_id(f.get('product_id', ''))
        except ValueError:
            self._send_json(400, {'error': 'Invalid product ID'}); return
        prod = db.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone()
        if prod is None:
            self._send_json(404, {'error': 'Product not found'}); return

        if db.execute("SELECT 1 FROM product_archives WHERE product_id=?", (pid,)).fetchone() is not None:
            self._redirect('/admin#products'); return

        db.execute("INSERT INTO product_archives (product_id, archived_at) VALUES (?,?)",
                   (pid, datetime.now(timezone.utc).isoformat()))
        db.execute(
            "INSERT INTO admin_activity_log (user_id, action, target_type, target_id, created_at) VALUES (?,?,?,?,?)",
            (self._identity['user_id'], 'archive_product', 'product', pid, datetime.now(timezone.utc).isoformat())
        )
        self._redirect('/admin#products')

    def _admin_product_stock(self, db) -> None:
        if not self._require_admin():
            return
        f = self._form()
        try:
            pid = _positive_id(f.get('product_id', ''))
        except ValueError:
            self._send_json(400, {'error': 'Invalid product ID'}); return
        prod = db.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()
        if prod is None:
            self._send_json(404, {'error': 'Product not found'}); return
        try:
            new_stock = _validate_stock(f.get('stock', ''))
        except ValueError:
            self._send_json(400, {'error': 'Invalid stock value'}); return

        expected_stock = None
        if 'expected_stock' in f and f['expected_stock'].strip():
            try:
                expected_stock = _validate_stock(f['expected_stock'])
            except ValueError:
                self._send_json(400, {'error': 'Invalid expected stock'}); return

        if expected_stock is not None:
            cur = db.execute(
                "UPDATE products SET stock=? WHERE id=? AND stock=?",
                (new_stock, pid, expected_stock)
            )
            if cur.rowcount == 0:
                self._send_json(409, {'error': 'Stock has changed concurrently, please refresh and retry'}); return
        else:
            db.execute("UPDATE products SET stock=? WHERE id=? AND stock>=0", (new_stock, pid))

        db.execute(
            "INSERT INTO admin_activity_log (user_id, action, target_type, target_id, old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?)",
            (self._identity['user_id'], 'stock_update', 'product', pid, str(prod['stock']), str(new_stock), datetime.now(timezone.utc).isoformat())
        )
        self._redirect('/admin#products')

    def _admin_order_status(self, db) -> None:
        if not self._require_admin():
            return
        f = self._form()
        try:
            oid = _positive_id(f.get('order_id', ''))
        except ValueError:
            self._send_json(400, {'error': 'Invalid order ID'}); return
        new_status = f.get('status', '').strip().lower()
        if not new_status:
            self._send_json(400, {'error': 'Status cannot be empty'}); return

        order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if order is None:
            self._send_json(404, {'error': 'Order not found'}); return

        curr_status = order['status'] or 'pending'
        if new_status == curr_status:
            self._redirect(f"/admin/orders/{oid}"); return

        valid_transitions = ORDER_TRANSITIONS.get(curr_status, set())
        if new_status not in valid_transitions:
            self._send_json(400, {'error': f"Invalid status transition from '{curr_status}' to '{new_status}'"}); return

        db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
        db.execute(
            "INSERT INTO admin_activity_log (user_id, action, target_type, target_id, old_value, new_value, created_at) VALUES (?,?,?,?,?,?,?)",
            (self._identity['user_id'], 'order_status_update', 'order', oid, curr_status, new_status, datetime.now(timezone.utc).isoformat())
        )
        self._redirect(f"/admin/orders/{oid}")

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
