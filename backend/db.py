import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "var" / "doaide.db"


@contextmanager
def database(path=None):
    target = Path(path or os.environ.get("DOAIDE_DB_PATH", DEFAULT_PATH))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(target, timeout=15)
    os.chmod(target, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path=None):
    with database(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            product TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft', 'reviewed', 'archived')),
            version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS records_owner_product ON records(user_id, product, updated_at DESC);
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id),
            user_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL,
            version INTEGER NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_attempts (ip TEXT NOT NULL, at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS attempts_ip_time ON auth_attempts(ip, at);
        """)
        from .migrations import migrate
        migrate(db)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def password_matches(password, encoded):
    _, salt, _ = encoded.split("$")
    return secrets.compare_digest(password_hash(password, salt), encoded)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
