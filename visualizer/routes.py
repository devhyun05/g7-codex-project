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

    if not code:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "시각화할 파이썬 코드를 입력하세요.",
                    "steps": [],
                    "analysis": {"structures": [], "intent_map": {}, "summary": ""},
                }
            ),
            400,
        )

    result = trace_service.visualize(code, stdin=stdin)
    status_code = 200 if result.get("steps") else 400
    return jsonify(result), status_code
