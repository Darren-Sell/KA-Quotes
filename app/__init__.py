import os
from flask import Flask, send_from_directory
from .db import init_db


def create_app():
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    app = Flask(__name__, static_folder=static_dir, static_url_path="")

    init_db(app)

    from . import routes_auth, routes_catalog, routes_quotes, routes_export
    app.register_blueprint(routes_auth.bp)
    app.register_blueprint(routes_catalog.bp)
    app.register_blueprint(routes_quotes.bp)
    app.register_blueprint(routes_export.bp)

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    # Client has no deep-linked routes today, but fall back to index.html for
    # any unmatched non-API path so a refresh never 404s.
    @app.errorhandler(404)
    def not_found(e):
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found"}), 404
        return send_from_directory(static_dir, "index.html")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
