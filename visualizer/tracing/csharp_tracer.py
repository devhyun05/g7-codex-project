from __future__ import annotations

import json
import locale
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENTER_PREFIX = "__ENTER__|"
STEP_PREFIX = "__STEP__|"
EXIT_PREFIX = "__EXIT__|"

METHOD_PATTERN = re.compile(
    r"(?P<prefix>(?:public|private|protected|internal|static|virtual|override|sealed|async|\s)+)?"
    r"(?P<return_type>[\w<>\[\],?.]+)\s+"
    r"(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
)
FIELD_PATTERN = re.compile(
    r"^\s*(?:public|private|protected|internal)?\s*static\s+(?:readonly\s+)?[\w<>\[\],?.]+\s+(?P<name>\w+)\s*="
)
DECLARATION_PATTERN = re.compile(r"^\s*(?:var|[\w<>\[\],?.]+)\s+(?P<name>\w+)\s*=")
CONTROL_HEADER_PREFIXES = ("if ", "if(", "for ", "for(", "foreach", "while", "switch", "catch", "using ")
SKIP_SNAPSHOT_PREFIXES = ("//", "else", "catch", "finally", "case ", "default:")


@dataclass
class MethodScope:
    name: str
    line_number: int
    params: list[str]
    known_vars: list[str]
    brace_depth: int = 0


