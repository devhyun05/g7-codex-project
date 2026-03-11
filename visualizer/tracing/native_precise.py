from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRACE_MARKER = "__CODEX_TRACE__"
MAX_STEPS = 256


@dataclass
class PreciseTraceResult:
    ok: bool
    steps: list[dict[str, Any]]
    stdout: str
    error: str | None = None
    display_error: str | None = None


def precise_trace_java(
    code: str,
    stdin: str,
    analysis: dict[str, Any],
    javac_path: str,
    java_path: str,
) -> PreciseTraceResult:
    class_name = detect_java_class_name(code)
    if not class_name:
        return PreciseTraceResult(False, [], "", "Java class not found", "No runnable Java class was found.")

    with tempfile.TemporaryDirectory() as temp_dir:
        instrumented = instrument_java_code(code, class_name)
        source_path = Path(temp_dir, f"{class_name}.java")
        source_path.write_text(instrumented, encoding="utf-8")

        compile_process = subprocess.run(
            [javac_path, "-g", str(source_path)],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
        )
        if compile_process.returncode != 0:
            detail = compile_process.stderr.strip() or "javac failed"
            return PreciseTraceResult(False, [], compile_process.stdout or "", detail, f"Java compile failed: {detail.splitlines()[0]}")

        run_process = subprocess.run(
            [java_path, "-cp", temp_dir, class_name],
            cwd=temp_dir,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
        )
        raw_trace_lines = [
            line.strip()
            for line in (run_process.stderr or "").splitlines()
            if line.strip().startswith(TRACE_MARKER)
        ]
        steps = parse_java_trace_lines(code, raw_trace_lines, analysis)
        if run_process.returncode != 0:
            combined = (run_process.stderr or run_process.stdout or "").strip()
            return PreciseTraceResult(False, steps, run_process.stdout or "", combined or "java failed", f"Java run failed: {(combined or 'unknown error').splitlines()[0]}")
        return PreciseTraceResult(True, steps, run_process.stdout or "")


