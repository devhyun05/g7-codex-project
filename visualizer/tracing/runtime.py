from __future__ import annotations

import builtins
import bisect
import collections
import contextlib
import functools
import heapq
import inspect
import io
import itertools
import math
import operator
import random
import re
import sys
import time
from dataclasses import dataclass
from types import FrameType, ModuleType, SimpleNamespace
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
    step_limit: int = 2000
    time_limit_seconds: float = 5.0


class ExecutionTracer:
    def __init__(self, config: TraceConfig | None = None):
        self.config = config or TraceConfig()
        self.allowed_modules = {
            "bisect": bisect,
            "collections": collections,
            "functools": functools,
            "heapq": heapq,
            "itertools": itertools,
            "math": math,
            "operator": operator,
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
            raw_error = self._format_syntax_error(exc)
            return {
                "ok": False,
                "code": code,
                "stdin": stdin,
                "steps": [],
                "stdout": "",
                "error": raw_error,
                "display_error": self._format_display_error(exc),
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
            self.display_error = self._format_display_error(exc)
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            self.display_error = self._format_display_error(exc)
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
            "display_error": self.display_error,
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
        self.display_error: str | None = None
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

    def _build_safe_sys_module(self) -> ModuleType:
        safe_sys = ModuleType("sys")
        safe_sys.stdin = SimpleNamespace(readline=self._safe_stdin_readline)
        safe_sys.stdout = self.stdout_buffer
        safe_sys.stderr = self.stdout_buffer
        safe_sys.setrecursionlimit = self._safe_setrecursionlimit
        safe_sys.getrecursionlimit = lambda: 10_000
        safe_sys.maxsize = sys.maxsize
        return safe_sys

    def _safe_input(self, prompt: str = "") -> str:
        if prompt:
            self.stdout_buffer.write(str(prompt))

        if self.stdin_index >= len(self.stdin_lines):
            raise EOFError("입력 데이터가 더 이상 없습니다.")

        line = self.stdin_lines[self.stdin_index]
        self.stdin_index += 1
        return line

    def _safe_stdin_readline(self, size: int = -1) -> str:
        if self.stdin_index >= len(self.stdin_lines):
            return ""

        line = self.stdin_lines[self.stdin_index]
        self.stdin_index += 1
        result = f"{line}\n"
        if size is not None and size >= 0:
            return result[:size]
        return result

    def _safe_setrecursionlimit(self, limit: int) -> None:
        # Visualized code runs in a controlled environment, so this is a no-op.
        _ = limit

    def _safe_import(
        self,
        name: str,
        globals_dict: dict[str, Any] | None = None,
        locals_dict: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if level != 0 or name not in self.allowed_modules:
            if name == "sys" and level == 0:
                return self._build_safe_sys_module()
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
            "locals": self._serialize_namespace(frame.f_locals),
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
            self.node_by_id[node_id]["locals"] = self._serialize_namespace(frame.f_locals)
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
        node["locals"] = self._serialize_namespace(frame.f_locals)

    def _register_exception(self, frame: FrameType, arg: Any) -> None:
        exc_type, exc_value, _ = arg
        node_id = self.frame_to_node.get(id(frame))
        if node_id:
            node = self.node_by_id[node_id]
            node["status"] = "exception"
            node["error"] = f"{exc_type.__name__}: {exc_value}"
            node["line"] = frame.f_lineno
            node["locals"] = self._serialize_namespace(frame.f_locals)

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
                "value": self._json_safe_value(value),
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
            "locals": node.get("locals", {}),
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

    def _format_display_error(self, exc: BaseException) -> str:
        if isinstance(exc, SyntaxError):
            return self._format_display_syntax_error(exc)

        if isinstance(exc, EOFError):
            return (
                "입력 데이터가 부족합니다. `input()` 호출 수만큼 입력 데이터 칸에 "
                "줄 단위로 값을 더 넣어 주세요."
            )

        if isinstance(exc, ImportError):
            return (
                "이 시각화기에서는 일부 모듈만 사용할 수 있습니다. 허용되지 않은 "
                "import를 제거하거나 지원되는 표준 모듈만 사용해 주세요."
            )

        if isinstance(exc, NameError):
            missing_name = self._extract_missing_name(str(exc))
            if missing_name:
                return (
                    f"`{missing_name}` 이름을 아직 정의하지 않았습니다. 변수나 함수 이름 "
                    "오타, 선언 순서를 확인해 주세요."
                )
            return (
                "정의되지 않은 이름을 사용했습니다. 변수나 함수 이름 오타, 선언 순서를 "
                "확인해 주세요."
            )

        if isinstance(exc, TypeError):
            return (
                "값의 종류가 연산이나 호출 방식과 맞지 않습니다. 함수 인자 개수와 "
                "자료형 조합을 확인해 주세요."
            )

        if isinstance(exc, ValueError):
            if "invalid literal for int()" in str(exc):
                return (
                    "숫자로 바꾸려는 값 형식이 올바르지 않습니다. 입력 데이터에 숫자가 "
                    "아닌 문자가 섞여 있지 않은지 확인해 주세요."
                )
            return (
                "값의 형식이 기대한 형태와 다릅니다. 형변환 대상이나 입력값 형식을 "
                "다시 확인해 주세요."
            )

        if isinstance(exc, IndexError):
            return (
                "리스트나 튜플 범위를 벗어난 위치에 접근했습니다. 인덱스 계산과 반복 "
                "범위를 확인해 주세요."
            )

        if isinstance(exc, KeyError):
            return (
                "딕셔너리에 없는 키에 접근했습니다. 키가 실제로 존재하는지 먼저 확인해 "
                "주세요."
            )

        if isinstance(exc, ZeroDivisionError):
            return (
                "0으로 나누려고 했습니다. 나누는 값이 0이 아닌지 먼저 확인해 주세요."
            )

        if isinstance(exc, TraceLimitExceeded):
            if "실행 시간" in str(exc):
                return (
                    "실행 시간이 너무 길어 중단했습니다. 무한 루프이거나 계산량이 큰 "
                    "코드일 수 있으니 범위를 줄여 다시 실행해 주세요."
                )
            return (
                "실행 단계가 너무 많아 중단했습니다. 반복문 종료 조건이나 재귀 종료 "
                "조건을 확인해 주세요."
            )

        return (
            f"실행 중 {type(exc).__name__}가 발생했습니다. 최근에 수정한 줄과 변수 값을 "
            "다시 확인해 주세요."
        )

    def _format_display_syntax_error(self, exc: SyntaxError) -> str:
        location = f"{exc.lineno}번째 줄" if exc.lineno else "문법 분석 단계"
        lowered = (exc.msg or "").lower()

        if "expected ':'" in lowered:
            hint = "if, for, while, def, class 문장 끝에 콜론(:)이 있는지 확인해 주세요."
        elif "indent" in lowered:
            hint = "들여쓰기 깊이를 맞추고 탭과 공백이 섞이지 않았는지 확인해 주세요."
        elif "eof" in lowered or "was never closed" in lowered or "unclosed" in lowered:
            hint = "괄호, 대괄호, 문자열 따옴표가 모두 닫혔는지 확인해 주세요."
        else:
            hint = "괄호, 콜론, 들여쓰기, 문자열 닫힘을 차례로 확인해 주세요."

        return f"{location}에서 문법 오류가 있습니다. {hint}"

    def _extract_missing_name(self, message: str) -> str | None:
        match = re.search(r"name '(.+?)' is not defined", message)
        return match.group(1) if match else None

    def _short_repr(self, value: Any) -> str:
        try:
            text = repr(value)
        except Exception:  # noqa: BLE001
            text = f"<{type(value).__name__}>"
        if len(text) > MAX_REPR_LENGTH:
            return text[: MAX_REPR_LENGTH - 3] + "..."
        return text

    def _json_safe_value(self, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return self._short_repr(value)
        return value
