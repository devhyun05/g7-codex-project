from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from visualizer.services.runtime_locator import find_node_runtime


TRACE_PREFIX = "__TRACE__|"


class JavaScriptLineTracer:
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        node = find_node_runtime()
        if node is None:
            return self._result(
                code=code,
                stdin=stdin,
                steps=[],
                stdout="",
                error="Required runtime was not found: node.",
            )

        instrumented = self._instrument_code(code)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.js"
            source_path.write_text(instrumented, encoding="utf-8")

            run = self._run_process([node, str(source_path)], temp_path, stdin)
            trace_lines, other_stderr = self._split_trace_lines(run.stderr)
            steps = self._build_steps(code, trace_lines, run.stdout, other_stderr if run.returncode != 0 else "")
            error = other_stderr if run.returncode != 0 else None
            return self._result(code=code, stdin=stdin, steps=steps, stdout=run.stdout, error=error)

    def _instrument_code(self, code: str) -> str:
        lines = code.splitlines()
        instrumented: list[str] = []
        brace_depth = 0

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            current_indent = line[: len(line) - len(line.lstrip())]

            if self._should_instrument(stripped, brace_depth):
                instrumented.append(f"{current_indent}__traceStep({index});")

            instrumented.append(line)

            brace_depth += line.count("{")
            brace_depth -= line.count("}")
            brace_depth = max(brace_depth, 0)

        helper = [
            "function __traceStep(line) {",
            f"  process.stderr.write('{TRACE_PREFIX}' + line + '\\n');",
            "}",
            "",
        ]

        return "\n".join(helper + instrumented)

    def _should_instrument(self, stripped: str, brace_depth: int) -> bool:
        if not stripped:
            return False
        if stripped in {"{", "}", ");"}:
            return False
        if stripped.startswith(("//", "else", "catch", "finally", "case ", "default:")):
            return False
        if stripped.endswith("{") and not any(
            stripped.startswith(prefix)
            for prefix in ("if", "for", "while", "switch", "function", "class", "else")
        ):
            return False
        return True

    def _split_trace_lines(self, stderr: str) -> tuple[list[int], str]:
        trace_lines: list[int] = []
        other_lines: list[str] = []
        for raw_line in stderr.splitlines():
            if raw_line.startswith(TRACE_PREFIX):
                line_text = raw_line[len(TRACE_PREFIX):].strip()
                if line_text.isdigit():
                    trace_lines.append(int(line_text))
            else:
                other_lines.append(raw_line)
        return trace_lines, "\n".join(other_lines).strip()

    def _build_steps(
        self,
        code: str,
        executed_lines: list[int],
        stdout: str,
        error: str,
    ) -> list[dict[str, Any]]:
        code_lines = code.splitlines()
        steps: list[dict[str, Any]] = []
        for line_number in executed_lines:
            line_source = code_lines[line_number - 1] if 1 <= line_number <= len(code_lines) else ""
            steps.append(
                {
                    "index": len(steps) + 1,
                    "event": "line",
                    "line": line_number,
                    "line_source": line_source,
                    "message": f"Executed JavaScript line {line_number}.",
                    "stdout": stdout,
                    "stack": [
                        {
                            "name": "main",
                            "label": "main()",
                            "line": line_number,
                            "active": True,
                            "node_id": "call-main",
                            "locals": {},
                        }
                    ],
                    "globals": {},
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
                                "id": "call-main",
                                "label": "main()",
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
                    "explanation": f"Executed `{line_source.strip()}` on JavaScript line {line_number}.",
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
                env={**os.environ},
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
