"""BF-03 retired generation endpoints; no legacy providers, imports or file writes."""
from __future__ import annotations

def install_retired_interpreter_routes(app):
    from flask import jsonify
    def retired(legacy_path=""):
        return jsonify(status="RETIRED", authority="ADVISORY_ONLY", provider_called=False,
                       reason="Legacy Interpreter retired; use the canonical Lab review."), 410
    app.add_url_rule("/api/interpreter/", "legacy_interpreter_retired_root", retired, methods=["GET", "POST"])
    app.add_url_rule("/api/interpreter/<path:legacy_path>", "legacy_interpreter_retired", retired, methods=["GET", "POST"])
