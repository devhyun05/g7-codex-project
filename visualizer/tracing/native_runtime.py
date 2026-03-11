from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .native_precise import precise_trace_cpp, precise_trace_java

EMPTY_ANALYSIS = {
    "structures": [],
    "intent_map": {},
    "summary": "",
    "intents": {"sorting": False, "sorting_order": "unknown"},
}


@dataclass
class FunctionBlock:
    name: str
    params: list[str]
    start: int
    end: int


class NativeExecutionTracer:
    supported_languages = {"java", "cpp"}

    def trace(self, code: str, stdin: str = "", language: str = "java") -> dict[str, Any]:
        normalized_language = (language or "").strip().lower()
        if normalized_language not in self.supported_languages:
            return self._error_result(
                code=code,
                stdin=stdin,
                language=normalized_language or "unknown",
                analysis=EMPTY_ANALYSIS,
                error=f"Unsupported language: {language}",
                display_error="Unsupported language.",
            )

        normalized_code = code.replace("\r\n", "\n")
        analysis = analyze_native_code_structures(normalized_code, normalized_language)

        precise_result = self._trace_precise(normalized_code, stdin, normalized_language, analysis)
        if precise_result is not None:
            precise_steps = self._merge_precise_with_static(
                code=normalized_code,
                analysis=analysis,
                language=normalized_language,
                precise_steps=precise_result.steps,
                stdout=precise_result.stdout,
            )
            return {
                "ok": precise_result.ok,
                "code": normalized_code,
                "stdin": stdin,
                "language": normalized_language,
                "steps": precise_steps,
                "stdout": precise_result.stdout,
                "error": precise_result.error,
                "display_error": precise_result.display_error,
                "analysis": analysis,
            }

        compile_result = self._compile_and_run(normalized_code, stdin, normalized_language)
        if compile_result["error"]:
            return self._error_result(
                code=normalized_code,
                stdin=stdin,
                language=normalized_language,
                analysis=analysis,
                error=compile_result["error"],
                display_error=compile_result["display_error"],
                stdout=compile_result["stdout"],
            )

        steps = self._build_steps(
            code=normalized_code,
            stdout=compile_result["stdout"],
            analysis=analysis,
            language=normalized_language,
        )
        return {
            "ok": True,
            "code": normalized_code,
            "stdin": stdin,
            "language": normalized_language,
            "steps": steps,
            "stdout": compile_result["stdout"],
            "error": None,
            "display_error": None,
            "analysis": analysis,
        }

    def _trace_precise(
        self,
        code: str,
        stdin: str,
        language: str,
        analysis: dict[str, Any],
    ):
        if language == "java":
            javac_path = self._find_command(["javac"])
            java_path = self._find_command(["java"])
            if javac_path and java_path:
                result = precise_trace_java(code, stdin, analysis, javac_path, java_path)
                if result.steps or result.ok:
                    return result
        if language == "cpp":
            compiler_path = self._find_command(["clang++", "g++"])
            python311_dir = self._find_python311_dir()
            if compiler_path and python311_dir:
                result = precise_trace_cpp(code, stdin, analysis, compiler_path, python311_dir)
                if result.steps or result.ok:
                    return result
        return None

    def _merge_precise_with_static(
        self,
        code: str,
        analysis: dict[str, Any],
        language: str,
        precise_steps: list[dict[str, Any]],
        stdout: str,
    ) -> list[dict[str, Any]]:
        if not precise_steps:
            return precise_steps

        static_steps = self._build_steps(code=code, stdout=stdout, analysis=analysis, language=language)
        static_by_line = {
            (step.get("line"), step.get("event")): step
            for step in static_steps
            if step.get("line") is not None
        }
        merged: list[dict[str, Any]] = []
        fallback_graph = next((step.get("graph") for step in reversed(static_steps) if step.get("graph")), None)
        fallback_structure = next((step.get("structure") for step in reversed(static_steps) if step.get("structure")), None)
        for step in precise_steps:
            static_step = static_by_line.get((step.get("line"), "line")) or static_by_line.get((step.get("line"), step.get("event")))
            if static_step:
                if not step.get("graph"):
                    step["graph"] = static_step.get("graph")
                if not step.get("structure"):
                    step["structure"] = static_step.get("structure")
                if static_step.get("globals"):
                    merged_globals = dict(static_step["globals"])
                    merged_globals.update(step.get("globals", {}))
                    step["globals"] = merged_globals
            merged.append(step)

        if merged:
            end_step = dict(merged[-1])
            end_step["event"] = "end"
            end_step["stdout"] = stdout
            end_step["stack"] = []
            if not end_step.get("graph"):
                end_step["graph"] = fallback_graph
            if not end_step.get("structure"):
                end_step["structure"] = fallback_structure
            end_step["message"] = f"{language.upper()} execution finished."
            end_step["explanation"] = "Final runtime state after execution completed."
            end_step["explanation_json"] = {
                "summary": f"{language.upper()} runtime trace completed.",
                "line_explanations": [],
                "improvements": merged[-1].get("explanation_json", {}).get("improvements", []),
            }
            merged.append(end_step)

        for index, step in enumerate(merged, start=1):
            step["index"] = index
        return merged

    def _compile_and_run(self, code: str, stdin: str, language: str) -> dict[str, str | None]:
        if language == "java":
            return self._compile_and_run_java(code, stdin)
        return self._compile_and_run_cpp(code, stdin)

    def _compile_and_run_java(self, code: str, stdin: str) -> dict[str, str | None]:
        class_name = self._detect_java_class_name(code)
        if not class_name:
            return {
                "stdout": "",
                "error": "Java class not found",
                "display_error": "No runnable Java class was found.",
            }

        javac_path = self._find_command(["javac"])
        java_path = self._find_command(["java"])
        if not javac_path or not java_path:
            return {
                "stdout": "",
                "error": "Java toolchain missing",
                "display_error": "javac/java was not found in PATH.",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir, f"{class_name}.java")
            source_path.write_text(code, encoding="utf-8")

            compile_process = subprocess.run(
                [javac_path, str(source_path)],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if compile_process.returncode != 0:
                return {
                    "stdout": compile_process.stdout or "",
                    "error": compile_process.stderr.strip() or "javac failed",
                    "display_error": self._format_tool_error(compile_process.stderr, "Java compile"),
                }

            run_process = subprocess.run(
                [java_path, "-cp", temp_dir, class_name],
                cwd=temp_dir,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
            if run_process.returncode != 0:
                combined = (run_process.stderr or run_process.stdout or "").strip()
                return {
                    "stdout": run_process.stdout or "",
                    "error": combined or "java failed",
                    "display_error": self._format_tool_error(combined, "Java run"),
                }
            return {"stdout": run_process.stdout or "", "error": None, "display_error": None}

    def _compile_and_run_cpp(self, code: str, stdin: str) -> dict[str, str | None]:
        compiler_path = self._find_command(["clang++", "g++"])
        if not compiler_path:
            return {
                "stdout": "",
                "error": "C++ compiler missing",
                "display_error": "clang++/g++ was not found in PATH.",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir, "main.cpp")
            binary_path = Path(temp_dir, "program.exe")
            source_path.write_text(code, encoding="utf-8")

            compile_process = subprocess.run(
                [compiler_path, "-std=c++17", str(source_path), "-o", str(binary_path)],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=20,
                encoding="utf-8",
                errors="replace",
            )
            if compile_process.returncode != 0:
                return {
                    "stdout": compile_process.stdout or "",
                    "error": compile_process.stderr.strip() or "c++ compile failed",
                    "display_error": self._format_tool_error(compile_process.stderr, "C++ compile"),
                }

            run_process = subprocess.run(
                [str(binary_path)],
                cwd=temp_dir,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
            if run_process.returncode != 0:
                combined = (run_process.stderr or run_process.stdout or "").strip()
                return {
                    "stdout": run_process.stdout or "",
                    "error": combined or "c++ run failed",
                    "display_error": self._format_tool_error(combined, "C++ run"),
                }
            return {"stdout": run_process.stdout or "", "error": None, "display_error": None}

    def _build_steps(
        self,
        code: str,
        stdout: str,
        analysis: dict[str, Any],
        language: str,
    ) -> list[dict[str, Any]]:
        lines = code.splitlines()
        tracker = NativeStateTracker(analysis=analysis)
        functions = collect_function_blocks(lines, language)
        call_tree = build_static_call_tree(lines, functions)
        steps: list[dict[str, Any]] = []

        for line_number, line_source in enumerate(lines, start=1):
            stripped = line_source.strip()
            if not stripped or stripped.startswith("//"):
                continue

            tracker.consume(stripped)
            active_function = find_enclosing_function(functions, line_number)
            snapshot = {
                "index": len(steps) + 1,
                "event": "line",
                "line": line_number,
                "line_source": line_source,
                "line_detail": describe_native_line(stripped, language),
                "message": build_line_message(active_function, line_number, language),
                "stdout": "",
                "stack": build_stack_payload(active_function, line_number),
                "globals": tracker.serialized_globals(),
                "call_tree": activate_call_tree(call_tree, active_function, line_number),
                "graph": tracker.graph_state(analysis),
                "structure": tracker.structure_state(analysis),
            }
            snapshot["explanation"] = snapshot["line_detail"]
            snapshot["explanation_json"] = {
                "summary": f"Read the {language.upper()} code top to bottom and mapped it into the shared UI schema.",
                "line_explanations": [
                    {
                        "line": line_number,
                        "code": line_source,
                        "description": snapshot["line_detail"],
                    }
                ],
                "improvements": build_improvements(analysis, language),
            }
            steps.append(snapshot)

        steps.append(
            {
                "index": len(steps) + 1,
                "event": "end",
                "line": None,
                "line_source": "",
                "line_detail": "",
                "message": f"{language.upper()} execution finished.",
                "stdout": stdout,
                "stack": [],
                "globals": tracker.serialized_globals(),
                "call_tree": activate_call_tree(call_tree, None, None),
                "graph": tracker.graph_state(analysis),
                "structure": tracker.structure_state(analysis),
                "explanation": "Compilation and execution completed. This is the final state.",
                "explanation_json": {
                    "summary": f"{language.upper()} program finished successfully.",
                    "line_explanations": [],
                    "improvements": build_improvements(analysis, language),
                },
            }
        )
        return steps

    def _detect_java_class_name(self, code: str) -> str | None:
        public_match = re.search(r"\bpublic\s+class\s+([A-Za-z_]\w*)", code)
        if public_match:
            return public_match.group(1)
        class_match = re.search(r"\bclass\s+([A-Za-z_]\w*)", code)
        if class_match:
            return class_match.group(1)
        return None

    def _find_command(self, candidates: list[str]) -> str | None:
        for candidate in candidates:
            result = subprocess.run(
                ["where", candidate],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                first = next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)
                if first:
                    return first
        for candidate in candidates:
            for path in fallback_command_paths(candidate):
                if path.exists():
                    return str(path)
        return None

    def _format_tool_error(self, raw_error: str | None, stage: str) -> str:
        detail = (raw_error or "").strip()
        if not detail:
            return f"{stage} failed."
        return f"{stage} failed: {detail.splitlines()[0]}"

    def _find_python311_dir(self) -> str | None:
        result = subprocess.run(
            ["py", "-3.11", "-c", "import sys, pathlib; print(pathlib.Path(sys.executable).parent)"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
        return None

    def _error_result(
        self,
        code: str,
        stdin: str,
        language: str,
        analysis: dict[str, Any],
        error: str,
        display_error: str,
        stdout: str = "",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "code": code,
            "stdin": stdin,
            "language": language,
            "steps": [],
            "stdout": stdout,
            "error": error,
            "display_error": display_error,
            "analysis": analysis,
        }


class NativeStateTracker:
    def __init__(self, analysis: dict[str, Any]):
        self.analysis = analysis
        self.values: dict[str, dict[str, Any]] = {}

    def consume(self, line: str) -> None:
        self._parse_literal_assignment(line)
        self._apply_mutation(line)
        self._apply_sort(line)

    def serialized_globals(self) -> dict[str, Any]:
        serialized: dict[str, Any] = {}
        for name, value in sorted(self.values.items()):
            if value["type"] == "list":
                serialized[name] = serialize_list(value["items"])
        return serialized

    def graph_state(self, analysis: dict[str, Any]) -> dict[str, Any] | None:
        for structure in analysis.get("structures", []):
            if structure["kind"] != "graph":
                continue
            value = self.values.get(structure["name"])
            if value and value["type"] == "graph":
                return value["graph"]
        return None

    def structure_state(self, analysis: dict[str, Any]) -> dict[str, Any] | None:
        for structure in analysis.get("structures", []):
            name = structure["name"]
            value = self.values.get(name)
            if structure["kind"] == "stack":
                items = value["items"] if value and value["type"] == "list" else []
                return {
                    "kind": "stack",
                    "name": name,
                    "items": [repr(item) for item in items],
                    "truncated": False,
                    "top_index": len(items) - 1 if items else None,
                }
            if structure["kind"] == "queue":
                items = value["items"] if value and value["type"] == "list" else []
                return {
                    "kind": "queue",
                    "name": name,
                    "items": [repr(item) for item in items],
                    "truncated": False,
                    "front_index": 0 if items else None,
                    "back_index": len(items) - 1 if items else None,
                }
            if structure["kind"] == "tree":
                return {
                    "kind": "tree",
                    "name": name,
                    "root": {"id": f"{name}-root", "label": name, "children": []},
                    "current_id": f"{name}-root",
                }
        return None

    def _parse_literal_assignment(self, line: str) -> None:
        array_match = re.search(
            r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>\{.*\}|new\s+[A-Za-z_][\w<>\[\]]*\s*\{.*\})\s*;",
            line,
        )
        if array_match:
            name = array_match.group("name")
            value = strip_constructor_prefix(array_match.group("value"))
            parsed = parse_brace_literal(value)
            if parsed is None:
                return
            if parsed and all(isinstance(item, list) for item in parsed):
                self.values[name] = {"type": "graph", "graph": build_graph_payload(name, parsed)}
                return
            self.values[name] = {"type": "list", "items": parsed}
            return

        java_empty_match = re.search(
            r"(?P<name>[A-Za-z_]\w*)\s*=\s*new\s+(ArrayDeque|LinkedList|Stack|ArrayList|Vector)\b",
            line,
        )
        if java_empty_match:
            self.values[java_empty_match.group("name")] = {"type": "list", "items": []}
            return

        cpp_empty_match = re.search(
            r"(?:stack|queue|deque|vector)\s*<.*?>\s+(?P<name>[A-Za-z_]\w*)\s*(?:;|=\s*\{\s*\};)",
            line,
        )
        if cpp_empty_match:
            self.values[cpp_empty_match.group("name")] = {"type": "list", "items": []}

    def _apply_mutation(self, line: str) -> None:
        push_match = re.search(
            r"(?P<name>[A-Za-z_]\w*)\.(?:push|push_back|add|offer|append)\((?P<value>.+?)\)\s*;",
            line,
        )
        if push_match:
            self._ensure_list(push_match.group("name")).append(parse_scalar(push_match.group("value")))
            return

        pop_zero_match = re.search(r"(?P<name>[A-Za-z_]\w*)\.(?:poll|remove)\(\s*0?\s*\)\s*;", line)
        if pop_zero_match:
            items = self._ensure_list(pop_zero_match.group("name"))
            if items:
                items.pop(0)
            return

        pop_match = re.search(r"(?P<name>[A-Za-z_]\w*)\.(?:pop|pop_back)\(\s*\)\s*;", line)
        if pop_match:
            items = self._ensure_list(pop_match.group("name"))
            if items:
                items.pop()

    def _apply_sort(self, line: str) -> None:
        java_sort = re.search(r"Arrays\.sort\((?P<name>[A-Za-z_]\w*)\)", line)
        if java_sort:
            self._ensure_list(java_sort.group("name")).sort(key=sort_key)
            return

        cpp_sort = re.search(
            r"sort\(\s*(?P<name>[A-Za-z_]\w*)\.begin\(\)\s*,\s*(?P=name)\.end\(\)\s*\)",
            line,
        )
        if cpp_sort:
            self._ensure_list(cpp_sort.group("name")).sort(key=sort_key)

    def _ensure_list(self, name: str) -> list[Any]:
        value = self.values.setdefault(name, {"type": "list", "items": []})
        value["type"] = "list"
        return value.setdefault("items", [])


def analyze_native_code_structures(code: str, language: str) -> dict[str, Any]:
    hints: dict[str, tuple[str, str, int]] = {}
    sorting_detected = False

    def set_hint(name: str, kind: str, reason: str, score: int) -> None:
        current = hints.get(name)
        if current and current[2] >= score:
            return
        hints[name] = (kind, reason, score)

    for raw_line in code.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        lowered = line.lower()
        if any(token in lowered for token in ["sort(", "arrays.sort", "collections.sort"]):
            sorting_detected = True

        stack_name = infer_container_name(line, ["stack"], ["push", "pop"])
        if stack_name:
            set_hint(stack_name, "stack", f"{language.upper()} stack-like pattern detected.", 90)

        queue_name = infer_container_name(line, ["queue", "deque"], ["offer", "poll", "remove"])
        if queue_name:
            set_hint(queue_name, "queue", f"{language.upper()} queue-like pattern detected.", 90)

        graph_name = infer_graph_name(line)
        if graph_name:
            set_hint(graph_name, "graph", f"{language.upper()} graph-like structure detected.", 92)

        tree_name = infer_tree_name(line)
        if tree_name:
            set_hint(tree_name, "tree", f"{language.upper()} tree-like structure detected.", 88)

    structures = [
        {"kind": kind, "name": name, "reason": reason}
        for name, (kind, reason, _score) in sorted(hints.items(), key=lambda item: (-item[1][2], item[0]))
    ]
    summary = ", ".join(f"{item['kind']}({item['name']})" for item in structures)
    return {
        "structures": structures,
        "intent_map": {name: kind for name, (kind, _reason, _score) in hints.items()},
        "summary": summary,
        "intents": {"sorting": sorting_detected, "sorting_order": "unknown"},
    }


def infer_container_name(line: str, keywords: list[str], methods: list[str]) -> str | None:
    lowered = line.lower()
    if any(keyword in lowered for keyword in keywords):
        match = re.search(r"([A-Za-z_]\w*)\s*(?:=|;|\.)", line)
        if match:
            return match.group(1)
    method_match = re.search(
        rf"(?P<name>[A-Za-z_]\w*)\.(?:{'|'.join(re.escape(method) for method in methods)})\b",
        line,
    )
    if method_match:
        return method_match.group("name")
    return None


def infer_graph_name(line: str) -> str | None:
    lowered = line.lower()
    if any(token in lowered for token in ["graph", "adj", "adjlist", "adj_list"]):
        match = re.search(r"([A-Za-z_]\w*)\s*=", line)
        if match:
            return match.group(1)
    if re.search(r"(vector<vector|int\[\]\[|list<list|list<arraylist)", lowered):
        match = re.search(r"([A-Za-z_]\w*)\s*=", line)
        if match:
            return match.group(1)
    return None


def infer_tree_name(line: str) -> str | None:
    if re.search(r"\b(class|struct)\s+\w*Node\b", line):
        return "root"
    if re.search(r"\b(left|right|children)\b", line):
        match = re.search(r"([A-Za-z_]\w*)\s*=", line)
        if match:
            return match.group(1)
    return None


def serialize_list(items: list[Any]) -> dict[str, Any]:
    return {
        "type": "list",
        "repr": repr(items),
        "items": [
            {
                "type": type(item).__name__,
                "repr": repr(item),
                "value": item,
            }
            for item in items
        ],
        "truncated": False,
    }


def strip_constructor_prefix(value: str) -> str:
    brace_index = value.find("{")
    return value[brace_index:] if brace_index >= 0 else value


def parse_brace_literal(text: str) -> list[Any] | None:
    text = text.strip()
    if not text.startswith("{") or not text.endswith("}"):
        return None

    translated = []
    in_string = False
    quote_char = ""
    for char in text:
        if char in {"'", '"'}:
            if in_string and char == quote_char:
                in_string = False
                quote_char = ""
            elif not in_string:
                in_string = True
                quote_char = char
            translated.append('"')
            continue
        if not in_string and char == "{":
            translated.append("[")
            continue
        if not in_string and char == "}":
            translated.append("]")
            continue
        translated.append(char)

    try:
        parsed = json.loads("".join(translated))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def parse_scalar(raw: str) -> Any:
    value = raw.strip().rstrip(";")
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def build_graph_payload(name: str, rows: list[list[Any]]) -> dict[str, Any]:
    nodes = {str(index) for index in range(len(rows))}
    edges: list[dict[str, str]] = []
    for index, targets in enumerate(rows):
        for target in targets:
            edges.append({"source": str(index), "target": str(target)})
            nodes.add(str(target))

    sorted_nodes = sorted(nodes, key=sort_key)
    return {
        "name": name,
        "nodes": [
            {"id": node, "label": node, "current": False, "visited": False}
            for node in sorted_nodes
        ],
        "edges": edges,
        "tree_mode": len(edges) == max(len(sorted_nodes) - 1, 0),
    }


def collect_function_blocks(lines: list[str], language: str) -> list[FunctionBlock]:
    functions: list[FunctionBlock] = []
    index = 0
    while index < len(lines):
        signature = detect_function_signature(lines[index].strip(), language)
        if not signature:
            index += 1
            continue

        brace_depth = lines[index].count("{") - lines[index].count("}")
        end = index + 1
        while end < len(lines) and brace_depth > 0:
            brace_depth += lines[end].count("{") - lines[end].count("}")
            end += 1
        functions.append(
            FunctionBlock(
                name=signature["name"],
                params=signature["params"],
                start=index + 1,
                end=end,
            )
        )
        index = end
    return functions


def detect_function_name(line: str, language: str) -> str | None:
    signature = detect_function_signature(line, language)
    return signature["name"] if signature else None


def detect_function_signature(line: str, language: str) -> dict[str, Any] | None:
    if line.startswith(("if ", "if(", "for ", "for(", "while ", "while(", "switch ", "switch(")):
        return None
    if language == "java":
        match = re.search(
            r"(?:public|private|protected|static|final|synchronized|native|abstract|\s)+[\w<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\(([^;]*)\)\s*(?:throws\s+[\w<>\., ]+)?\s*\{",
            line,
        )
        if not match:
            return None
        return {"name": match.group(1), "params": parse_parameter_names(match.group(2))}
    match = re.search(
        r"(?:[\w:<>\*&]+\s+)+([A-Za-z_]\w*)\s*\(([^;]*)\)\s*(?:const)?\s*\{",
        line,
    )
    if not match:
        return None
    return {"name": match.group(1), "params": parse_parameter_names(match.group(2))}


def parse_parameter_names(raw_params: str) -> list[str]:
    params: list[str] = []
    if not raw_params.strip():
        return params
    for item in split_arguments(raw_params):
        cleaned = item.strip()
        if not cleaned:
            continue
        match = re.search(r"([A-Za-z_]\w*)\s*$", cleaned)
        if match:
            params.append(match.group(1))
    return params


def build_static_call_tree(lines: list[str], functions: list[FunctionBlock]) -> dict[str, Any]:
    root = {"id": "root", "label": "module", "status": "running", "line": None, "children": []}
    if not functions:
        return root

    name_map = {function.name: function for function in functions}
    entry = name_map.get("main") or functions[0]
    root["children"].append(
        build_call_node(
            lines=lines,
            function=entry,
            name_map=name_map,
            seen={},
            call_args=None,
            node_id=f"{entry.name}-0",
        )
    )
    return root


def build_call_node(
    lines: list[str],
    function: FunctionBlock,
    name_map: dict[str, FunctionBlock],
    seen: dict[str, int],
    call_args: list[str] | None,
    node_id: str,
) -> dict[str, Any]:
    label = format_static_call_label(function.name, function.params, call_args)
    node = {
        "id": node_id,
        "label": label,
        "status": "running",
        "line": function.start,
        "locals": {},
        "children": [],
    }
    current_depth = seen.get(function.name, 0)
    if current_depth >= 3:
        return node

    substitutions = build_param_substitutions(function.params, call_args)
    next_seen = dict(seen)
    next_seen[function.name] = current_depth + 1
    body = lines[function.start:function.end - 1]
    child_index = 0
    for line in body:
        for call_name, args in extract_call_sites(line, name_map):
            called_block = name_map.get(call_name)
            if not called_block:
                continue
            resolved_args = [substitute_param_refs(arg, substitutions) for arg in args]
            child_index += 1
            node["children"].append(
                build_call_node(
                    lines=lines,
                    function=called_block,
                    name_map=name_map,
                    seen=next_seen,
                    call_args=resolved_args,
                    node_id=f"{node_id}-{call_name}-{child_index}",
                )
            )
    return node


def format_static_call_label(name: str, params: list[str], call_args: list[str] | None) -> str:
    if not params:
        return f"{name}()"
    if not call_args:
        joined = ", ".join(params[:3])
        suffix = ", ..." if len(params) > 3 else ""
        return f"{name}({joined}{suffix})"
    pairs = [f"{param}={arg}" for param, arg in zip(params, call_args)]
    if len(call_args) > len(params):
        pairs.extend(call_args[len(params):])
    joined = ", ".join(pairs[:3])
    suffix = ", ..." if len(pairs) > 3 else ""
    return f"{name}({joined}{suffix})"


def build_param_substitutions(params: list[str], call_args: list[str] | None) -> dict[str, str]:
    if not call_args:
        return {}
    return {
        param: arg.strip()
        for param, arg in zip(params, call_args)
        if arg and arg.strip()
    }


def extract_call_sites(line: str, name_map: dict[str, FunctionBlock]) -> list[tuple[str, list[str]]]:
    call_sites: list[tuple[str, list[str]]] = []
    for called_name in name_map:
        for match in re.finditer(rf"\b{re.escape(called_name)}\s*\(", line):
            start = match.end()
            end = find_matching_paren(line, start - 1)
            if end < 0:
                continue
            args = split_arguments(line[start:end])
            call_sites.append((called_name, args))
    return call_sites


def find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def split_arguments(text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    for char in text:
        if char == "," and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
            item = "".join(current).strip()
            if item:
                args.append(item)
            current = []
            continue
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(paren_depth - 1, 0)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(bracket_depth - 1, 0)
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(brace_depth - 1, 0)
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


def substitute_param_refs(expression: str, substitutions: dict[str, str]) -> str:
    result = expression.strip()
    for name, value in substitutions.items():
        result = re.sub(rf"\b{re.escape(name)}\b", f"({value})", result)
    result = re.sub(r"\s+", " ", result).strip()
    return simplify_parenthesized_literal(result)


def simplify_parenthesized_literal(expression: str) -> str:
    simplified = expression
    while True:
        next_value = re.sub(r"\((-?\d+)\)", r"\1", simplified)
        if next_value == simplified:
            return simplified
        simplified = next_value


def find_enclosing_function(functions: list[FunctionBlock], line_number: int) -> str | None:
    for function in functions:
        if function.start <= line_number <= function.end:
            return function.name
    return None


def build_stack_payload(active_function: str | None, line_number: int) -> list[dict[str, Any]]:
    if not active_function:
        return []
    return [
        {
            "name": active_function,
            "label": f"{active_function}()",
            "line": line_number,
            "active": True,
            "node_id": active_function,
            "locals": {},
        }
    ]


def activate_call_tree(tree: dict[str, Any], active_function: str | None, line_number: int | None) -> dict[str, Any]:
    copied = {
        "id": tree["id"],
        "label": tree["label"],
        "status": tree.get("status", "running"),
        "line": line_number if tree["id"] == active_function else tree.get("line"),
        "active": tree["id"] == active_function,
        "return_value": tree.get("return_value"),
        "error": tree.get("error"),
        "locals": tree.get("locals", {}),
        "children": [],
    }
    for child in tree.get("children", []):
        copied["children"].append(activate_call_tree(child, active_function, line_number))
    return copied


def describe_native_line(line: str, language: str) -> str:
    if any(token in line for token in ["Arrays.sort", "Collections.sort", "sort("]):
        return f"{language.upper()} sorting logic is running."
    if any(token in line for token in [".push(", ".push_back(", ".add(", ".offer("]):
        return "A value is being inserted into a container."
    if any(token in line for token in [".pop()", ".pop_back()", ".poll()", ".remove("]):
        return "A value is being removed from a container."
    if line.startswith(("if", "else if")):
        return "A condition is being evaluated."
    if line.startswith(("for", "while")):
        return "A loop step is being processed."
    if "=" in line:
        return "A variable is being assigned or updated."
    return f"{language.upper()} code is being interpreted for visualization."


def build_line_message(active_function: str | None, line_number: int, language: str) -> str:
    if active_function:
        return f"Processed line {line_number} inside {active_function}."
    return f"Processed line {line_number} in {language.upper()} code."


def build_improvements(analysis: dict[str, Any], language: str) -> list[str]:
    improvements: list[str] = []
    if language != "python":
        improvements.append("Native languages currently use compiler execution plus static step simulation.")
    if analysis.get("intents", {}).get("sorting"):
        improvements.append("Use clear array names like arr or values to make sorting visuals easier to read.")
    if not analysis.get("structures"):
        improvements.append("Use structure-specific names like stack, queue, graph, or root for richer visuals.")
    return improvements


def sort_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, int):
        return (0, value)
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def fallback_command_paths(command: str) -> list[Path]:
    if command == "clang++":
        return [Path("C:/Program Files/LLVM/bin/clang++.exe")]
    if command == "javac":
        return [Path("C:/Program Files/Java/bin/javac.exe")]
    if command == "java":
        return [Path("C:/Program Files/Java/bin/java.exe")]
    return []
