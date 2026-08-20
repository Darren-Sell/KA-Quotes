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
           currency=?, default_tax=?, prefix=? WHERE id = 1""",
        (
            (data.get("companyName") or "Your company").strip(),
            data.get("companyAddress") or "",
            data.get("companyEmail") or "",
            data.get("companyPhone") or "",
            data.get("currency") or "£",
            float(data.get("defaultTax") or 0),
            data.get("prefix") or "Q-",
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(settings_row_to_dict(row))


# ---------------- Products ----------------

def product_row_to_dict(row):
    return {"id": row["id"], "name": row["name"], "sku": row["sku"], "price": row["price"]}


@bp.get("/products")
@login_required
def list_products():
    db = get_db()
    rows = db.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE ASC").fetchall()
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

    db = get_db()
    pid = new_id()
    ts = now()
    db.execute(
        "INSERT INTO products (id, name, sku, price, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, name, sku, price, ts, ts),
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
    db.execute(
        "UPDATE products SET name=?, sku=?, price=?, updated_at=? WHERE id=?",
        (name, sku, price, now(), pid),
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