def precise_trace_cpp(
    code: str,
    stdin: str,
    analysis: dict[str, Any],
    compiler_path: str,
    python311_dir: str,
) -> PreciseTraceResult:
    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir, "main.cpp")
        binary_path = Path(temp_dir, "program.exe")
        stdin_path = Path(temp_dir, "stdin.txt")
        command_path = Path(temp_dir, "lldb_cmds.txt")
        source_path.write_text(code, encoding="utf-8")
        stdin_path.write_text(stdin, encoding="utf-8")

        compile_process = subprocess.run(
            [compiler_path, "-g", "-std=c++17", str(source_path), "-o", str(binary_path)],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        if compile_process.returncode != 0:
            detail = compile_process.stderr.strip() or "c++ compile failed"
            return PreciseTraceResult(False, [], compile_process.stdout or "", detail, f"C++ compile failed: {detail.splitlines()[0]}")

        command_path.write_text(build_lldb_command_script(stdin_path), encoding="utf-8")
        env = dict(os.environ)
        env["PATH"] = f"{python311_dir};C:\\Program Files\\LLVM\\bin;{env.get('PATH', '')}"
        run_process = subprocess.run(
            [str(Path("C:/Program Files/LLVM/bin/lldb.exe")), "-b", "-s", str(command_path), str(binary_path)],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if run_process.returncode != 0 and "Current executable set" not in (run_process.stdout or ""):
            detail = (run_process.stderr or run_process.stdout or "").strip()
            return PreciseTraceResult(False, [], "", detail or "lldb failed", f"C++ debugger failed: {(detail or 'unknown error').splitlines()[0]}")

        steps = parse_lldb_output(code, run_process.stdout or "", analysis)

        stdout_process = subprocess.run(
            [str(binary_path)],
            cwd=temp_dir,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
        )
        if stdout_process.returncode != 0:
            combined = (stdout_process.stderr or stdout_process.stdout or "").strip()
            return PreciseTraceResult(False, steps, stdout_process.stdout or "", combined or "c++ run failed", f"C++ run failed: {(combined or 'unknown error').splitlines()[0]}")
        return PreciseTraceResult(True, steps, stdout_process.stdout or "")


def detect_java_class_name(code: str) -> str | None:
    public_match = re.search(r"\bpublic\s+class\s+([A-Za-z_]\w*)", code)
    if public_match:
        return public_match.group(1)
    class_match = re.search(r"\bclass\s+([A-Za-z_]\w*)", code)
    return class_match.group(1) if class_match else None


def instrument_java_code(code: str, class_name: str) -> str:
    lines = code.splitlines()
    output: list[str] = []
    scope_stack: list[dict[str, Any]] = [{"kind": "root", "vars": []}]
    method_stack: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        if stripped == "}":
            if scope_stack and scope_stack[-1]["kind"] == "method":
                method_name = scope_stack[-1]["name"]
                snapshot_expr = build_java_snapshot_expr(visible_java_vars(scope_stack))
                output.append(f'{indent}CodexJavaRuntimeTracer.leave("{method_name}", {line_number}, {snapshot_expr});')
                scope_stack.pop()
                if method_stack:
                    method_stack.pop()
            elif len(scope_stack) > 1:
                scope_stack.pop()
            output.append(line)
            continue

        method_info = detect_java_method(stripped)
        current_vars = visible_java_vars(scope_stack)
        if method_info:
            output.append(line)
            method_scope = {
                "kind": "method",
                "name": method_info["name"],
                "vars": method_info["params"],
            }
            scope_stack.append(method_scope)
            method_stack.append(method_info["name"])
            snapshot_expr = build_java_snapshot_expr(visible_java_vars(scope_stack))
            escaped_source = java_escape(line.rstrip())
            output.append(
                f'{indent}    CodexJavaRuntimeTracer.enter("{method_info["name"]}", {line_number}, "{escaped_source}", {snapshot_expr});'
            )
            for _ in range(max(line.count("{") - line.count("}") - 1, 0)):
                scope_stack.append({"kind": "block", "vars": []})
            continue

        if method_stack and should_trace_java_line(stripped):
            snapshot_expr = build_java_snapshot_expr(current_vars)
            escaped_source = java_escape(line.rstrip())
            active_method = method_stack[-1] if method_stack else "module"
            if stripped.startswith("return"):
                output.append(
                    f'{indent}CodexJavaRuntimeTracer.leave("{active_method}", {line_number}, {snapshot_expr});'
                )
            output.append(
                f'{indent}CodexJavaRuntimeTracer.line("{active_method}", {line_number}, "{escaped_source}", {snapshot_expr});'
            )

        output.append(line)
        declared = detect_java_declared_vars(stripped)
        if declared:
            scope_stack[-1]["vars"].extend(declared)
        brace_delta = line.count("{") - line.count("}")
        if brace_delta > 0:
            for _ in range(brace_delta):
                scope_stack.append({"kind": "block", "vars": []})
        elif brace_delta < 0:
            for _ in range(-brace_delta):
                if len(scope_stack) > 1:
                    scope_stack.pop()

    output.append(JAVA_RUNTIME_HELPER)
    return "\n".join(output) + "\n"


def visible_java_vars(scope_stack: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for scope in scope_stack:
        names.extend(scope.get("vars", []))
    # keep last declaration if duplicated
    seen: set[str] = set()
    ordered: list[str] = []
    for name in reversed(names):
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    ordered.reverse()
    return ordered


def build_java_snapshot_expr(names: list[str]) -> str:
    if not names:
        return "new Object[0][0]"
    rows = ", ".join(f'new Object[]{{"{name}", {name}}}' for name in names)
    return f"new Object[][]{{{rows}}}"


def should_trace_java_line(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith(("//", "import ", "package ", "class ", "public class", "private class")):
        return False
    if stripped in {"{", "}"}:
        return False
    return True


def detect_java_method(stripped: str) -> dict[str, Any] | None:
    if not stripped.endswith("{"):
        return None
    if stripped.startswith(("if ", "if(", "for ", "for(", "while ", "while(", "switch ", "switch(", "catch ", "catch(")):
        return None
    match = re.search(
        r"(?:public|private|protected|static|final|synchronized|native|abstract|\s)+[\w<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:throws\s+[\w<>\., ]+)?\s*\{",
        stripped,
    )
    if not match:
        return None
    params = []
    raw_params = match.group(2).strip()
    if raw_params:
        for item in raw_params.split(","):
            cleaned = item.strip()
            if not cleaned:
                continue
            param_match = re.search(r"([A-Za-z_]\w*)\s*$", cleaned)
            if param_match:
                params.append(param_match.group(1))
    return {"name": match.group(1), "params": params}


def detect_java_declared_vars(stripped: str) -> list[str]:
    if stripped.startswith(("for ", "for(", "if ", "if(", "while ", "while(", "return ", "System.out")):
        return []
    if "(" in stripped and stripped.endswith("{"):
        return []
    if ";" not in stripped:
        return []
    match = re.match(
        r"(?:final\s+)?[\w<>\[\], ?]+\s+([A-Za-z_]\w*(?:\s*=.*)?(?:\s*,\s*[A-Za-z_]\w*(?:\s*=.*)?)*)\s*;",
        stripped,
    )
    if not match:
        return []
    tail = match.group(1)
    names = []
    for part in tail.split(","):
        name_match = re.match(r"\s*([A-Za-z_]\w*)", part.strip())
        if name_match:
            names.append(name_match.group(1))
    return names


def parse_java_trace_lines(code: str, lines: list[str], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    parsed_events = []
    for raw_line in lines:
        parts = raw_line.split("|")
        if len(parts) != 7:
            continue
        _, event, line_text, method_b64, source_b64, stack_b64, vars_b64 = parts
        parsed_events.append(
            {
                "event": event,
                "line": int(line_text),
                "method": base64.b64decode(method_b64.encode("ascii")).decode("utf-8"),
                "source": base64.b64decode(source_b64.encode("ascii")).decode("utf-8"),
                "stack": json.loads(base64.b64decode(stack_b64.encode("ascii")).decode("utf-8")),
                "vars": json.loads(base64.b64decode(vars_b64.encode("ascii")).decode("utf-8")),
            }
        )

    steps: list[dict[str, Any]] = []
    call_root = {"id": "root", "label": "module", "status": "running", "line": None, "active": False, "children": [], "locals": {}}
    runtime_stack: list[dict[str, Any]] = []
    call_counter = 0

    for index, event in enumerate(parsed_events[:MAX_STEPS], start=1):
        if event["event"] == "enter":
            call_counter += 1
            locals_payload = serialize_runtime_namespace(event["vars"])
            node = {
                "id": f'call-{call_counter}',
                "label": format_runtime_label(event["method"], event["vars"]),
                "status": "running",
                "line": event["line"],
                "active": True,
                "children": [],
                "locals": locals_payload,
            }
            parent = runtime_stack[-1]["node"] if runtime_stack else call_root
            parent["children"].append(node)
            runtime_stack.append({"name": event["method"], "node": node})

        if runtime_stack:
            active_node = runtime_stack[-1]["node"]
            active_node["label"] = format_runtime_label(event["method"], event["vars"])
            active_node["locals"] = serialize_runtime_namespace(event["vars"])
            active_node["line"] = event["line"]

        stack = build_stack_from_runtime_stack(runtime_stack, event["line"], event["vars"])
        globals_payload = serialize_runtime_namespace(event["vars"])
        active_tree = snapshot_runtime_tree(call_root, runtime_stack, event["line"], stack)
        steps.append(
            {
                "index": index,
                "event": "return" if event["event"] == "leave" else "line",
                "line": event["line"],
                "line_source": event["source"],
                "line_detail": describe_runtime_line(event["source"], event["method"], "java"),
                "message": f'{event["method"]} at line {event["line"]}',
                "stdout": "",
                "stack": stack,
                "globals": globals_payload,
                "call_tree": active_tree,
                "graph": None,
                "structure": None,
                "explanation": describe_runtime_line(event["source"], event["method"], "java"),
                "explanation_json": {
                    "summary": build_runtime_summary(event["method"], stack, "java"),
                    "line_explanations": [
                        {"line": event["line"], "code": event["source"], "description": describe_runtime_line(event["source"], event["method"], "java")}
                    ],
                    "improvements": build_runtime_improvements(analysis, "java"),
                },
            }
        )
        if runtime_stack and event["event"] == "leave":
            runtime_stack[-1]["node"]["status"] = "returned"
            runtime_stack[-1]["node"]["line"] = event["line"]
            runtime_stack.pop()
    enrich_runtime_structures(steps, analysis)
    return steps


def build_lldb_command_script(stdin_path: Path) -> str:
    commands = [
        "breakpoint set --name main",
        f"process launch -i \"{stdin_path}\"",
    ]
    for _ in range(MAX_STEPS):
        commands.extend(
            [
                "frame info",
                "frame variable",
                "thread backtrace",
                "thread step-over",
            ]
        )
    commands.append("quit")
    return "\n".join(commands) + "\n"


def parse_lldb_output(code: str, output: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = output.split("(lldb) frame info")
    steps: list[dict[str, Any]] = []
    for index, block in enumerate(blocks[1:MAX_STEPS + 1], start=1):
        line_match = re.search(r"at .*?:(\d+)", block)
        if not line_match:
            continue
        line_number = int(line_match.group(1))
        source_line = code.splitlines()[line_number - 1] if 1 <= line_number <= len(code.splitlines()) else ""
        locals_section = block.split("(lldb) frame variable", 1)[-1].split("(lldb) thread backtrace", 1)[0]
        stack_section = block.split("(lldb) thread backtrace", 1)[-1]
        locals_payload = parse_lldb_locals(locals_section)
        stack_names = parse_lldb_stack(stack_section)
        steps.append(
            {
                "index": index,
                "event": "line",
                "line": line_number,
                "line_source": source_line,
                "line_detail": describe_runtime_line(source_line, stack_names[-1] if stack_names else "main", "cpp"),
                "message": f"Stopped at line {line_number}",
                "stdout": "",
                "stack": build_stack_from_names(stack_names, line_number, locals_payload),
                "globals": serialize_runtime_namespace(locals_payload),
                "call_tree": build_call_tree_from_stack(stack_names, line_number),
                "graph": None,
                "structure": None,
                "explanation": describe_runtime_line(source_line, stack_names[-1] if stack_names else "main", "cpp"),
                "explanation_json": {
                    "summary": build_runtime_summary(stack_names[-1] if stack_names else "main", build_stack_from_names(stack_names, line_number, locals_payload), "cpp"),
                    "line_explanations": [
                        {"line": line_number, "code": source_line, "description": describe_runtime_line(source_line, stack_names[-1] if stack_names else "main", "cpp")}
                    ],
                    "improvements": build_runtime_improvements(analysis, "cpp"),
                },
            }
        )
    enrich_runtime_structures(steps, analysis)
    return steps


def parse_lldb_locals(section: str) -> dict[str, Any]:
    locals_payload: dict[str, Any] = {}
    for line in section.splitlines():
        line = line.strip()
        match = re.match(r"\((.+?)\)\s+([A-Za-z_]\w*)\s*=\s*(.+)", line)
        if not match:
            continue
        name = match.group(2)
        raw_value = match.group(3).strip()
        locals_payload[name] = parse_runtime_scalar(raw_value)
    return locals_payload


def parse_lldb_stack(section: str) -> list[str]:
    names: list[str] = []
    for line in section.splitlines():
        match = re.search(r"#\d+.*?`([^`\s]+)", line)
        if match:
            names.append(match.group(1).split("::")[-1])
    return list(reversed(names)) if names else ["main"]


def build_stack_from_names(names: list[str], line_number: int, vars_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not names:
        names = ["main"]
    stack = []
    for index, name in enumerate(names):
        stack.append(
            {
                "name": name,
                "label": f"{name}()",
                "line": line_number,
                "active": index == len(names) - 1,
                "node_id": f"{name}-{index}",
                "locals": serialize_runtime_namespace(vars_payload if index == len(names) - 1 else {}),
            }
        )
    return stack


def build_stack_from_runtime_stack(
    runtime_stack: list[dict[str, Any]],
    line_number: int,
    vars_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    if not runtime_stack:
        return []
    stack = []
    for index, item in enumerate(runtime_stack):
        label = item["node"]["label"]
        stack.append(
            {
                "name": item["name"],
                "label": label,
                "line": line_number,
                "active": index == len(runtime_stack) - 1,
                "node_id": item["node"]["id"],
                "locals": serialize_runtime_namespace(vars_payload if index == len(runtime_stack) - 1 else {}),
            }
        )
    return stack


def build_call_tree_from_stack(names: list[str], line_number: int) -> dict[str, Any]:
    root = {"id": "root", "label": "module", "status": "running", "line": None, "active": False, "children": [], "locals": {}}
    cursor = root
    for index, name in enumerate(names or ["main"]):
        node = {
            "id": f"{name}-{index}",
            "label": f"{name}()",
            "status": "running",
            "line": line_number,
            "active": index == len(names or ['main']) - 1,
            "children": [],
            "locals": {},
        }
        cursor["children"].append(node)
        cursor = node
    return root


def snapshot_runtime_tree(
    root: dict[str, Any],
    runtime_stack: list[dict[str, Any]],
    line_number: int,
    stack_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    active_ids = {frame["node_id"] for frame in stack_payload}

    def clone(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "label": node["label"],
            "status": node.get("status", "running"),
            "line": line_number if node["id"] in active_ids else node.get("line"),
            "active": node["id"] in active_ids,
            "return_value": node.get("return_value"),
            "error": node.get("error"),
            "locals": node.get("locals", {}),
            "children": [clone(child) for child in node.get("children", [])],
        }

    return clone(root)


def serialize_runtime_namespace(vars_payload: dict[str, Any]) -> dict[str, Any]:
    return {name: convert_runtime_value(value) for name, value in vars_payload.items()}


def convert_runtime_value(value: Any) -> dict[str, Any]:
    if value is None or isinstance(value, (bool, int, float, str)):
        return {"type": type(value).__name__, "repr": repr(value), "value": value}
    if isinstance(value, list):
        return {
            "type": "list",
            "repr": repr(value),
            "items": [convert_runtime_value(item) for item in value],
            "truncated": False,
        }
    if isinstance(value, dict):
        return {
            "type": "dict",
            "repr": repr(value),
            "items": [{"key": convert_runtime_value(k), "value": convert_runtime_value(v)} for k, v in value.items()],
            "truncated": False,
        }
    return {"type": type(value).__name__, "repr": repr(value)}


def parse_runtime_scalar(raw_value: str) -> Any:
    raw_value = raw_value.strip()
    if raw_value.startswith('"') and raw_value.endswith('"'):
        return raw_value[1:-1]
    if re.fullmatch(r"-?\d+", raw_value):
        return int(raw_value)
    if re.fullmatch(r"-?\d+\.\d+", raw_value):
        return float(raw_value)
    return raw_value


def enrich_runtime_structures(steps: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
    for step in steps:
        globals_payload = step.get("globals", {})
        for structure in analysis.get("structures", []):
            value = globals_payload.get(structure["name"])
            if structure["kind"] == "stack" and value and value.get("type") == "list":
                items = [item.get("repr", "") for item in value.get("items", [])]
                step["structure"] = {
                    "kind": "stack",
                    "name": structure["name"],
                    "items": items,
                    "truncated": False,
                    "top_index": len(items) - 1 if items else None,
                }
            elif structure["kind"] == "queue" and value and value.get("type") == "list":
                items = [item.get("repr", "") for item in value.get("items", [])]
                step["structure"] = {
                    "kind": "queue",
                    "name": structure["name"],
                    "items": items,
                    "truncated": False,
                    "front_index": 0 if items else None,
                    "back_index": len(items) - 1 if items else None,
                }


def java_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_runtime_summary(method_name: str, stack: list[dict[str, Any]], language: str) -> str:
    depth = len(stack)
    return f"{language.upper()} runtime tracing is active in {method_name} with stack depth {depth}."


def describe_runtime_line(source: str, method_name: str, language: str) -> str:
    stripped = source.strip()
    if not stripped:
        return f"{language.upper()} runtime reached an empty line."
    if stripped.startswith("if"):
        return f"{method_name} is evaluating a condition."
    if stripped.startswith(("for", "while")):
        return f"{method_name} is advancing a loop."
    if stripped.startswith("return"):
        return f"{method_name} is returning to its caller."
    if "(" in stripped and stripped.endswith(";") and not stripped.startswith(("System.out", "sb.append")):
        return f"{method_name} is making a function call."
    if "=" in stripped:
        return f"{method_name} is updating data for the next step."
    return f"{method_name} is executing this line."


def build_runtime_improvements(analysis: dict[str, Any], language: str) -> list[str]:
    improvements: list[str] = []
    if any(item["kind"] == "graph" for item in analysis.get("structures", [])):
        improvements.append("Name traversal variables clearly so graph focus nodes are easier to highlight.")
    if any(item["kind"] == "tree" for item in analysis.get("structures", [])):
        improvements.append("Expose node fields like left/right/children consistently for clearer tree visuals.")
    if analysis.get("intents", {}).get("sorting"):
        improvements.append("Keep the main sortable array in one variable so sorting state stays readable.")
    if language == "java":
        improvements.append("Avoid packing too much logic into one line so the runtime panel stays easy to follow.")
    return improvements


def format_runtime_label(method_name: str, vars_payload: dict[str, Any]) -> str:
    preferred = [name for name in ("n", "fr", "mid", "to", "i", "j", "x", "args") if name in vars_payload]
    if not preferred:
        preferred = [name for name in vars_payload.keys() if name not in {"sb", "br", "arr"}][:3]
    parts = []
    for name in preferred[:3]:
        value = vars_payload.get(name)
        parts.append(f"{name}={short_runtime_repr(value)}")
    joined = ", ".join(parts)
    return f"{method_name}({joined})" if joined else f"{method_name}()"


def short_runtime_repr(value: Any) -> str:
    if isinstance(value, list):
        preview = ", ".join(short_runtime_repr(item) for item in value[:3])
        suffix = ", ..." if len(value) > 3 else ""
        return f"[{preview}{suffix}]"
    text = repr(value)
    return text if len(text) <= 24 else text[:21] + "..."


JAVA_RUNTIME_HELPER = r"""
class CodexJavaRuntimeTracer {
  private static final java.util.List<String> STACK = new java.util.ArrayList<>();
  private static final java.util.Base64.Encoder B64 = java.util.Base64.getEncoder();

  static void enter(String method, int line, String source, Object[][] vars) {
    STACK.add(method);
    emit("enter", method, line, source, vars);
  }

  static void line(String method, int line, String source, Object[][] vars) {
    emit("line", method, line, source, vars);
  }

  static void leave(String method, int line, Object[][] vars) {
    emit("leave", method, line, "", vars);
    if (!STACK.isEmpty()) {
      STACK.remove(STACK.size() - 1);
    }
  }

  private static void emit(String event, String method, int line, String source, Object[][] vars) {
    String stackJson = toJson(STACK, 0, new java.util.IdentityHashMap<>());
    java.util.Map<String, Object> varMap = new java.util.LinkedHashMap<>();
    for (Object[] row : vars) {
      if (row.length == 2) {
        varMap.put(String.valueOf(row[0]), row[1]);
      }
    }
    String varsJson = toJson(varMap, 0, new java.util.IdentityHashMap<>());
    System.err.println("__CODEX_TRACE__|" + event + "|" + line + "|" + enc(method) + "|" + enc(source) + "|" + enc(stackJson) + "|" + enc(varsJson));
  }

  private static String enc(String text) {
    return B64.encodeToString(text.getBytes(java.nio.charset.StandardCharsets.UTF_8));
  }

  private static String q(String text) {
    return "\"" + text
      .replace("\\", "\\\\")
      .replace("\"", "\\\"")
      .replace("\n", "\\n")
      .replace("\r", "\\r")
      .replace("\t", "\\t") + "\"";
  }

  private static String toJson(Object value, int depth, java.util.IdentityHashMap<Object, Boolean> seen) {
    if (value == null) return "null";
    if (depth > 3) return q(String.valueOf(value));
    if (value instanceof String || value instanceof Character) return q(String.valueOf(value));
    if (value instanceof Number || value instanceof Boolean) return String.valueOf(value);
    if (seen.containsKey(value)) return q("<recursive>");
    seen.put(value, true);

    Class<?> cls = value.getClass();
    if (cls.isArray()) {
      StringBuilder sb = new StringBuilder("[");
      int len = java.lang.reflect.Array.getLength(value);
      for (int i = 0; i < len; i++) {
        if (i > 0) sb.append(",");
        sb.append(toJson(java.lang.reflect.Array.get(value, i), depth + 1, seen));
      }
      return sb.append("]").toString();
    }
    if (value instanceof java.util.Map<?, ?> map) {
      StringBuilder sb = new StringBuilder("{");
      boolean first = true;
      for (java.util.Map.Entry<?, ?> entry : map.entrySet()) {
        if (!first) sb.append(",");
        first = false;
        sb.append(q(String.valueOf(entry.getKey()))).append(":").append(toJson(entry.getValue(), depth + 1, seen));
      }
      return sb.append("}").toString();
    }
    if (value instanceof java.lang.Iterable<?> iterable) {
      StringBuilder sb = new StringBuilder("[");
      boolean first = true;
      for (Object item : iterable) {
        if (!first) sb.append(",");
        first = false;
        sb.append(toJson(item, depth + 1, seen));
      }
      return sb.append("]").toString();
    }
    if (cls.getName().startsWith("java.")) {
      return q(String.valueOf(value));
    }
    StringBuilder sb = new StringBuilder("{");
    boolean first = true;
    for (java.lang.reflect.Field field : cls.getDeclaredFields()) {
      if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
      field.setAccessible(true);
      try {
        Object fieldValue = field.get(value);
        if (!first) sb.append(",");
        first = false;
        sb.append(q(field.getName())).append(":").append(toJson(fieldValue, depth + 1, seen));
      } catch (IllegalAccessException ignored) {
      }
    }
    return sb.append("}").toString();
  }
}
"""
