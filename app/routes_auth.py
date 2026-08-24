import re
from flask import Blueprint, request, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db, new_id, now
from .auth import issue_token, set_auth_cookie, clear_auth_cookie, get_current_user, login_required, admin_required

bp = Blueprint("auth", __name__, url_prefix="/api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "status": row["status"]}


def validate_email(email):
    return bool(email) and bool(EMAIL_RE.match(email))


def validate_password(pw):
    return bool(pw) and len(pw) >= 8


@bp.get("/setup/status")
def setup_status():
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    return jsonify({"needsSetup": count == 0})


@bp.post("/setup")
def setup():
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return jsonify({"error": "already_set_up"}), 409

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name:
        return jsonify({"error": "name_required"}), 400
    if not validate_email(email):
        return jsonify({"error": "invalid_email"}), 400
    if not validate_password(password):
        return jsonify({"error": "weak_password", "message": "Password must be at least 8 characters."}), 400

    uid = new_id()
    db.execute(
        "INSERT INTO users (id, name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'admin', ?)",
        (uid, name, email, generate_password_hash(password), now()),
    )
    db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    token = issue_token(row)
    resp = make_response(jsonify({"user": public_user(row)}))
    set_auth_cookie(resp, token)
    return resp


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid_credentials"}), 401
    if row["status"] == "disabled":
        return jsonify({"error": "account_disabled"}), 403

    token = issue_token(row)
    resp = make_response(jsonify({"user": public_user(row)}))
    set_auth_cookie(resp, token)
    return resp


@bp.post("/auth/logout")
def logout():
    resp = make_response(jsonify({"ok": True}))
    clear_auth_cookie(resp)
    return resp


@bp.get("/auth/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"user": None})
    return jsonify({"user": public_user(user)})


@bp.patch("/auth/password")
@login_required
def change_password():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    current = data.get("currentPassword") or ""
    new_password = data.get("newPassword") or ""

    if not check_password_hash(user["password_hash"], current):
        return jsonify({"error": "wrong_current_password"}), 400
    if not validate_password(new_password):
        return jsonify({"error": "weak_password", "message": "Password must be at least 8 characters."}), 400

    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), user["id"]))
    db.commit()
    return jsonify({"ok": True})


# ---- User management (admin only) ----

@bp.get("/users")
@admin_required
def list_users():
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
    return jsonify({"users": [public_user(r) for r in rows]})


@bp.post("/users")
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") if data.get("role") in ("admin", "member") else "member"

    if not name:
        return jsonify({"error": "name_required"}), 400
    if not validate_email(email):
        return jsonify({"error": "invalid_email"}), 400
    if not validate_password(password):
        return jsonify({"error": "weak_password", "message": "Password must be at least 8 characters."}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "email_taken"}), 409

    uid = new_id()
    db.execute(
        "INSERT INTO users (id, name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, name, email, generate_password_hash(password), role, now()),
    )
    db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return jsonify(public_user(row)), 201


@bp.put("/users/<uid>")
@admin_required
def update_user(uid):
    current = get_current_user()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json(silent=True) or {}

    status = row["status"]
    if "status" in data:
        if data["status"] not in ("active", "disabled"):
            return jsonify({"error": "invalid_status"}), 400
        status = data["status"]

    if current["id"] == uid and status != row["status"]:
        return jsonify({"error": "cannot_change_own_status"}), 400

    if row["role"] == "admin" and row["status"] == "active" and status == "disabled":
        other_active_admins = db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND status = 'active' AND id != ?", (uid,)
        ).fetchone()["c"]
        if other_active_admins == 0:
            return jsonify({"error": "cannot_disable_last_admin"}), 400

    password_hash = row["password_hash"]
    if data.get("password"):
        if not validate_password(data["password"]):
            return jsonify({"error": "weak_password", "message": "Password must be at least 8 characters."}), 400
        password_hash = generate_password_hash(data["password"])

    db.execute("UPDATE users SET status = ?, password_hash = ? WHERE id = ?", (status, password_hash, uid))
    db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return jsonify(public_user(row))


@bp.delete("/users/<uid>")
@admin_required
def delete_user(uid):
    current = get_current_user()
    if current["id"] == uid:
        return jsonify({"error": "cannot_delete_self"}), 400

    db = get_db()
    admin_count = db.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()["c"]
    target = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not target:
        return jsonify({"error": "not_found"}), 404
    if target["role"] == "admin" and admin_count <= 1:
        return jsonify({"error": "cannot_delete_last_admin"}), 400

    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    return jsonify({"ok": True})
