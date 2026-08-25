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
    status TEXT NOT NULL DEFAULT 'active',
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

-- Some customers have several people who place orders — each contact is a
-- separate named buyer at a customer, so a given quote can be addressed to
-- whichever one of them actually asked for it. This replaces the old single
-- free-typed "contact" name on the customer itself (still on that table but
-- no longer edited directly — see _backfill_contacts()).
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY,
    number TEXT NOT NULL,
    customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
    contact_id TEXT NOT NULL DEFAULT '',
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

-- Configurable option lists that feed the Screw Jack part code builder
-- (Jack Model, Screw Jack Type, Gearbox Execution, Gear Ratio, End
-- Attachment, Protective Bellows). Seeded from the Screw Jack Selection
-- guide on first run (see _backfill_sj_options()) but fully editable from
-- then on, so new product variants can be added without a code change.
CREATE TABLE IF NOT EXISTS sj_options (
    id TEXT PRIMARY KEY,
    field TEXT NOT NULL,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    kn REAL NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quote_items_quote_id ON quote_items(quote_id);
CREATE INDEX IF NOT EXISTS idx_quotes_customer_id ON quotes(customer_id);
CREATE INDEX IF NOT EXISTS idx_contacts_customer_id ON contacts(customer_id);
CREATE INDEX IF NOT EXISTS idx_sj_options_field ON sj_options(field);
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
    ("quotes", "contact_id", "TEXT NOT NULL DEFAULT ''"),
    ("users", "status", "TEXT NOT NULL DEFAULT 'active'"),
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


def _backfill_contacts(db):
    """Turn each customer's old single free-typed contact name (from before
    named buyers were tracked separately) into a real row in the new
    contacts table, so multi-buyer customers can add the rest without
    losing the one already on file. Safe to re-run — only backfills
    customers that don't already have any contacts.
    """
    rows = db.execute(
        "SELECT id, contact, email, phone FROM customers WHERE TRIM(contact) != ''"
    ).fetchall()
    for row in rows:
        existing = db.execute(
            "SELECT COUNT(*) AS n FROM contacts WHERE customer_id = ?", (row["id"],)
        ).fetchone()
        if existing["n"] > 0:
            continue
        db.execute(
            "INSERT INTO contacts (id, customer_id, name, email, phone, created_at) VALUES (?,?,?,?,?,?)",
            (new_id(), row["id"], row["contact"].strip(), row["email"] or "", row["phone"] or "", now()),
        )


SJ_OPTION_DEFAULTS = {
    # (code, label, kn) — kn only meaningful for "model", left as 0 elsewhere.
    "model": [
        ("J00", "J00", 5), ("J01", "J01", 10), ("J02", "J02", 25), ("J03", "J03", 50),
        ("J04", "J04", 100), ("J051", "J051", 200), ("J05", "J05", 200), ("J06", "J06", 300),
        ("J07", "J07", 500), ("J08", "J08", 750), ("J09", "J09", 1000),
    ],
    "screw": [
        ("TS", "Translating", 0), ("KS", "Keyed", 0), ("RS", "Rotating", 0),
        ("TB", "Translating with backlash limiter", 0), ("RB", "Rotating with backlash limiter", 0),
    ],
    "gearbox": [("U", "Upright", 0), ("I", "Inverted", 0)],
    "ratio": [("L", "Low", 0), ("H", "High", 0)],
    "end": [
        ("F", "Flanged end", 0), ("C", "Clevis end", 0), ("T", "Threaded end", 0), ("P", "Plain turned end", 0),
    ],
    "bellows": [("V", "P.V.C", 0), ("R", "Heat resistant", 0), ("N", "Not specified", 0)],
}


def _backfill_sj_options(db):
    """Seed the Screw Jack part-code builder's option lists from the Screw
    Jack Selection guide, but only the very first time — once the table has
    any rows in it (including an admin having deleted every default from a
    given field down to zero), this does nothing further, so admin edits are
    never overwritten on a later restart.
    """
    total = db.execute("SELECT COUNT(*) AS c FROM sj_options").fetchone()["c"]
    if total > 0:
        return
    for field, options in SJ_OPTION_DEFAULTS.items():
        for i, (code, label, kn) in enumerate(options):
            db.execute(
                "INSERT INTO sj_options (id, field, code, label, kn, sort_order, created_at) VALUES (?,?,?,?,?,?,?)",
                (new_id(), field, code, label, kn, i, now()),
            )


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        _run_migrations(db)
        _backfill_categories(db)
        _backfill_contacts(db)
        _backfill_sj_options(db)
        db.execute(
            "INSERT OR IGNORE INTO settings (id) VALUES (1)"
        )
        db.commit()
    app.teardown_appcontext(close_db)
