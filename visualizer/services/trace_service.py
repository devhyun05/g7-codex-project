from __future__ import annotations

from typing import Any

from visualizer.services.execution_service import CodeExecutionService
from visualizer.services.language_service import LanguageDetector
from visualizer.services.tracing_registry import TracingRegistry
from visualizer.tracing.runtime import ExecutionTracer


class TraceService:
    def __init__(
        self,
        tracer: ExecutionTracer | None = None,
        language_detector: LanguageDetector | None = None,
        executor: CodeExecutionService | None = None,
    ):
        self.tracer = tracer or ExecutionTracer()
        self.language_detector = language_detector or LanguageDetector()
        self.executor = executor or CodeExecutionService()
        self.tracing_registry = TracingRegistry(self.tracer)

    def visualize(
        self,
        code: str,
        stdin: str = "",
        requested_language: str = "auto",
    ) -> dict[str, Any]:
        language = self.language_detector.detect(code, requested_language)
        trace_capabilities = self.tracing_registry.describe(language["key"])

        if trace_capabilities and trace_capabilities.get("line_tracing"):
            result = self.tracing_registry.get(language["key"]).trace(code, stdin=stdin)
            result["language"] = language
            result["supported_languages"] = self.language_detector.options()
            result["trace_capabilities"] = trace_capabilities
            result["run_mode"] = "trace"
            return result

        result = self.executor.execute(code, stdin, language["key"])
        result["language"] = language
        result["supported_languages"] = self.language_detector.options()
        result["trace_capabilities"] = trace_capabilities
        return result


trace_service = TraceService()
