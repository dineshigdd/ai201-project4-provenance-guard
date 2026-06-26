"""Provenance Guard — Flask application factory.

Wires the API blueprint onto a Flask app. Rate limiting (planning §6 / required
feature), the structural signal, fusion, labeller, and audit log register here
in later steps.
"""

import logging

from flask import Flask

from provenance_guard.api.routes import bp as api_bp


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)

    app = Flask(__name__)
    app.register_blueprint(api_bp)

    return app
