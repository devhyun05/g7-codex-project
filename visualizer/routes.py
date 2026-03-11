from flask import Blueprint, jsonify, make_response, render_template, request

from .services.trace_service import trace_service

main_blueprint = Blueprint("main", __name__)


@main_blueprint.get("/")
def index():
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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
    response = make_response(jsonify(result), status_code)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
