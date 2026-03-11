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
    language = (payload.get("language") or "python").strip().lower()

    if not code:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "시각화할 파이썬 코드를 입력하세요.",
                    "display_error": (
                        "실행할 Python 코드를 먼저 입력해 주세요. 코드 입력창에 "
                        "한 줄 이상 작성한 뒤 다시 실행해 보세요."
                    ),
                    "steps": [],
                    "stdout": "",
                    "stdin": stdin,
                    "language": language,
                    "analysis": {
                        "structures": [],
                        "intent_map": {},
                        "summary": "",
                        "intents": {"sorting": False, "sorting_order": "unknown"},
                    },
                }
            ),
            400,
        )

    result = trace_service.visualize(code, stdin=stdin, language=language)
    status_code = 200 if result.get("steps") else 400
    return jsonify(result), status_code
