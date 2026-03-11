from flask import Blueprint, jsonify, render_template, request

from .services.trace_service import trace_service

main_blueprint = Blueprint("main", __name__)


@main_blueprint.get("/")
def index():
    return render_template("index.html")


@main_blueprint.post("/api/visualize")
def visualize():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").rstrip()
    stdin = payload.get("stdin") or ""
    language = payload.get("language") or "auto"

    if not code:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Please enter code to visualize.",
                    "steps": [],
                    "language": {
                        "key": "unknown",
                        "label": "Unknown",
                        "source": "auto",
                        "trace_supported": False,
                    },
                    "trace_capabilities": None,
                    "supported_languages": [],
                    "analysis": {"structures": [], "intent_map": {}, "summary": ""},
                }
            ),
            400,
        )

    result = trace_service.visualize(code, stdin=stdin, requested_language=language)
    detected_language = (result.get("language") or {}).get("key")
    status_code = 200 if result.get("steps") or detected_language not in {None, "unknown"} else 400
    return jsonify(result), status_code
