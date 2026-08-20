from flask import Blueprint, request, jsonify
from .db import get_db, new_id, now
from .auth import login_required, get_current_user

bp = Blueprint("quotes", __name__, url_prefix="/api")

VALID_STATUSES = {"draft", "sent", "accepted", "rejected", "expired"}


def quote_row_to_dict(db, row):
    items = db.execute(
        "SELECT * FROM quote_items WHERE quote_id = ? ORDER BY sort_order ASC", (row["id"],)
    ).fetchall()
    return {
        "id": row["id"],
        "number": row["number"],
        "customerId": row["customer_id"],
        "date": row["date"],
        "validUntil": row["valid_until"],
        "discount": row["discount"],
        "tax": row["tax"],
        "notes": row["notes"],
        "status": row["status"],
        "createdBy": row["created_by"],
        "updatedBy": row["updated_by"],
        "updatedAt": row["updated_at"],
        "items": [
            {"id": it["id"], "partNumber": it["part_number"], "description": it["description"], "qty": it["qty"], "unitPrice": it["unit_price"]}
            for it in items
        ],
    }


@bp.get("/quotes")
@login_required
def list_quotes():
    db = get_db()
    rows = db.execute("SELECT * FROM quotes ORDER BY date DESC, created_at DESC").fetchall()
    return jsonify({"quotes": [quote_row_to_dict(db, r) for r in rows]})


@bp.get("/quotes/next-number")
@login_required
def next_number():
    db = get_db()
    s = db.execute("SELECT prefix, next_num FROM settings WHERE id = 1").fetchone()
    return jsonify({"number": f"{s['prefix']}{s['next_num']}"})


def _save_items(db, quote_id, items):
    db.execute("DELETE FROM quote_items WHERE quote_id = ?", (quote_id,))
    for i, it in enumerate(items or []):
        db.execute(
            "INSERT INTO quote_items (id, quote_id, part_number, description, qty, unit_price, sort_order) VALUES (?,?,?,?,?,?,?)",
            (new_id(), quote_id, (it.get("partNumber") or ""), (it.get("description") or ""), float(it.get("qty") or 0),
             float(it.get("unitPrice") or 0), i),
        )


@bp.post("/quotes")
@login_required
def create_quote():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    db = get_db()

    status = data.get("status") if data.get("status") in VALID_STATUSES else "draft"
    qid = new_id()
    ts = now()

    # The quote number is always assigned server-side, atomically, so two
    # people creating a quote at the same moment can never collide on the
    # same number — the client-supplied "number" field (if any) is ignored.
    db.execute("BEGIN IMMEDIATE")
    s = db.execute("SELECT prefix, next_num FROM settings WHERE id = 1").fetchone()
    number = f"{s['prefix']}{s['next_num']}"
    db.execute("UPDATE settings SET next_num = next_num + 1 WHERE id = 1")

    db.execute(
        """INSERT INTO quotes (id, number, customer_id, date, valid_until, discount, tax, notes, status,
           created_by, updated_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (qid, number, data.get("customerId"), data.get("date") or "", data.get("validUntil") or "",
         float(data.get("discount") or 0), float(data.get("tax") or 0), data.get("notes") or "",
         status, user["id"], user["id"], ts, ts),
    )
    _save_items(db, qid, data.get("items"))
    db.commit()
    row = db.execute("SELECT * FROM quotes WHERE id = ?", (qid,)).fetchone()
    return jsonify(quote_row_to_dict(db, row)), 201


@bp.put("/quotes/<qid>")
@login_required
def update_quote(qid):
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    db = get_db()
    row = db.execute("SELECT * FROM quotes WHERE id = ?", (qid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    status = data.get("status") if data.get("status") in VALID_STATUSES else row["status"]
    db.execute(
        """UPDATE quotes SET number=?, customer_id=?, date=?, valid_until=?, discount=?, tax=?, notes=?,
           status=?, updated_by=?, updated_at=? WHERE id=?""",
        (
            data.get("number", row["number"]),
            data.get("customerId", row["customer_id"]),
            data.get("date", row["date"]),
            data.get("validUntil", row["valid_until"]),
            float(data.get("discount", row["discount"]) or 0),
            float(data.get("tax", row["tax"]) or 0),
            data.get("notes", row["notes"]),
            status,
            user["id"],
            now(),
            qid,
        ),
    )
    if "items" in data:
        _save_items(db, qid, data.get("items"))
    db.commit()
    row = db.execute("SELECT * FROM quotes WHERE id = ?", (qid,)).fetchone()
    return jsonify(quote_row_to_dict(db, row))


@bp.delete("/quotes/<qid>")
@login_required
def delete_quote(qid):
    db = get_db()
    db.execute("DELETE FROM quotes WHERE id = ?", (qid,))
    db.commit()
    return jsonify({"ok": True})
