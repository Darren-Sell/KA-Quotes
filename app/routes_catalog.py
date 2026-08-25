from flask import Blueprint, request, jsonify
from .db import get_db, new_id, now
from .auth import login_required, admin_required, get_current_user

bp = Blueprint("catalog", __name__, url_prefix="/api")


# ---------------- Settings ----------------

def settings_row_to_dict(row):
    return {
        "companyName": row["company_name"],
        "companyAddress": row["company_address"],
        "companyEmail": row["company_email"],
        "companyPhone": row["company_phone"],
        "currency": row["currency"],
        "defaultTax": row["default_tax"],
        "prefix": row["prefix"],
        "nextNum": row["next_num"],
        "defaultNotes": row["default_notes"],
        "vatNumber": row["vat_number"],
        "companyNumber": row["company_number"],
        "logo": row["logo_data"],
        "defaultSummary": row["default_summary"],
    }


@bp.get("/settings")
@login_required
def get_settings():
    db = get_db()
    row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(settings_row_to_dict(row))


@bp.put("/settings")
@admin_required
def update_settings():
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        """UPDATE settings SET company_name=?, company_address=?, company_email=?, company_phone=?,
           currency=?, default_tax=?, prefix=?, default_notes=?, vat_number=?, company_number=?, logo_data=?,
           default_summary=?
           WHERE id = 1""",
        (
            (data.get("companyName") or "Your company").strip(),
            data.get("companyAddress") or "",
            data.get("companyEmail") or "",
            data.get("companyPhone") or "",
            data.get("currency") or "£",
            float(data.get("defaultTax") or 0),
            data.get("prefix") or "Q-",
            data.get("defaultNotes") or "",
            data.get("vatNumber") or "",
            data.get("companyNumber") or "",
            data.get("logo") or "",
            data.get("defaultSummary") or "",
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(settings_row_to_dict(row))


# ---------------- Products ----------------

def product_row_to_dict(row):
    return {"id": row["id"], "name": row["name"], "sku": row["sku"], "price": row["price"], "category": row["category"]}


@bp.get("/products")
@login_required
def list_products():
    db = get_db()
    # Grouped by category, then by part number. SQL can't do a true natural
    # sort (so "LA-10" sorts before "LA-9" here) — the frontend re-sorts with
    # a numeric-aware comparison for display; this ordering is just a
    # reasonable default for any other API consumer.
    rows = db.execute("SELECT * FROM products ORDER BY category COLLATE NOCASE ASC, sku COLLATE NOCASE ASC").fetchall()
    return jsonify({"products": [product_row_to_dict(r) for r in rows]})


@bp.post("/products")
@login_required
def create_product():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400
    sku = (data.get("sku") or "").strip()
    price = float(data.get("price") or 0)
    category = (data.get("category") or "").strip()

    db = get_db()
    pid = new_id()
    ts = now()
    db.execute(
        "INSERT INTO products (id, name, sku, price, category, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (pid, name, sku, price, category, ts, ts),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    return jsonify(product_row_to_dict(row)), 201


@bp.put("/products/<pid>")
@login_required
def update_product(pid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    name = (data.get("name") or row["name"]).strip()
    sku = data.get("sku", row["sku"])
    price = float(data.get("price", row["price"]) or 0)
    category = (data.get("category", row["category"]) or "").strip()
    db.execute(
        "UPDATE products SET name=?, sku=?, price=?, category=?, updated_at=? WHERE id=?",
        (name, sku, price, category, now(), pid),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    return jsonify(product_row_to_dict(row))


@bp.delete("/products/<pid>")
@login_required
def delete_product(pid):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (pid,))
    db.commit()
    return jsonify({"ok": True})


# ---------------- Categories ----------------
# A small fixed picklist for products.category, kept in its own table so the
# UI can offer a dropdown instead of free text — the actual fix for typos
# like "Actuator" vs "Actuators" ending up as two different categories.

def category_row_to_dict(row):
    return {"id": row["id"], "name": row["name"]}


@bp.get("/categories")
@login_required
def list_categories():
    db = get_db()
    rows = db.execute("SELECT * FROM categories ORDER BY name COLLATE NOCASE ASC").fetchall()
    return jsonify({"categories": [category_row_to_dict(r) for r in rows]})


@bp.post("/categories")
@login_required
def create_category():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400

    db = get_db()
    existing = db.execute("SELECT * FROM categories WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        # Someone already created this category (maybe in different casing) —
        # hand back the existing one instead of erroring, so picking a
        # near-duplicate name just quietly reuses the original.
        return jsonify(category_row_to_dict(existing)), 200

    cid = new_id()
    db.execute("INSERT INTO categories (id, name, created_at) VALUES (?,?,?)", (cid, name, now()))
    db.commit()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return jsonify(category_row_to_dict(row)), 201


@bp.put("/categories/<cid>")
@login_required
def update_category(cid):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    clash = db.execute("SELECT * FROM categories WHERE name = ? COLLATE NOCASE AND id != ?", (name, cid)).fetchone()
    if clash:
        return jsonify({"error": "name_taken"}), 409

    old_name = row["name"]
    db.execute("UPDATE categories SET name = ? WHERE id = ?", (name, cid))
    # Renaming a category updates every product already tagged with the old
    # name (matched case-insensitively) so nothing is silently orphaned.
    db.execute("UPDATE products SET category = ? WHERE category = ? COLLATE NOCASE", (name, old_name))
    db.commit()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return jsonify(category_row_to_dict(row))


@bp.delete("/categories/<cid>")
@login_required
def delete_category(cid):
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    db.execute("DELETE FROM categories WHERE id = ?", (cid,))
    # Products that were tagged with this category fall back to "no
    # category" rather than pointing at something that no longer exists.
    db.execute("UPDATE products SET category = '' WHERE category = ? COLLATE NOCASE", (row["name"],))
    db.commit()
    return jsonify({"ok": True})


# ---------------- Screw jack part-code options ----------------
# Configurable option lists (Jack Model, Screw Jack Type, Gearbox Execution,
# Gear Ratio, End Attachment, Protective Bellows) that feed the Screw Jacks
# part-code builder. Seeded once from the Screw Jack Selection guide (see
# _backfill_sj_options in db.py) and fully editable from the Screw Jacks
# page from then on, so new variants can be added without a code change.

SJ_OPTION_FIELDS = ("model", "screw", "gearbox", "ratio", "end", "bellows")


def sj_option_row_to_dict(row):
    return {
        "id": row["id"], "field": row["field"], "code": row["code"],
        "label": row["label"], "kn": row["kn"], "sortOrder": row["sort_order"],
    }


@bp.get("/sj-options")
@login_required
def list_sj_options():
    db = get_db()
    rows = db.execute("SELECT * FROM sj_options ORDER BY field ASC, sort_order ASC, created_at ASC").fetchall()
    return jsonify({"options": [sj_option_row_to_dict(r) for r in rows]})


@bp.post("/sj-options")
@login_required
def create_sj_option():
    data = request.get_json(silent=True) or {}
    field = data.get("field")
    code = (data.get("code") or "").strip()
    label = (data.get("label") or "").strip()
    kn = float(data.get("kn") or 0)

    if field not in SJ_OPTION_FIELDS:
        return jsonify({"error": "invalid_field"}), 400
    if not code or not label:
        return jsonify({"error": "code_and_label_required"}), 400

    db = get_db()
    clash = db.execute(
        "SELECT id FROM sj_options WHERE field = ? AND code = ? COLLATE NOCASE", (field, code)
    ).fetchone()
    if clash:
        return jsonify({"error": "code_taken"}), 409

    next_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM sj_options WHERE field = ?", (field,)
    ).fetchone()["n"]

    oid = new_id()
    db.execute(
        "INSERT INTO sj_options (id, field, code, label, kn, sort_order, created_at) VALUES (?,?,?,?,?,?,?)",
        (oid, field, code, label, kn, next_order, now()),
    )
    db.commit()
    row = db.execute("SELECT * FROM sj_options WHERE id = ?", (oid,)).fetchone()
    return jsonify(sj_option_row_to_dict(row)), 201


@bp.put("/sj-options/<oid>")
@login_required
def update_sj_option(oid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM sj_options WHERE id = ?", (oid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    code = (data.get("code") or row["code"]).strip()
    label = (data.get("label") or row["label"]).strip()
    kn = float(data.get("kn", row["kn"]) or 0)
    if not code or not label:
        return jsonify({"error": "code_and_label_required"}), 400

    clash = db.execute(
        "SELECT id FROM sj_options WHERE field = ? AND code = ? COLLATE NOCASE AND id != ?",
        (row["field"], code, oid),
    ).fetchone()
    if clash:
        return jsonify({"error": "code_taken"}), 409

    db.execute("UPDATE sj_options SET code = ?, label = ?, kn = ? WHERE id = ?", (code, label, kn, oid))
    db.commit()
    row = db.execute("SELECT * FROM sj_options WHERE id = ?", (oid,)).fetchone()
    return jsonify(sj_option_row_to_dict(row))


@bp.delete("/sj-options/<oid>")
@login_required
def delete_sj_option(oid):
    db = get_db()
    row = db.execute("SELECT * FROM sj_options WHERE id = ?", (oid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    db.execute("DELETE FROM sj_options WHERE id = ?", (oid,))
    db.commit()
    return jsonify({"ok": True})


# ---------------- Customers ----------------

def customer_row_to_dict(row):
    return {
        "id": row["id"], "company": row["company"], "contact": row["contact"],
        "email": row["email"], "phone": row["phone"], "address": row["address"],
    }


@bp.get("/customers")
@login_required
def list_customers():
    db = get_db()
    rows = db.execute("SELECT * FROM customers ORDER BY company COLLATE NOCASE ASC").fetchall()
    return jsonify({"customers": [customer_row_to_dict(r) for r in rows]})


@bp.post("/customers")
@login_required
def create_customer():
    data = request.get_json(silent=True) or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"error": "company_required"}), 400

    db = get_db()
    cid = new_id()
    ts = now()
    db.execute(
        """INSERT INTO customers (id, company, contact, email, phone, address, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (cid, company, data.get("contact") or "", data.get("email") or "",
         data.get("phone") or "", data.get("address") or "", ts, ts),
    )
    db.commit()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    return jsonify(customer_row_to_dict(row)), 201


@bp.put("/customers/<cid>")
@login_required
def update_customer(cid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    fields = {
        "company": (data.get("company") or row["company"]).strip(),
        "contact": data.get("contact", row["contact"]),
        "email": data.get("email", row["email"]),
        "phone": data.get("phone", row["phone"]),
        "address": data.get("address", row["address"]),
    }
    db.execute(
        "UPDATE customers SET company=?, contact=?, email=?, phone=?, address=?, updated_at=? WHERE id=?",
        (fields["company"], fields["contact"], fields["email"], fields["phone"], fields["address"], now(), cid),
    )
    db.commit()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    return jsonify(customer_row_to_dict(row))


@bp.delete("/customers/<cid>")
@login_required
def delete_customer(cid):
    db = get_db()
    db.execute("DELETE FROM customers WHERE id = ?", (cid,))
    db.commit()
    return jsonify({"ok": True})


# ---------------- Contacts ----------------
# Named buyers at a customer — some customers have several people who place
# orders, so a quote can be addressed to whichever one of them asked for it
# rather than always greeting the same, single contact.

def contact_row_to_dict(row):
    return {
        "id": row["id"], "customerId": row["customer_id"], "name": row["name"],
        "email": row["email"], "phone": row["phone"],
    }


@bp.get("/contacts")
@login_required
def list_contacts():
    db = get_db()
    rows = db.execute("SELECT * FROM contacts ORDER BY name COLLATE NOCASE ASC").fetchall()
    return jsonify({"contacts": [contact_row_to_dict(r) for r in rows]})


@bp.post("/contacts")
@login_required
def create_contact():
    data = request.get_json(silent=True) or {}
    customer_id = data.get("customerId") or ""
    name = (data.get("name") or "").strip()
    if not customer_id or not name:
        return jsonify({"error": "customer_and_name_required"}), 400

    db = get_db()
    customer = db.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        return jsonify({"error": "customer_not_found"}), 404

    ctid = new_id()
    db.execute(
        "INSERT INTO contacts (id, customer_id, name, email, phone, created_at) VALUES (?,?,?,?,?,?)",
        (ctid, customer_id, name, data.get("email") or "", data.get("phone") or "", now()),
    )
    db.commit()
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (ctid,)).fetchone()
    return jsonify(contact_row_to_dict(row)), 201


@bp.put("/contacts/<ctid>")
@login_required
def update_contact(ctid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (ctid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    name = (data.get("name") or row["name"]).strip()
    if not name:
        return jsonify({"error": "name_required"}), 400
    email = data.get("email", row["email"])
    phone = data.get("phone", row["phone"])
    db.execute("UPDATE contacts SET name=?, email=?, phone=? WHERE id=?", (name, email, phone, ctid))
    db.commit()
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (ctid,)).fetchone()
    return jsonify(contact_row_to_dict(row))


@bp.delete("/contacts/<ctid>")
@login_required
def delete_contact(ctid):
    db = get_db()
    db.execute("DELETE FROM contacts WHERE id = ?", (ctid,))
    db.commit()
    return jsonify({"ok": True})