class CSharpLineTracer:
    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        dotnet = shutil.which("dotnet")
        if dotnet is None:
            return self._result(code, stdin, [], "", "Required runtime was not found: dotnet.")

        instrumented = self._instrument_code(code)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "Program.cs"
            project_path = temp_path / "Runner.csproj"
            source_path.write_text(instrumented, encoding="utf-8")
            project_path.write_text(
                "\n".join(
                    [
                        '<Project Sdk="Microsoft.NET.Sdk">',
                        "  <PropertyGroup>",
                        "    <OutputType>Exe</OutputType>",
                        "    <TargetFramework>net6.0</TargetFramework>",
                        "    <ImplicitUsings>enable</ImplicitUsings>",
                        "    <Nullable>enable</Nullable>",
                        "    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>",
                        "    <NoWarn>CS8604</NoWarn>",
                        "  </PropertyGroup>",
                        "</Project>",
                    ]
                ),
                encoding="utf-8",
            )

            build = self._run_process([dotnet, "build", str(project_path), "-nologo", "-v", "q"], temp_path, "")
            if build.returncode != 0:
                return self._result(code, stdin, [], "", self._collect_error_text(build))

            dll_path = temp_path / "bin" / "Debug" / "net6.0" / "Runner.dll"
            run = self._run_process([dotnet, str(dll_path)], temp_path, stdin)
            events, other_stderr = self._parse_event_stream(run.stderr)
            analysis = self._analyze_code(code)
            steps = self._build_steps(
                code,
                events,
                run.stdout,
                other_stderr if run.returncode != 0 else "",
                analysis,
            )
            error = other_stderr if run.returncode != 0 else None
            return self._result(code, stdin, steps, run.stdout, error, analysis)

    def _instrument_code(self, code: str) -> str:
        lines = code.splitlines()
        class_fields = self._collect_static_fields(lines)
        instrumented: list[str] = []
        pending_scope: MethodScope | None = None
        active_scopes: list[MethodScope] = []

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            indent = line[: len(line) - len(line.lstrip())]

            signature = self._parse_method_signature(stripped, index)
            if signature:
                pending_scope = signature

            instrumented.append(line)

            if pending_scope and "{" in line:
                pending_scope.brace_depth = line.count("{") - line.count("}")
                active_scopes.append(pending_scope)
                enter_payload = self._tuple_args(self._snapshot_variables(class_fields, pending_scope))
                instrumented.append(
                    f'{indent}    __Trace.Enter({pending_scope.line_number}, "{pending_scope.name}", {enter_payload});'
                )
                pending_scope = None
                continue

            if not active_scopes:
                continue

            scope = active_scopes[-1]
            self._register_declared_variables(stripped, scope)

            if self._should_capture_statement(stripped):
                snapshot_payload = self._tuple_args(self._snapshot_variables(class_fields, scope))
                if self._is_return_statement(stripped):
                    instrumented[-1] = self._instrument_return_line(
                        line=line,
                        indent=indent,
                        stripped=stripped,
                        line_number=index,
                        method_name=scope.name,
                        snapshot_payload=snapshot_payload,
                    )
                else:
                    instrumented.append(f'{indent}__Trace.Step({index}, "{scope.name}", {snapshot_payload});')

            scope.brace_depth += line.count("{") - line.count("}")

            if stripped == "}" and scope.brace_depth <= 0:
                instrumented.insert(len(instrumented) - 1, f'{indent}__Trace.Exit({index}, "{scope.name}");')
                active_scopes.pop()

        helper = self._helper_code()
        insert_at = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("using ") or not stripped:
                insert_at = i + 1
                continue
            break

        combined = instrumented[:insert_at] + helper + instrumented[insert_at:]
        if not any(line.strip() == "using System;" for line in lines):
            combined.insert(0, "using System;")
        if not any(line.strip() == "using System.Text.Json;" for line in lines):
            combined.insert(1, "using System.Text.Json;")

        return "\n".join(combined)

    def _helper_code(self) -> list[str]:
        return [
            "static class __Trace",
            "{",
            "    public static void Enter(int line, string method, params (string Name, object? Value)[] items)",
            '        => Console.Error.WriteLine("__ENTER__|" + line + "|" + method + "|" + Serialize(items));',
            "    public static void Step(int line, string method, params (string Name, object? Value)[] items)",
            '        => Console.Error.WriteLine("__STEP__|" + line + "|" + method + "|" + Serialize(items));',
            "    public static void Exit(int line, string method)",
            '        => Console.Error.WriteLine("__EXIT__|" + line + "|" + method);',
            "    public static T Return<T>(int line, string method, T value, params (string Name, object? Value)[] items)",
            "    {",
            "        Step(line, method, items);",
            '        Console.Error.WriteLine("__EXIT__|" + line + "|" + method + "|" + FormatValue(value));',
            "        return value;",
            "    }",
            "    public static void ReturnVoid(int line, string method, params (string Name, object? Value)[] items)",
            "    {",
            "        Step(line, method, items);",
            "        Exit(line, method);",
            "    }",
            "    private static string Serialize((string Name, object? Value)[] items)",
            "    {",
            "        var dict = new Dictionary<string, object>();",
            "        foreach (var item in items)",
            "        {",
            "            dict[item.Name] = new Dictionary<string, string>",
            "            {",
            '                ["type"] = item.Value?.GetType().Name ?? "null",',
            '                ["repr"] = FormatValue(item.Value),',
            "            };",
            "        }",
            "        return JsonSerializer.Serialize(dict);",
            "    }",
            "    private static string FormatValue(object? value)",
            "    {",
            '        if (value is null) return "null";',
            '        if (value is string text) return text;',
            '        if (value is System.Text.StringBuilder builder) return builder.ToString();',
            "        if (value is System.Array array)",
            "        {",
            "            var items = new List<string>();",
            "            var index = 0;",
            "            foreach (var element in array)",
            "            {",
            '                if (index >= 8) { items.Add("..."); break; }',
            "                items.Add(FormatValue(element));",
            "                index += 1;",
            "            }",
            '            return "[" + string.Join(", ", items) + "]";',
            "        }",
            "        if (value is System.Collections.IEnumerable enumerable)",
            "        {",
            "            var items = new List<string>();",
            "            var index = 0;",
            "            foreach (var element in enumerable)",
            "            {",
            '                if (index >= 8) { items.Add("..."); break; }',
            "                items.Add(FormatValue(element));",
            "                index += 1;",
            "            }",
            '            return "[" + string.Join(", ", items) + "]";',
            "        }",
            "        return value.ToString() ?? string.Empty;",
            "    }",
            "}",
            "",
        ]

    def _collect_static_fields(self, lines: list[str]) -> list[str]:
        fields: list[str] = []
        for line in lines:
            match = FIELD_PATTERN.match(line)
            if match:
                fields.append(match.group("name"))
        return fields

    def _parse_method_signature(self, stripped: str, line_number: int) -> MethodScope | None:
        if not stripped or stripped.startswith("//"):
            return None
        if stripped.startswith(CONTROL_HEADER_PREFIXES):
            return None
        match = METHOD_PATTERN.search(stripped)
        if not match:
            return None

        params_text = match.group("params").strip()
        params = [self._extract_param_name(part) for part in params_text.split(",") if part.strip()]
        params = [name for name in params if name]
        return MethodScope(match.group("name"), line_number, params, list(params))

    def _extract_param_name(self, param_text: str) -> str | None:
        pieces = param_text.strip().split()
        return pieces[-1] if pieces else None

    def _register_declared_variables(self, stripped: str, scope: MethodScope) -> None:
        if stripped.startswith(("for ", "for(", "if ", "if(", "while ", "while(", "switch ", "switch(", "foreach")):
            return

        match = DECLARATION_PATTERN.search(stripped)
        if match:
            name = match.group("name")
            if name not in scope.known_vars:
                scope.known_vars.append(name)

    def _snapshot_variables(self, class_fields: list[str], scope: MethodScope) -> list[str]:
        names: list[str] = []
        for name in [*class_fields, *scope.known_vars]:
            if name not in names:
                names.append(name)
        return names

    def _tuple_args(self, names: list[str]) -> str:
        if not names:
            return ""
        return ", ".join(f'("{name}", (object?){name})' for name in names)

    def _should_capture_statement(self, stripped: str) -> bool:
        if not stripped or stripped in {"{", "}"}:
            return False
        if stripped.startswith(SKIP_SNAPSHOT_PREFIXES):
            return False
        if stripped.startswith(CONTROL_HEADER_PREFIXES):
            return False
        return ";" in stripped

    def _is_return_statement(self, stripped: str) -> bool:
        return stripped.startswith("return")

    def _instrument_return_line(
        self,
        line: str,
        indent: str,
        stripped: str,
        line_number: int,
        method_name: str,
        snapshot_payload: str,
    ) -> str:
        payload_suffix = f", {snapshot_payload}" if snapshot_payload else ""
        expression = self._extract_return_expression(stripped)
        if expression is None:
            return f'{indent}__Trace.ReturnVoid({line_number}, "{method_name}"{payload_suffix}); return;'
        return f'{indent}return __Trace.Return({line_number}, "{method_name}", {expression}{payload_suffix});'

    def _extract_return_expression(self, stripped: str) -> str | None:
        if stripped == "return;":
            return None
        if not stripped.startswith("return ") or not stripped.endswith(";"):
            return None
        expression = stripped[len("return ") : -1].strip()
        return expression or None

    def _parse_event_stream(self, stderr: str) -> tuple[list[dict[str, Any]], str]:
        events: list[dict[str, Any]] = []
        other_lines: list[str] = []

        for raw_line in stderr.splitlines():
            if raw_line.startswith(ENTER_PREFIX):
                payload = raw_line[len(ENTER_PREFIX):]
                line_text, _, rest = payload.partition("|")
                method_name, _, state_json = rest.partition("|")
                if line_text.isdigit():
                    events.append(
                        {
                            "kind": "enter",
                            "line": int(line_text),
                            "method": method_name,
                            "state": self._load_state_json(state_json),
                        }
                    )
                continue

            if raw_line.startswith(STEP_PREFIX):
                payload = raw_line[len(STEP_PREFIX):]
                line_text, _, rest = payload.partition("|")
                method_name, _, state_json = rest.partition("|")
                if line_text.isdigit():
                    events.append(
                        {
                            "kind": "step",
                            "line": int(line_text),
                            "method": method_name,
                            "state": self._load_state_json(state_json),
                        }
                    )
                continue

            if raw_line.startswith(EXIT_PREFIX):
                payload = raw_line[len(EXIT_PREFIX):]
                line_text, _, rest = payload.partition("|")
                method_name, _, return_value = rest.partition("|")
                if line_text.isdigit():
                    events.append(
                        {
                            "kind": "exit",
                            "line": int(line_text),
                            "method": method_name,
                            "return_value": return_value or None,
                        }
                    )
                continue

            other_lines.append(raw_line)

        return events, "\n".join(other_lines).strip()

    def _load_state_json(self, text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def _build_steps(
        self,
        code: str,
        events: list[dict[str, Any]],
        stdout: str,
        error: str,
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        code_lines = code.splitlines()
        steps: list[dict[str, Any]] = []
        call_root = {"id": "root", "label": "module", "status": "running", "line": None, "children": []}
        node_by_id = {"root": call_root}
        frame_stack: list[dict[str, Any]] = []
        call_index = 0

        def snapshot_tree(node: dict[str, Any], active_ids: set[str]) -> dict[str, Any]:
            return {
                "id": node["id"],
                "label": node["label"],
                "status": node.get("status", "running"),
                "line": node.get("line"),
                "active": node["id"] in active_ids,
                "return_value": node.get("return_value"),
                "error": node.get("error"),
                "locals": node.get("locals", {}),
                "children": [snapshot_tree(child, active_ids) for child in node.get("children", [])],
            }

        def merge_visible_state() -> dict[str, Any]:
            merged: dict[str, Any] = {}
            for frame in frame_stack:
                merged.update(frame.get("locals", {}))
            return merged

        def line_source(line_number: int | None) -> str:
            if line_number and 1 <= line_number <= len(code_lines):
                return code_lines[line_number - 1]
            return ""

        def format_label(method: str, state: dict[str, Any]) -> str:
            preview_parts: list[str] = []
            compact_items = [
                (name, value)
                for name, value in state.items()
                if "\n" not in value.get("repr", "")
                and len(value.get("repr", "")) <= 24
                and not value.get("type", "").endswith("[]")
            ]
            source_items = compact_items or list(state.items())
            for name, value in source_items[:3]:
                preview_parts.append(f"{name}={value.get('repr', '')}")
            joined = ", ".join(preview_parts)
            return f"{method}({joined})" if joined else f"{method}()"

        def stack_snapshot() -> list[dict[str, Any]]:
            return [
                {
                    "name": frame["name"],
                    "label": format_label(frame["name"], frame["locals"]),
                    "line": frame["line"],
                    "active": True,
                    "node_id": frame["node_id"],
                    "locals": frame["locals"],
                }
                for frame in frame_stack
            ]

        def append_step(event_kind: str, line_number: int, state: dict[str, Any], message: str) -> None:
            active_ids = {frame["node_id"] for frame in frame_stack}
            globals_snapshot = merge_visible_state()
            structure_state = self._detect_structure_state(globals_snapshot, analysis)
            steps.append(
                {
                    "index": len(steps) + 1,
                    "event": event_kind,
                    "line": line_number,
                    "line_source": line_source(line_number),
                    "message": message,
                    "stdout": stdout,
                    "stack": stack_snapshot(),
                    "globals": globals_snapshot,
                    "call_tree": snapshot_tree(call_root, active_ids),
                    "graph": None,
                    "structure": structure_state,
                    "explanation": self._build_explanation(
                        event_kind,
                        line_number,
                        line_source(line_number),
                        structure_state,
                    ),
                }
            )

        for event in events:
            if event["kind"] == "enter":
                call_index += 1
                node_id = f"call-{call_index}"
                parent_id = frame_stack[-1]["node_id"] if frame_stack else "root"
                state = event.get("state", {})
                node = {
                    "id": node_id,
                    "label": format_label(event["method"], state),
                    "status": "running",
                    "line": event["line"],
                    "locals": state,
                    "children": [],
                }
                node_by_id[node_id] = node
                node_by_id[parent_id]["children"].append(node)
                frame_stack.append(
                    {
                        "name": event["method"],
                        "line": event["line"],
                        "locals": state,
                        "node_id": node_id,
                    }
                )
                continue

            if event["kind"] == "step":
                if frame_stack:
                    frame_stack[-1]["locals"] = event.get("state", {})
                    frame_stack[-1]["line"] = event["line"]
                    current_node = node_by_id[frame_stack[-1]["node_id"]]
                    current_node["line"] = event["line"]
                    current_node["locals"] = event.get("state", {})
                    current_node["label"] = format_label(frame_stack[-1]["name"], event.get("state", {}))

                append_step(
                    "line",
                    event["line"],
                    event.get("state", {}),
                    f"C# {event['line']}번째 줄을 실행했습니다.",
                )
                continue

            if event["kind"] == "exit" and frame_stack:
                exiting = frame_stack[-1]
                node = node_by_id[exiting["node_id"]]
                node["status"] = "returned"
                node["line"] = event["line"]
                node["return_value"] = event.get("return_value")
                node["label"] = format_label(exiting["name"], exiting["locals"])
                append_step(
                    "return",
                    event["line"],
                    exiting["locals"],
                    f"{exiting['name']} 호출이 반환되었습니다.",
                )
                frame_stack.pop()

        steps.append(
            {
                "index": len(steps) + 1,
                "event": "error" if error else "end",
                "line": None,
                "line_source": "",
                "message": error or "Program execution finished.",
                "stdout": stdout,
                "stack": [],
                "globals": {},
                "call_tree": snapshot_tree(call_root, set()),
                "graph": None,
                "structure": None,
                "explanation": error or "Execution finished successfully.",
            }
        )
        return steps

    def _build_explanation(
        self,
        event_kind: str,
        line_number: int,
        line_source: str,
        structure: dict[str, Any] | None,
    ) -> str:
        structure_message = self._describe_structure(structure)
        if event_kind == "return":
            pieces = [f"{line_number}번째 줄에서 호출이 반환되었습니다.", f"현재 코드는 `{line_source.strip()}` 입니다."]
        else:
            pieces = [f"{line_number}번째 줄을 실행했습니다.", f"현재 코드는 `{line_source.strip()}` 입니다."]
        if structure_message:
            pieces.append(structure_message)
        else:
            pieces.append("감지된 자료구조가 없으면 호출 흐름과 변수 상태를 기준으로 설명합니다.")
        return " ".join(pieces)

    def _describe_structure(self, structure: dict[str, Any] | None) -> str:
        if not structure:
            return ""
        if structure["kind"] == "array":
            return f"`{structure['name']}` 배열의 현재 값 변화를 배열 형태로 보여줍니다."
        if structure["kind"] == "stack":
            return f"`{structure['name']}` 를 스택으로 판단해 top 기준으로 보여줍니다."
        if structure["kind"] == "queue":
            return f"`{structure['name']}` 를 큐로 판단해 front/back 기준으로 보여줍니다."
        if structure["kind"] == "tree":
            return f"`{structure['name']}` 를 트리로 판단해 노드 구조를 보여줍니다."
        return ""

    def _analyze_code(self, code: str) -> dict[str, Any]:
        hints: dict[str, dict[str, Any]] = {}

        def set_hint(name: str, kind: str, reason: str, score: int) -> None:
            existing = hints.get(name)
            if existing and existing["score"] >= score:
                return
            hints[name] = {"kind": kind, "reason": reason, "score": score}

        array_decl = re.finditer(r"\b[\w<>]+\[\]\s+(?P<name>\w+)\s*=", code)
        for match in array_decl:
            set_hint(match.group("name"), "array", "배열 선언으로 감지된 자료구조입니다.", 90)

        stack_decl = re.finditer(r"\bStack<[^>]+>\s+(?P<name>\w+)\s*=", code)
        for match in stack_decl:
            set_hint(match.group("name"), "stack", "C# Stack 컬렉션 선언으로 감지했습니다.", 92)

        queue_decl = re.finditer(r"\bQueue<[^>]+>\s+(?P<name>\w+)\s*=", code)
        for match in queue_decl:
            set_hint(match.group("name"), "queue", "C# Queue 컬렉션 선언으로 감지했습니다.", 92)

        list_decl = re.finditer(r"\bList<[^>]+>\s+(?P<name>\w+)\s*=", code)
        for match in list_decl:
            name = match.group("name")
            lowered = name.lower()
            if "stack" in lowered:
                set_hint(name, "stack", "이름과 List 사용 패턴을 기준으로 스택 후보로 감지했습니다.", 72)
            elif any(token in lowered for token in ("queue", "deque", "q")):
                set_hint(name, "queue", "이름과 List 사용 패턴을 기준으로 큐 후보로 감지했습니다.", 72)
            else:
                set_hint(name, "array", "리스트형 컬렉션을 배열형 시각화로 표시합니다.", 60)

        node_decl = re.finditer(r"\b(?P<name>\w+)\s*=\s*new\s+\w*Node\b", code)
        for match in node_decl:
            set_hint(match.group("name"), "tree", "Node 객체 생성 패턴으로 트리 후보를 감지했습니다.", 76)

        structures = [
            {"kind": hint["kind"], "name": name, "reason": hint["reason"]}
            for name, hint in sorted(hints.items(), key=lambda item: (-item[1]["score"], item[0]))
        ]
        summary = ", ".join(f"{item['kind']}({item['name']})" for item in structures)
        return {
            "structures": structures,
            "intent_map": {name: hint["kind"] for name, hint in hints.items()},
            "summary": summary,
        }

    def _detect_structure_state(
        self,
        globals_snapshot: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any] | None:
        intent_map = analysis.get("intent_map", {})
        candidates: list[tuple[int, dict[str, Any]]] = []

        for name, value in globals_snapshot.items():
            kind = intent_map.get(name)
            structure = self._coerce_structure(name, value, kind)
            if structure:
                candidates.append((structure.pop("_score"), structure))

        if not candidates:
            return None

        return sorted(candidates, key=lambda item: -item[0])[0][1]

    def _coerce_structure(
        self,
        name: str,
        value: dict[str, Any],
        hinted_kind: str | None,
    ) -> dict[str, Any] | None:
        repr_text = str(value.get("repr", ""))
        value_type = str(value.get("type", ""))
        items = self._parse_sequence_repr(repr_text)

        if (hinted_kind == "array" or value_type.endswith("[]")) and items is not None:
            return {
                "_score": 95 if hinted_kind == "array" else 82,
                "kind": "array",
                "name": name,
                "items": items[:8],
                "truncated": len(items) > 8 or repr_text.endswith("... ]"),
            }

        if (hinted_kind == "stack" or "stack" in name.lower() or "Stack" in value_type) and items is not None:
            return {
                "_score": 92 if hinted_kind == "stack" else 70,
                "kind": "stack",
                "name": name,
                "items": items[:8],
                "truncated": len(items) > 8,
                "top_index": len(items[:8]) - 1 if items else None,
            }

        if (hinted_kind == "queue" or "queue" in name.lower() or "Queue" in value_type) and items is not None:
            return {
                "_score": 92 if hinted_kind == "queue" else 70,
                "kind": "queue",
                "name": name,
                "items": items[:8],
                "truncated": len(items) > 8,
                "front_index": 0 if items else None,
                "back_index": len(items[:8]) - 1 if items else None,
            }

        return None

    def _parse_sequence_repr(self, repr_text: str) -> list[str] | None:
        stripped = repr_text.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            return None
        body = stripped[1:-1].strip()
        if not body:
            return []
        return [item.strip() for item in body.split(",") if item.strip()]

    def _run_process(self, command: list[str], cwd: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding=locale.getpreferredencoding(False) or "utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                env={
                    **os.environ,
                    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                    "DOTNET_NOLOGO": "1",
                    "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                },
                check=False,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(command, 124, stdout="", stderr=f"Execution exceeded {self.timeout_seconds:.1f} seconds.")

    def _collect_error_text(self, process: subprocess.CompletedProcess[str]) -> str:
        return "\n".join(part for part in [process.stdout.strip(), process.stderr.strip()] if part).strip() or "C# build failed."

    def _result(
        self,
        code: str,
        stdin: str,
        steps: list[dict[str, Any]],
        stdout: str,
        error: str | None,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "ok": error is None,
            "code": code,
            "stdin": stdin,
            "steps": steps,
            "stdout": stdout,
            "error": error,
            "analysis": analysis,
        }
