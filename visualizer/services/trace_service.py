from __future__ import annotations

from typing import Any

from visualizer.tracing.native_runtime import NativeExecutionTracer
from visualizer.tracing.runtime import ExecutionTracer


class TraceService:
    def __init__(
        self,
        tracer: ExecutionTracer | None = None,
        native_tracer: NativeExecutionTracer | None = None,
    ):
        self.tracer = tracer or ExecutionTracer()
        self.native_tracer = native_tracer or NativeExecutionTracer()

    def visualize(self, code: str, stdin: str = "", language: str = "python") -> dict[str, Any]:
        normalized_language = (language or "python").strip().lower()
        if normalized_language == "python":
            result = self.tracer.trace(code, stdin=stdin)
            result["language"] = "python"
            return result
        return self.native_tracer.trace(code, stdin=stdin, language=normalized_language)


trace_service = TraceService()
