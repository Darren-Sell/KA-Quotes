from flask import Blueprint, jsonify
from .db import get_db
from .auth import admin_required
from .routes_catalog import product_row_to_dict, customer_row_to_dict, settings_row_to_dict
from .routes_quotes import quote_row_to_dict

bp = Blueprint("export", __name__, url_prefix="/api")


@bp.get("/export")
@admin_required
def export_all():
    db = get_db()
    products = [product_row_to_dict(r) for r in db.execute("SELECT * FROM products").fetchall()]
    customers = [customer_row_to_dict(r) for r in db.execute("SELECT * FROM customers").fetchall()]
    quotes = [quote_row_to_dict(db, r) for r in db.execute("SELECT * FROM quotes").fetchall()]
    settings = settings_row_to_dict(db.execute("SELECT * FROM settings WHERE id = 1").fetchone())
    return jsonify({"products": products, "customers": customers, "quotes": quotes, "settings": settings})
