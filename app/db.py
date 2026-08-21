"""SQLite data access layer for the Kelston Actuation quote builder.

Uses Python's built-in sqlite3 module only — no external DB dependency.
One connection per request (Flask app context), WAL mode for safe
concurrent reads/writes from multiple logged-in users.
"""
import os
import sqlite3
import time
import uuid
from flask import g

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "app.db"))


def new_id():
    return uuid.uuid4().hex[:16]


def now():
    return int(time.time())


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    company_name TEXT NOT NULL DEFAULT 'Kelston Actuation',
    company_address TEXT NOT NULL DEFAULT '',
    company_email TEXT NOT NULL DEFAULT '',
    company_phone TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '£',
    default_tax REAL NOT NULL DEFAULT 20,
    prefix TEXT NOT NULL DEFAULT 'KA-Q-',
    next_num INTEGER NOT NULL DEFAULT 1001,
    default_notes TEXT NOT NULL DEFAULT '',
    vat_number TEXT NOT NULL DEFAULT '',
    company_number TEXT NOT NULL DEFAULT '',
    logo_data TEXT NOT NULL DEFAULT '',
    default_summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sku TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- The canonical list of category names, kept separate from products.category
-- (which stores the name as plain text) so the UI can offer a fixed picklist
-- instead of free typing. COLLATE NOCASE on the UNIQUE constraint means
-- "Linear Actuators" and "linear actuators" are treated as the same
-- category, which is what actually prevents accidental near-duplicates.
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY,
    number TEXT NOT NULL,
    customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
    date TEXT NOT NULL,
    valid_until TEXT NOT NULL DEFAULT '',
    discount REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'GBP',
    status TEXT NOT NULL DEFAULT 'draft',
    created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    updated_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_items (
    id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    part_number TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    qty REAL NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_quote_items_quote_id ON quote_items(quote_id);
CREATE INDEX IF NOT EXISTS idx_quotes_customer_id ON quotes(customer_id);
"""


# Columns added to existing tables after the initial release. CREATE TABLE
# IF NOT EXISTS only helps on a brand-new database — a database created by
# an earlier version of the app needs these added on top. Safe to re-run:
# each column is only added if missing.
MIGRATIONS = [
    ("settings", "default_notes", "TEXT NOT NULL DEFAULT ''"),
    ("quote_items", "part_number", "TEXT NOT NULL DEFAULT ''"),
    ("settings", "vat_number", "TEXT NOT NULL DEFAULT ''"),
    ("settings", "company_number", "TEXT NOT NULL DEFAULT ''"),
    ("settings", "logo_data", "TEXT NOT NULL DEFAULT ''"),
    ("quotes", "summary", "TEXT NOT NULL DEFAULT ''"),
    ("quotes", "currency", "TEXT NOT NULL DEFAULT 'GBP'"),
    ("products", "category", "TEXT NOT NULL DEFAULT ''"),
    ("settings", "default_summary", "TEXT NOT NULL DEFAULT ''"),
]


def _run_migrations(db):
    for table, column, coltype in MIGRATIONS:
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _backfill_categories(db):
    """Carry forward any free-typed category names already sitting on
    products (from before the categories table existed) so nothing is lost
    when the UI switches to picking from a fixed list. Safe to re-run —
    INSERT OR IGNORE plus the COLLATE NOCASE unique constraint means an
    already-known category (in any casing) is simply skipped.
    """
    rows = db.execute(
        "SELECT DISTINCT category FROM products WHERE TRIM(category) != ''"
    ).fetchall()
    for row in rows:
        db.execute(
            "INSERT OR IGNORE INTO categories (id, name, created_at) VALUES (?,?,?)",
            (new_id(), row["category"].strip(), now()),
        )


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        _run_migrations(db)
        _backfill_categories(db)
        db.execute(
            "INSERT OR IGNORE INTO settings (id) VALUES (1)"
        )
        db.commit()
    app.teardown_appcontext(close_db)
