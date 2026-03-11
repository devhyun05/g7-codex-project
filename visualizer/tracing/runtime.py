from __future__ import annotations

import builtins
import collections
import contextlib
import heapq
import inspect
import io
import itertools
import math
import random
import sys
import time
from dataclasses import dataclass
from types import FrameType
from typing import Any

from .code_analysis import analyze_code_structures
from .structure_detection import StructureDetector

USER_FILENAME = "<visualizer>"
MAX_ITEMS = 256
MAX_DEPTH = 3
MAX_REPR_LENGTH = 96


class TraceLimitExceeded(RuntimeError):
    pass


@dataclass
class TraceConfig:
    step_limit: int = 999
    time_limit_seconds: float = 3.0


class ExecutionTracer:
    def __init__(self, config: TraceConfig | None = None):
        self.config = config or TraceConfig()
        self.allowed_modules = {
            "collections": collections,
            "heapq": heapq,
            "itertools": itertools,
            "math": math,
            "random": random,
        }
        self._reset_state("")

    def trace(self, code: str, stdin: str = "") -> dict[str, Any]:
        self._reset_state(code, stdin)
        self.code_analysis = analyze_code_structures(code)
        self.detector = StructureDetector(self._short_repr, self.code_analysis)

        try:
            compiled = compile(code, USER_FILENAME, "exec")
        except SyntaxError as exc:
            return {
                "ok": False,
                "code": code,
                "stdin": stdin,
                "steps": [],
                "stdout": "",
                "error": self._format_syntax_error(exc),
                "analysis": self.code_analysis,
            }

        safe_builtins = self._build_safe_builtins()
        self.globals_env = {
            "__builtins__": safe_builtins,
            "__name__": "__main__",
        }

        previous_trace = sys.gettrace()
        try:
            with contextlib.redirect_stdout(self.stdout_buffer):
                sys.settrace(self._trace)
                exec(compiled, self.globals_env, self.globals_env)
        except TraceLimitExceeded as exc:
            self.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            sys.settrace(previous_trace)

        self.stdout = self.stdout_buffer.getvalue()
        self._append_terminal_step()

        return {
            "ok": self.error is None,
            "code": code,
            "stdin": stdin,
            "steps": self.steps,
            "stdout": self.stdout,
            "error": self.error,
            "analysis": self.code_analysis,
        }

    def _reset_state(self, code: str, stdin: str = "") -> None:
        self.code = code
        self.code_lines = code.splitlines()
        self.stdin = stdin
        self.stdin_lines = stdin.splitlines()
        self.stdin_index = 0
        self.steps: list[dict[str, Any]] = []
        self.stdout_buffer = io.StringIO()
        self.stdout = ""
        self.error: str | None = None
        self.step_count = 0
        self.started_at = time.perf_counter()
        self.globals_env: dict[str, Any] = {}
        self.code_analysis: dict[str, Any] = {
            "structures": [],
            "intent_map": {},
            "summary": "",
            "intents": {"sorting": False, "sorting_order": "unknown"},
        }
        self.detector = StructureDetector(self._short_repr, self.code_analysis)
        self.call_root = {
            "id": "root",
            "label": "module",
            "status": "running",
            "line": None,
            "children": [],
        }
        self.node_by_id = {"root": self.call_root}
        self.frame_to_node: dict[int, str] = {}
        self.call_index = 0

    def _build_safe_builtins(self) -> dict[str, Any]:
        allowed_builtin_names = [
            "abs",
            "all",
            "any",
            "bin",
            "bool",
            "bytearray",
            "bytes",
            "callable",
            "chr",
            "classmethod",
            "complex",
            "dict",
            "divmod",
            "enumerate",
            "Exception",
            "filter",
            "float",
            "format",
            "frozenset",
            "getattr",
            "hasattr",
            "hash",
            "hex",
            "int",
            "isinstance",
            "issubclass",
            "iter",
            "len",
            "list",
            "map",
            "max",
            "min",
            "next",
            "object",
            "oct",
            "ord",
            "pow",
            "print",
            "property",
            "range",
            "repr",
            "reversed",
            "round",
            "set",
            "setattr",
            "slice",
            "sorted",
            "staticmethod",
            "str",
            "sum",
            "super",
            "tuple",
            "type",
            "ValueError",
            "TypeError",
            "IndexError",
            "KeyError",
            "StopIteration",
            "EOFError",
            "zip",
            "__build_class__",
        ]
        safe_builtins = {name: getattr(builtins, name) for name in allowed_builtin_names}
        safe_builtins["__import__"] = self._safe_import
        safe_builtins["input"] = self._safe_input
        return safe_builtins

    def _safe_input(self, prompt: str = "") -> str:
        if prompt:
            self.stdout_buffer.write(str(prompt))

        if self.stdin_index >= len(self.stdin_lines):
            raise EOFError("입력 데이터가 더 이상 없습니다.")

        line = self.stdin_lines[self.stdin_index]
        self.stdin_index += 1
        return line

    def _safe_import(
        self,
        name: str,
        globals_dict: dict[str, Any] | None = None,
        locals_dict: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if level != 0 or name not in self.allowed_modules:
            raise ImportError(f"'{name}' import is blocked in this visualizer.")
        return self.allowed_modules[name]

    def _trace(self, frame: FrameType, event: str, arg: Any):
        if not self._is_user_frame(frame):
            return self._trace

        self._check_limits()

        if event == "call":
            self._register_call(frame)
            return self._trace

        if event == "line":
            self.step_count += 1
            self._update_current_node_line(frame)
            self.steps.append(self._build_snapshot(frame, event, arg))
            return self._trace

        if event == "return":
            self._register_return(frame, arg)
            self.steps.append(self._build_snapshot(frame, event, arg))
            self.frame_to_node.pop(id(frame), None)
            return self._trace

        if event == "exception":
            self._register_exception(frame, arg)
            self.steps.append(self._build_snapshot(frame, event, arg))
            return self._trace

        return self._trace

    def _check_limits(self) -> None:
        if self.step_count >= self.config.step_limit:
            raise TraceLimitExceeded(
                f"실행 step 수가 {self.config.step_limit}개를 넘어 중단했습니다. "
                "무한 루프이거나 너무 긴 코드일 수 있습니다."
            )

        if (time.perf_counter() - self.started_at) > self.config.time_limit_seconds:
            raise TraceLimitExceeded(
                f"실행 시간이 {self.config.time_limit_seconds:.1f}초를 넘어 중단했습니다."
            )

    def _is_user_frame(self, frame: FrameType) -> bool:
        return frame.f_code.co_filename == USER_FILENAME

    def _register_call(self, frame: FrameType) -> None:
        if frame.f_code.co_name == "<module>":
            return

        self.call_index += 1
        node_id = f"call-{self.call_index}"
        parent_node_id = self._find_parent_node_id(frame)
        node = {
            "id": node_id,
            "label": self._format_call_label(frame),
            "status": "running",
            "line": frame.f_lineno,
            "children": [],
        }
        self.node_by_id[node_id] = node
        self.node_by_id[parent_node_id]["children"].append(node)
        self.frame_to_node[id(frame)] = node_id

    def _find_parent_node_id(self, frame: FrameType) -> str:
        cursor = frame.f_back
        while cursor:
            node_id = self.frame_to_node.get(id(cursor))
            if node_id:
                return node_id
            cursor = cursor.f_back
        return "root"

    def _update_current_node_line(self, frame: FrameType) -> None:
        node_id = self.frame_to_node.get(id(frame))
        if node_id:
            self.node_by_id[node_id]["line"] = frame.f_lineno
            self.node_by_id[node_id]["label"] = self._format_call_label(frame)
        else:
            self.call_root["line"] = frame.f_lineno

    def _register_return(self, frame: FrameType, value: Any) -> None:
        node_id = self.frame_to_node.get(id(frame))
        if not node_id:
            self.call_root["status"] = "returned"
            return

        node = self.node_by_id[node_id]
        node["status"] = "returned"
        node["return_value"] = self._short_repr(value)
        node["line"] = frame.f_lineno
        node["label"] = self._format_call_label(frame)

    def _register_exception(self, frame: FrameType, arg: Any) -> None:
        exc_type, exc_value, _ = arg
        node_id = self.frame_to_node.get(id(frame))
        if node_id:
            node = self.node_by_id[node_id]
            node["status"] = "exception"
            node["error"] = f"{exc_type.__name__}: {exc_value}"
            node["line"] = frame.f_lineno

    def _build_snapshot(self, frame: FrameType, event: str, arg: Any) -> dict[str, Any]:
        stack_frames = self._collect_user_stack(frame)
        active_ids = [
            self.frame_to_node[id(stack_frame)]
            for stack_frame in stack_frames
            if id(stack_frame) in self.frame_to_node
        ]
        line_number = frame.f_lineno if frame else None
        graph_state = self.detector.detect_graph_state(stack_frames, self.globals_env)
        structure_state = self.detector.detect_structure_state(stack_frames, self.globals_env)

        snapshot = {
            "index": len(self.steps) + 1,
            "event": event,
            "line": line_number,
            "line_source": self._line_source(line_number),
            "message": self._build_message(frame, event, arg),
            "stdout": self.stdout_buffer.getvalue(),
            "stack": [self._serialize_frame(stack_frame) for stack_frame in stack_frames],
            "globals": self._serialize_namespace(self.globals_env),
            "call_tree": self._snapshot_tree(self.call_root, set(active_ids)),
            "graph": graph_state,
            "structure": structure_state,
        }
        snapshot["explanation"] = self._build_step_explanation(snapshot)
        return snapshot

    def _append_terminal_step(self) -> None:
        graph_state = self.detector.detect_graph_state([], self.globals_env)
        structure_state = self.detector.detect_structure_state([], self.globals_env)
        snapshot = {
            "index": len(self.steps) + 1,
            "event": "error" if self.error else "end",
            "line": None,
            "line_source": "",
            "message": self.error or "프로그램 실행이 끝났습니다.",
            "stdout": self.stdout,
            "stack": [],
            "globals": self._serialize_namespace(self.globals_env),
            "call_tree": self._snapshot_tree(self.call_root, set()),
            "graph": graph_state,
            "structure": structure_state,
        }
        snapshot["explanation"] = self._build_step_explanation(snapshot)
        self.steps.append(snapshot)

    def _collect_user_stack(self, frame: FrameType) -> list[FrameType]:
        frames: list[FrameType] = []
        cursor = frame
        while cursor:
            if self._is_user_frame(cursor):
                frames.append(cursor)
            cursor = cursor.f_back
        frames.reverse()
        return frames

    def _serialize_frame(self, frame: FrameType) -> dict[str, Any]:
        node_id = self.frame_to_node.get(id(frame))
        return {
            "name": frame.f_code.co_name,
            "label": self._format_call_label(frame),
            "line": frame.f_lineno,
            "active": True,
            "node_id": node_id,
            "locals": self._serialize_namespace(frame.f_locals),
        }

    def _serialize_namespace(self, namespace: dict[str, Any]) -> dict[str, Any]:
        visible: dict[str, Any] = {}
        for name, value in namespace.items():
            if name.startswith("__"):
                continue
            visible[name] = self._serialize_value(value, depth=0, seen=set())
        return visible

    def _serialize_value(self, value: Any, depth: int, seen: set[int]) -> dict[str, Any]:
        value_id = id(value)
        if value_id in seen:
            return {"type": "ref", "repr": "<recursive reference>"}

        if value is None or isinstance(value, (bool, int, float, str)):
            return {
                "type": type(value).__name__,
                "repr": self._short_repr(value),
                "value": value,
            }

        if inspect.isfunction(value):
            return {"type": "function", "repr": f"<function {value.__name__}>"}

        if inspect.ismodule(value):
            return {"type": "module", "repr": f"<module {value.__name__}>"}

        if depth >= MAX_DEPTH:
            return {"type": type(value).__name__, "repr": self._short_repr(value)}

        next_seen = seen | {value_id}

        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)
            return {
                "type": type(value).__name__,
                "repr": self._short_repr(value),
                "items": [
                    self._serialize_value(item, depth + 1, next_seen)
                    for item in items[:MAX_ITEMS]
                ],
                "truncated": len(items) > MAX_ITEMS,
            }

        if isinstance(value, dict):
            items = list(value.items())
            return {
                "type": "dict",
                "repr": self._short_repr(value),
                "items": [
                    {
                        "key": self._serialize_value(key, depth + 1, next_seen),
                        "value": self._serialize_value(item, depth + 1, next_seen),
                    }
                    for key, item in items[:MAX_ITEMS]
                ],
                "truncated": len(items) > MAX_ITEMS,
            }

        try:
            attrs = vars(value)
        except TypeError:
            return {"type": type(value).__name__, "repr": self._short_repr(value)}

        return {
            "type": type(value).__name__,
            "repr": self._short_repr(value),
            "attributes": [
                {
                    "name": name,
                    "value": self._serialize_value(attr_value, depth + 1, next_seen),
                }
                for name, attr_value in list(attrs.items())[:MAX_ITEMS]
            ],
            "truncated": len(attrs) > MAX_ITEMS,
        }

    def _build_message(self, frame: FrameType, event: str, arg: Any) -> str:
        function_name = frame.f_code.co_name
        line_number = frame.f_lineno

        if event == "line":
            if function_name == "<module>":
                return f"{line_number}번째 줄을 실행합니다."
            return f"{function_name} 프레임에서 {line_number}번째 줄을 실행합니다."

        if event == "return":
            return f"{function_name} 호출이 {self._short_repr(arg)} 값을 반환했습니다."

        if event == "exception":
            exc_type, exc_value, _ = arg
            return f"{function_name} 프레임에서 {exc_type.__name__}: {exc_value}"

        return "실행 상태가 갱신되었습니다."

    def _snapshot_tree(self, node: dict[str, Any], active_ids: set[str]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "label": node["label"],
            "status": node.get("status", "running"),
            "line": node.get("line"),
            "active": node["id"] in active_ids,
            "return_value": node.get("return_value"),
            "error": node.get("error"),
            "children": [
                self._snapshot_tree(child, active_ids)
                for child in node.get("children", [])
            ],
        }

    def _build_step_explanation(self, snapshot: dict[str, Any]) -> str:
        pieces = [snapshot["message"]]
        line_source = (snapshot.get("line_source") or "").strip()
        if line_source:
            pieces.append(f"현재 코드는 `{line_source}` 입니다.")

        visual_target = self._describe_visual_target(snapshot)
        if visual_target:
            pieces.append(visual_target)

        analysis_summary = self.code_analysis.get("summary") or ""
        if analysis_summary:
            pieces.append(f"코드에서 자동 판단한 자료구조는 {analysis_summary} 입니다.")

        return " ".join(pieces)

    def _describe_visual_target(self, snapshot: dict[str, Any]) -> str:
        intents = self.code_analysis.get("intents") or {}
        if intents.get("sorting") and snapshot.get("call_tree", {}).get("children"):
            return "정렬 알고리즘으로 판단되어 호출 트리를 우선 표시합니다."

        if snapshot.get("graph"):
            graph_name = snapshot["graph"].get("name") or "graph"
            return f"`{graph_name}` 인접 구조를 그래프로 판단해 흐름을 그립니다."

        structure = snapshot.get("structure")
        if not structure:
            if snapshot.get("call_tree", {}).get("children"):
                return "재귀 호출이 있어 호출 트리를 기준으로 흐름을 보여줍니다."
            return "특정 자료구조가 감지되지 않아 실행 상태 요약을 유지합니다."

        labels = {
            "stack": "스택으로 판단해 top 중심으로 보여줍니다.",
            "queue": "큐로 판단해 front / back 흐름을 보여줍니다.",
            "tree": "트리로 판단해 현재 노드와 전체 구조를 함께 보여줍니다.",
        }
        return labels.get(structure.get("kind"), "")

    def _format_call_label(self, frame: FrameType) -> str:
        if frame.f_code.co_name == "<module>":
            return "module"

        preview_parts: list[str] = []
        for name, value in list(frame.f_locals.items())[:3]:
            if name.startswith("__"):
                continue
            preview_parts.append(f"{name}={self._short_repr(value)}")
        joined = ", ".join(preview_parts)
        return f"{frame.f_code.co_name}({joined})" if joined else f"{frame.f_code.co_name}()"

    def _line_source(self, line_number: int | None) -> str:
        if not line_number:
            return ""
        if 1 <= line_number <= len(self.code_lines):
            return self.code_lines[line_number - 1]
        return ""

    def _format_syntax_error(self, exc: SyntaxError) -> str:
        location = f"{exc.lineno}번째 줄" if exc.lineno else "문법 분석 단계"
        return f"SyntaxError ({location}): {exc.msg}"

    def _short_repr(self, value: Any) -> str:
        try:
            text = repr(value)
        except Exception:  # noqa: BLE001
            text = f"<{type(value).__name__}>"
        if len(text) > MAX_REPR_LENGTH:
            return text[: MAX_REPR_LENGTH - 3] + "..."
        return text
