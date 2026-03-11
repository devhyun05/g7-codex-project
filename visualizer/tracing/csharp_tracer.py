from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRACE_PREFIX = "__TRACE__|"
STATE_PREFIX = "__STATE__|"

METHOD_PATTERN = re.compile(
    r"(?P<prefix>(?:public|private|protected|internal|static|virtual|override|sealed|async|\s)+)?"
    r"(?P<return_type>[\w<>\[\],?.]+)\s+"
    r"(?P<name>\w+)\s*\((?P<params>[^)]*)\)"
)
FIELD_PATTERN = re.compile(
    r"^\s*(?:public|private|protected|internal)?\s*static\s+(?:readonly\s+)?[\w<>\[\],?.]+\s+(?P<name>\w+)\s*="
)
DECLARATION_PATTERN = re.compile(
    r"^\s*(?:var|[\w<>\[\],?.]+)\s+(?P<name>\w+)\s*="
)

@dataclass
class MethodScope:
    name: str
    params: list[str]
    known_vars: list[str]
    brace_depth: int = 0


class CSharpLineTracer:
    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        dotnet = shutil.which("dotnet")
        if dotnet is None:
            return self._result(
                code=code,
                stdin=stdin,
                steps=[],
                stdout="",
                error="Required runtime was not found: dotnet.",
            )

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

            build = self._run_process(
                [dotnet, "build", str(project_path), "-nologo", "-v", "q"],
                temp_path,
                "",
            )
            if build.returncode != 0:
                events, other_stderr = self._parse_trace_stream(build.stderr)
                error_text = "\n".join(part for part in [build.stdout.strip(), other_stderr] if part).strip()
                steps = self._build_steps(code, events, "", error_text)
                return self._result(code=code, stdin=stdin, steps=steps, stdout="", error=error_text or "C# build failed.")

            dll_path = temp_path / "bin" / "Debug" / "net6.0" / "Runner.dll"
            run = self._run_process([dotnet, str(dll_path)], temp_path, stdin)
            events, other_stderr = self._parse_trace_stream(run.stderr)
            steps = self._build_steps(code, events, run.stdout, other_stderr if run.returncode != 0 else "")
            error = other_stderr if run.returncode != 0 else None
            return self._result(code=code, stdin=stdin, steps=steps, stdout=run.stdout, error=error)

    def _instrument_code(self, code: str) -> str:
        lines = code.splitlines()
        instrumented: list[str] = []
        class_fields = self._collect_static_fields(lines)
        pending_scope: MethodScope | None = None
        active_scope: MethodScope | None = None

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            current_indent = line[: len(line) - len(line.lstrip())]

            signature = self._parse_method_signature(stripped)
            if signature:
                pending_scope = signature

            if active_scope and self._should_instrument(stripped):
                instrumented.append(f'{current_indent}__Trace.Step({index}, "{active_scope.name}");')

            instrumented.append(line)

            if pending_scope and "{" in line:
                pending_scope.brace_depth = line.count("{") - line.count("}")
                active_scope = pending_scope
                pending_scope = None
            elif active_scope:
                active_scope.brace_depth += line.count("{") - line.count("}")

            if active_scope and self._should_snapshot(stripped):
                self._register_declared_variables(stripped, active_scope)
                snapshot_vars = self._snapshot_variables(class_fields, active_scope)
                if snapshot_vars:
                    tuple_args = ", ".join(f'("{name}", (object?){name})' for name in snapshot_vars)
                    instrumented.append(f"{current_indent}__Trace.State({index}, {tuple_args});")

            if active_scope and active_scope.brace_depth <= 0:
                active_scope = None

        helper = self._helper_code()
        insert_at = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("using "):
                insert_at = i + 1
                continue
            if not stripped:
                insert_at = i + 1
                continue
            break

        combined = instrumented[:insert_at] + helper + instrumented[insert_at:]
        if not any(line.strip() == "using System;" for line in lines):
            combined.insert(0, "using System;")

        return "\n".join(combined)

    def _helper_code(self) -> list[str]:
        return [
            "static class __Trace",
            "{",
            f'    public static void Step(int line, string method) => Console.Error.WriteLine("{TRACE_PREFIX}" + line + "|" + method);',
            "    public static void State(int line, params (string Name, object? Value)[] items)",
            "    {",
            "        var entries = new List<string>();",
            "        foreach (var item in items)",
            "        {",
            '            var typeName = item.Value?.GetType().Name ?? "null";',
            '            var repr = FormatValue(item.Value);',
            '            var nameJson = System.Text.Json.JsonSerializer.Serialize(item.Name);',
            '            var typeJson = System.Text.Json.JsonSerializer.Serialize(typeName);',
            '            var reprJson = System.Text.Json.JsonSerializer.Serialize(repr);',
            '            entries.Add($"{nameJson}:{{\\"type\\":{typeJson},\\"repr\\":{reprJson}}}");',
            "        }",
            '        var entriesJson = "{" + string.Join(",", entries) + "}";',
            f'        Console.Error.WriteLine("{STATE_PREFIX}" + line + "|" + entriesJson);',
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
            "                if (index >= 8) { items.Add(\"...\"); break; }",
            "                items.Add(FormatValue(element));",
            "                index += 1;",
            "            }",
            '            return "[" + string.Join(", ", items) + "]";',
            "        }",
            "        if (value is System.Collections.IEnumerable enumerable && value is not string)",
            "        {",
            "            var items = new List<string>();",
            "            var index = 0;",
            "            foreach (var element in enumerable)",
            "            {",
            "                if (index >= 8) { items.Add(\"...\"); break; }",
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
            stripped = line.strip()
            if "(" in stripped and ")" in stripped:
                continue
            match = FIELD_PATTERN.match(line)
            if match:
                fields.append(match.group("name"))
        return fields

    def _parse_method_signature(self, stripped: str) -> MethodScope | None:
        if not stripped or stripped.startswith("//"):
            return None
        if stripped.startswith(("if ", "if(", "for ", "for(", "foreach", "while", "switch", "catch", "using ")):
            return None
        match = METHOD_PATTERN.search(stripped)
        if not match:
            return None

        params_text = match.group("params").strip()
        params = [self._extract_param_name(part) for part in params_text.split(",") if part.strip()]
        params = [name for name in params if name]
        return MethodScope(name=match.group("name"), params=params, known_vars=list(params))

    def _extract_param_name(self, param_text: str) -> str | None:
        cleaned = param_text.strip()
        if not cleaned:
            return None
        pieces = cleaned.split()
        return pieces[-1].strip() if pieces else None

    def _register_declared_variables(self, stripped: str, scope: MethodScope) -> None:
        if stripped.startswith("for " ) or stripped.startswith("for("):
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

    def _should_instrument(self, stripped: str) -> bool:
        if not stripped:
            return False
        if stripped in {"{", "}"}:
            return False
        if stripped.startswith(("//", "else", "catch", "finally", "case ", "default:")):
            return False
        return True

    def _should_snapshot(self, stripped: str) -> bool:
        if not self._should_instrument(stripped):
            return False
        if stripped.endswith("{"):
            return False
        if stripped.startswith(("for ", "for(", "if ", "if(", "while ", "while(", "switch ", "switch(", "foreach")):
            return False
        return ";" in stripped

    def _parse_trace_stream(self, stderr: str) -> tuple[list[dict[str, Any]], str]:
        events: list[dict[str, Any]] = []
        other_lines: list[str] = []

        for raw_line in stderr.splitlines():
            if raw_line.startswith(TRACE_PREFIX):
                payload = raw_line[len(TRACE_PREFIX):]
                line_text, _, method_name = payload.partition("|")
                if line_text.isdigit():
                    events.append(
                        {
                            "line": int(line_text),
                            "method": method_name or "Main",
                            "state": {},
                        }
                    )
            elif raw_line.startswith(STATE_PREFIX):
                payload = raw_line[len(STATE_PREFIX):]
                line_text, _, state_json = payload.partition("|")
                if line_text.isdigit() and events:
                    try:
                        events[-1]["state"] = json.loads(state_json) if state_json else {}
                    except json.JSONDecodeError:
                        events[-1]["state"] = {}
            else:
                other_lines.append(raw_line)

        return events, "\n".join(other_lines).strip()

    def _build_steps(
        self,
        code: str,
        events: list[dict[str, Any]],
        stdout: str,
        error: str,
    ) -> list[dict[str, Any]]:
        code_lines = code.splitlines()
        steps: list[dict[str, Any]] = []

        for event in events:
            line_number = event["line"]
            method_name = event.get("method") or "Main"
            state = event.get("state") or {}
            line_source = code_lines[line_number - 1] if 1 <= line_number <= len(code_lines) else ""

            steps.append(
                {
                    "index": len(steps) + 1,
                    "event": "line",
                    "line": line_number,
                    "line_source": line_source,
                    "message": f"Executed C# line {line_number}.",
                    "stdout": stdout,
                    "stack": [
                        {
                            "name": method_name,
                            "label": f"{method_name}()",
                            "line": line_number,
                            "active": True,
                            "node_id": f"call-{method_name.lower()}",
                            "locals": state,
                        }
                    ],
                    "globals": state,
                    "call_tree": {
                        "id": "root",
                        "label": "module",
                        "status": "running",
                        "line": line_number,
                        "active": False,
                        "return_value": None,
                        "error": None,
                        "children": [
                            {
                                "id": f"call-{method_name.lower()}",
                                "label": f"{method_name}()",
                                "status": "running",
                                "line": line_number,
                                "active": True,
                                "return_value": None,
                                "error": None,
                                "children": [],
                            }
                        ],
                    },
                    "graph": None,
                    "structure": None,
                    "explanation": f"Executed `{line_source.strip()}` on C# line {line_number}.",
                }
            )

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
                "call_tree": {
                    "id": "root",
                    "label": "module",
                    "status": "returned" if not error else "exception",
                    "line": None,
                    "active": False,
                    "return_value": None,
                    "error": error or None,
                    "children": [],
                },
                "graph": None,
                "structure": None,
                "explanation": error or "Execution finished successfully.",
            }
        )
        return steps

    def _run_process(
        self,
        command: list[str],
        cwd: Path,
        stdin: str = "",
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
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
            return subprocess.CompletedProcess(
                command,
                124,
                stdout="",
                stderr=f"Execution exceeded {self.timeout_seconds:.1f} seconds.",
            )

    def _result(
        self,
        *,
        code: str,
        stdin: str,
        steps: list[dict[str, Any]],
        stdout: str,
        error: str | None,
    ) -> dict[str, Any]:
        return {
            "ok": error is None,
            "code": code,
            "stdin": stdin,
            "steps": steps,
            "stdout": stdout,
            "error": error,
            "analysis": {"structures": [], "intent_map": {}, "summary": ""},
        }
