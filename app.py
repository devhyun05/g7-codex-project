from flask import Flask, jsonify, render_template, request

from tracer import ExecutionTracer

app = Flask(__name__)
tracer = ExecutionTracer()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/visualize")
def visualize():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").rstrip()

    if not code:
        return jsonify({"ok": False, "error": "시각화할 파이썬 코드를 입력하세요.", "steps": []}), 400

    result = tracer.trace(code)
    status_code = 200 if result.get("steps") else 400
    return jsonify(result), status_code


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)

