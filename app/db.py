"""SQLite access (standard library) and a tiny versioned migration runner."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import env

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    path = env().database_path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit; we use explicit BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


@contextmanager
def db():
    """Yield a connection. Wrap multi-statement writes in `with tx(conn):`."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def tx(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrate() -> list[str]:
    """Apply any migration files not yet recorded. Returns the versions applied."""
    applied: list[str] = []
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
            version = fname[:-4]
            if version in done:
                continue
            with open(os.path.join(MIGRATIONS_DIR, fname), encoding="utf-8") as fh:
                sql = fh.read()
            # executescript commits implicitly, so run each file inside an explicit transaction block.
            conn.executescript("BEGIN;\n" + sql + "\n" + f"INSERT INTO schema_migrations(version, applied_at) VALUES ('{version}', '{now_iso()}');\nCOMMIT;")
            applied.append(version)
    return applied
