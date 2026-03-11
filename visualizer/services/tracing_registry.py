from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from visualizer.tracing.javascript_tracer import JavaScriptLineTracer
from visualizer.tracing.csharp_tracer import CSharpLineTracer
from visualizer.tracing.runtime import ExecutionTracer


@dataclass(frozen=True)
class TraceCapabilities:
    language_key: str
    line_tracing: bool
    variable_snapshots: bool
    call_tree: bool
    structure_detection: bool
    difficulty: str
    approach: str
    status: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


class BaseLanguageTracer:
    capabilities: TraceCapabilities

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        raise NotImplementedError


class PythonLanguageTracer(BaseLanguageTracer):
    capabilities = TraceCapabilities(
        language_key="python",
        line_tracing=True,
        variable_snapshots=True,
        call_tree=True,
        structure_detection=True,
        difficulty="implemented",
        approach="Uses Python's runtime tracing hooks and AST-based structure analysis.",
        status="ready",
    )

    def __init__(self, tracer: ExecutionTracer | None = None):
        self.tracer = tracer or ExecutionTracer()

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        return self.tracer.trace(code, stdin=stdin)


class PlaceholderLanguageTracer(BaseLanguageTracer):
    def __init__(self, capabilities: TraceCapabilities):
        self.capabilities = capabilities

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        raise NotImplementedError(f"{self.capabilities.language_key} tracing is not implemented yet.")


class TracingRegistry:
    def __init__(self, python_tracer: ExecutionTracer | None = None):
        self._tracers: dict[str, BaseLanguageTracer] = {
            "python": PythonLanguageTracer(python_tracer),
            "cpp": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="cpp",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="hard",
                    approach="Needs compiler debug symbols or source-to-source instrumentation.",
                    status="planned",
                )
            ),
            "c": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="c",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="hard",
                    approach="Needs compiler debug symbols or source-to-source instrumentation.",
                    status="planned",
                )
            ),
            "rust": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="rust",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="hard",
                    approach="Needs rustc-level instrumentation or debugger integration with ownership-aware variable capture.",
                    status="planned",
                )
            ),
            "go": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="go",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="hard",
                    approach="Needs delve-style debugger integration or compiler-assisted instrumentation.",
                    status="planned",
                )
            ),
            "java": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="java",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="medium",
                    approach="Can be built with JVM debug interfaces and bytecode/source instrumentation.",
                    status="planned",
                )
            ),
            "kotlin": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="kotlin",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="medium-hard",
                    approach="Likely piggybacks JVM debugging, but source mapping to Kotlin syntax is trickier than Java.",
                    status="planned",
                )
            ),
            "javascript": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="javascript",
                    line_tracing=True,
                    variable_snapshots=False,
                    call_tree=True,
                    structure_detection=False,
                    difficulty="experimental",
                    approach="Uses source instrumentation before node execution. Line tracing works first; variable snapshots come later.",
                    status="experimental",
                )
            ),
            "typescript": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="typescript",
                    line_tracing=False,
                    variable_snapshots=False,
                    call_tree=False,
                    structure_detection=False,
                    difficulty="medium-hard",
                    approach="Needs TypeScript-to-JavaScript source maps plus Node inspector or instrumentation.",
                    status="planned",
                )
            ),
            "csharp": PlaceholderLanguageTracer(
                TraceCapabilities(
                    language_key="csharp",
                    line_tracing=True,
                    variable_snapshots=False,
                    call_tree=True,
                    structure_detection=False,
                    difficulty="experimental",
                    approach="Uses source instrumentation before dotnet run. Line tracing works first; variable snapshots come later.",
                    status="experimental",
                )
            ),
        }
        self._tracers["csharp"] = CSharpInstrumentedTracer()
        self._tracers["javascript"] = JavaScriptInstrumentedTracer()

    def get(self, language_key: str) -> BaseLanguageTracer | None:
        return self._tracers.get(language_key)

    def describe(self, language_key: str) -> dict[str, Any] | None:
        tracer = self.get(language_key)
        return tracer.capabilities.as_payload() if tracer else None


class CSharpInstrumentedTracer(BaseLanguageTracer):
    capabilities = TraceCapabilities(
        language_key="csharp",
        line_tracing=True,
        variable_snapshots=True,
        call_tree=True,
        structure_detection=False,
        difficulty="experimental",
        approach="Uses source instrumentation before dotnet execution. Line tracing, variable snapshots, and recursive call trees are available.",
        status="experimental",
    )

    def __init__(self):
        self.tracer = CSharpLineTracer()

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        return self.tracer.trace(code, stdin=stdin)


class JavaScriptInstrumentedTracer(BaseLanguageTracer):
    capabilities = TraceCapabilities(
        language_key="javascript",
        line_tracing=True,
        variable_snapshots=False,
        call_tree=True,
        structure_detection=False,
        difficulty="experimental",
        approach="Uses source instrumentation before node execution. Line tracing works first; variable snapshots come later.",
        status="experimental",
    )

    def __init__(self):
        self.tracer = JavaScriptLineTracer()

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        return self.tracer.trace(code, stdin=stdin)
