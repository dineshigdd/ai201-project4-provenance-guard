"""Provenance Guard — Flask application factory.

Wires the API blueprint onto a Flask app. Rate limiting (planning §6 / required
feature), the structural signal, fusion, labeller, and audit log register here
in later steps.
"""

import logging

from flask import Flask, jsonify

from provenance_guard.api.extensions import limiter
from provenance_guard.api.routes import bp as api_bp


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)

    app = Flask(__name__)
    limiter.init_app(app)
    app.register_blueprint(api_bp)

    @app.errorhandler(429)
    def ratelimit_handler(exc):
        """Return rate-limit rejections as JSON, matching the rest of the API."""
        return jsonify(
            {
                "error": "Rate limit exceeded. Please slow down and try again later.",
                "detail": str(exc.description),
            }
        ), 429

    return app
