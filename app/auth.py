import os
import functools
import datetime
import jwt
from flask import request, jsonify, g, current_app

COOKIE_NAME = "ka_session"
TOKEN_TTL_DAYS = 30


def _secret():
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # Local/dev fallback only — the deploy guide requires setting a real
        # SECRET_KEY env var in production so sessions survive restarts and
        # can't be forged.
        secret = "dev-only-insecure-secret-change-me"
    return secret


def issue_token(user_row):
    payload = {
        "uid": user_row["id"],
        "role": user_row["role"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def set_auth_cookie(response, token):
    secure = os.environ.get("COOKIE_SECURE", "1") != "0"
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        max_age=TOKEN_TTL_DAYS * 24 * 3600,
        path="/",
    )


def clear_auth_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/")


def decode_token(token):
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def get_current_user():
    """Returns the sqlite3.Row for the logged-in user, or None."""
    if "current_user" in g:
        return g.current_user
    token = request.cookies.get(COOKIE_NAME)
    g.current_user = None
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    from .db import get_db
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (payload["uid"],)).fetchone()
    if row and row["status"] == "disabled":
        # Checked fresh from the DB on every request (not just at login), so
        # disabling a user signs them out of any session they already have
        # open — no separate token revocation needed.
        return None
    g.current_user = row
    return row


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "not_authenticated"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "not_authenticated"}), 401
        if user["role"] != "admin":
            return jsonify({"error": "admin_only"}), 403
        return fn(*args, **kwargs)
    return wrapper
