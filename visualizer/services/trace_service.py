from __future__ import annotations

from typing import Any

from visualizer.tracing.runtime import ExecutionTracer


class TraceService:
    def __init__(self, tracer: ExecutionTracer | None = None):
        self.tracer = tracer or ExecutionTracer()

    def visualize(self, code: str, stdin: str = "") -> dict[str, Any]:
        return self.tracer.trace(code, stdin=stdin)


trace_service = TraceService()
