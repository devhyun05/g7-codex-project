from __future__ import annotations

import ast
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
        normalized_code = self._normalize_source(code)
        self._reset_state(normalized_code, stdin)
        self.code_analysis = analyze_code_structures(normalized_code)
        self.detector = StructureDetector(self._short_repr, self.code_analysis)
        self.static_line_descriptions = self._build_static_line_descriptions(normalized_code)

        try:
            compiled = compile(normalized_code, USER_FILENAME, "exec")
        except SyntaxError as exc:
            raw_error = self._format_syntax_error(exc)
            return {
                "ok": False,
                "code": normalized_code,
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
            "code": normalized_code,
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
        self.static_line_descriptions: dict[int, str] = {}

    def _normalize_source(self, code: str) -> str:
        translation = str.maketrans({
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
        })
        return code.translate(translation)

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
        line_source = self._line_source(line_number)
        line_detail = self._build_line_detail(frame, line_source, event)

        snapshot = {
            "index": len(self.steps) + 1,
            "event": event,
            "line": line_number,
            "line_source": line_source,
            "line_detail": line_detail,
            "message": self._build_message(frame, event, arg),
            "stdout": self.stdout_buffer.getvalue(),
            "stack": [self._serialize_frame(stack_frame) for stack_frame in stack_frames],
            "globals": self._serialize_namespace(self.globals_env),
            "call_tree": self._snapshot_tree(self.call_root, set(active_ids)),
            "graph": graph_state,
            "structure": structure_state,
        }
        snapshot["explanation"] = self._build_step_explanation(snapshot, frame)
        snapshot["explanation_json"] = self._build_explanation_json(snapshot)
        return snapshot

    def _append_terminal_step(self) -> None:
        graph_state = self.detector.detect_graph_state([], self.globals_env)
        structure_state = self.detector.detect_structure_state([], self.globals_env)
        snapshot = {
            "index": len(self.steps) + 1,
            "event": "error" if self.error else "end",
            "line": None,
            "line_source": "",
            "line_detail": "",
            "message": self.error or "프로그램 실행이 끝났습니다.",
            "stdout": self.stdout,
            "stack": [],
            "globals": self._serialize_namespace(self.globals_env),
            "call_tree": self._snapshot_tree(self.call_root, set()),
            "graph": graph_state,
            "structure": structure_state,
        }
        snapshot["explanation"] = self._build_step_explanation(snapshot, None)
        snapshot["explanation_json"] = self._build_explanation_json(snapshot)
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

    def _build_explanation_json(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        current_line = snapshot.get("line")
        current_line_detail = snapshot.get("line_detail") or ""
        line_explanations: list[dict[str, Any]] = []

        for line_number, code in enumerate(self.code_lines, start=1):
            if not code.strip():
                continue

            description = self.static_line_descriptions.get(
                line_number,
                "이 줄은 위아래 줄과 함께 하나의 동작을 완성하는 코드입니다.",
            )
            if current_line == line_number and current_line_detail:
                description = current_line_detail

            line_explanations.append(
                {
                    "line": line_number,
                    "code": code,
                    "description": description,
                }
            )

        return {
            "summary": self._build_explanation_summary(snapshot),
            "line_explanations": line_explanations,
            "improvements": self._build_improvements(),
        }

    def _build_explanation_summary(self, snapshot: dict[str, Any]) -> str:
        if snapshot.get("event") == "error":
            return snapshot.get("message") or "실행 중 오류가 발생했습니다."

        structures = self.code_analysis.get("summary") or ""
        if structures:
            return f"이 코드는 {structures} 흐름을 포함하며, 현재 step을 기준으로 각 줄의 역할을 설명합니다."
        return "이 코드는 위에서 아래로 실행되며, 현재 step 기준으로 각 줄의 역할을 설명합니다."

    def _build_improvements(self) -> list[str]:
        improvements: list[str] = []
        code_text = "\n".join(self.code_lines)

        if "input(" in code_text and not self.stdin:
            improvements.append("input()을 사용하는 코드라면 입력 데이터가 없을 때 EOFError가 발생할 수 있습니다.")

        if self._has_nested_loop():
            improvements.append("중첩 반복문이 보여서 입력 크기가 커지면 실행 시간이 길어질 수 있습니다.")

        if "global " in code_text:
            improvements.append("global 변수에 의존하면 함수 재사용과 테스트가 어려워질 수 있습니다.")

        return improvements

    def _has_nested_loop(self) -> bool:
        try:
            tree = ast.parse(self.code)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue
            if any(isinstance(child, (ast.For, ast.While)) for child in ast.iter_child_nodes(node)):
                return True
        return False

    def _build_step_explanation(
        self,
        snapshot: dict[str, Any],
        frame: FrameType | None,
    ) -> str:
        pieces = [snapshot["message"]]
        line_source = (snapshot.get("line_source") or "").strip()
        line_detail = snapshot.get("line_detail") or ""
        if line_source:
            pieces.append(f"현재 코드는 `{line_source}` 입니다.")
            if line_detail:
                pieces.append(line_detail)

        visual_target = self._describe_visual_target(snapshot)
        if visual_target and not (
            line_detail and visual_target == self._generic_summary_text()
        ):
            pieces.append(visual_target)

        analysis_summary = self.code_analysis.get("summary") or ""
        if analysis_summary:
            pieces.append(f"코드에서 자동 판단한 자료구조는 {analysis_summary} 입니다.")

        return " ".join(pieces)

    def _build_line_detail(
        self,
        frame: FrameType | None,
        line_source: str,
        event: str | None,
    ) -> str:
        if frame is None or event != "line":
            return ""

        stripped = line_source.strip()
        if not stripped:
            return ""

        node = self._parse_line_node(stripped)
        if node is None:
            return ""

        if isinstance(node, ast.If):
            return self._describe_if_detail(node, frame)
        if isinstance(node, ast.While):
            return self._describe_while_detail(node, frame)
        if isinstance(node, ast.For):
            return self._describe_for_detail(node, frame)
        if isinstance(node, ast.Assign):
            return self._describe_assign_detail(node, frame)
        if isinstance(node, ast.AugAssign):
            return self._describe_augassign_detail(node, frame)
        if isinstance(node, ast.Return):
            return self._describe_return_detail(node, frame)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return self._describe_call_detail(node.value, frame)
        return ""

    def _build_static_line_descriptions(self, code: str) -> dict[int, str]:
        descriptions: dict[int, str] = {}

        for line_number, line in enumerate(code.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                descriptions[line_number] = "주석으로, 아래 코드가 왜 필요한지 설명하거나 메모를 남깁니다."
                continue

            node = self._parse_line_node(stripped)
            if node is None:
                descriptions[line_number] = "이 줄은 위아래 줄과 함께 하나의 식이나 블록을 완성하는 코드입니다."
                continue

            descriptions[line_number] = self._describe_static_node(node)

        return descriptions

    def _describe_static_node(self, node: ast.stmt) -> str:
        if isinstance(node, ast.FunctionDef):
            return f"`{node.name}` 함수를 정의합니다. 나중에 필요할 때 같은 로직을 다시 호출하려고 묶어 둔 것입니다."
        if isinstance(node, ast.ClassDef):
            return f"`{node.name}` 클래스를 정의합니다. 관련된 데이터와 동작을 하나의 객체 형태로 관리하려는 구조입니다."
        if isinstance(node, ast.If):
            return f"`if` 조건문입니다. 조건이 참일 때만 아래 블록을 실행하려고 사용합니다."
        if isinstance(node, ast.While):
            return f"`while` 반복문입니다. 조건이 참인 동안 같은 작업을 계속 반복합니다."
        if isinstance(node, ast.For):
            target = ast.unparse(node.target)
            iterable = ast.unparse(node.iter)
            return f"`for` 반복문입니다. `{target}` 값을 바꿔 가며 `{iterable}` 를 처음부터 끝까지 순회합니다."
        if isinstance(node, ast.Assign):
            targets = ", ".join(ast.unparse(target) for target in node.targets)
            return f"`{targets}` 변수에 계산 결과를 저장합니다. 이후 줄에서 다시 사용하려고 값을 보관하는 단계입니다."
        if isinstance(node, ast.AugAssign):
            target = ast.unparse(node.target)
            return f"`{target}` 값을 바로 갱신합니다. 기존 값을 읽고 연산한 뒤 같은 변수에 다시 저장합니다."
        if isinstance(node, ast.Return):
            return "함수 실행을 여기서 끝내고 결과값을 호출한 쪽으로 돌려줍니다."
        if isinstance(node, ast.Import):
            return "다른 모듈의 기능을 현재 코드에서 쓰기 위해 가져옵니다."
        if isinstance(node, ast.ImportFrom):
            return "특정 모듈 안의 필요한 기능만 골라서 가져옵니다."
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return f"`{ast.unparse(node.value.func)}` 함수를 호출합니다. 이 줄에서 실제 동작이 일어납니다."
        return "이 줄은 현재 로직을 진행하기 위해 필요한 일반 실행 코드입니다."

    def _describe_if_detail(self, node: ast.If, frame: FrameType) -> str:
        return self._describe_condition_detail(node.test, frame, "if")

    def _describe_while_detail(self, node: ast.While, frame: FrameType) -> str:
        return self._describe_condition_detail(node.test, frame, "while")

    def _describe_condition_detail(
        self,
        test: ast.AST,
        frame: FrameType,
        keyword: str,
    ) -> str:
        expression = ast.unparse(test)
        value = self._safe_eval_node(test, frame)
        if value is None:
            return f"`{keyword}` 조건 `{expression}` 을 평가합니다."

        detail = self._describe_test_operands(test, frame)
        verdict = "참" if bool(value) else "거짓"
        if detail:
            return f"`{keyword}` 조건 `{expression}` 은 {detail} 이므로 {verdict} 입니다."
        return f"`{keyword}` 조건 `{expression}` 의 결과는 {self._short_repr(value)} 이므로 {verdict} 입니다."

    def _describe_for_detail(self, node: ast.For, frame: FrameType) -> str:
        target = ast.unparse(node.target)
        iterable_expr = ast.unparse(node.iter)
        iterable_value = self._safe_eval_node(node.iter, frame)
        current_value = frame.f_locals.get(target)
        iterable_preview = self._preview_iterable(iterable_value)
        current_text = (
            f" 현재 `{target}` 값은 {self._short_repr(current_value)} 입니다."
            if target in frame.f_locals
            else ""
        )
        if iterable_preview:
            return (
                f"`for` 문에서 `{target}` 이 `{iterable_expr}` 를 순회합니다. "
                f"반복 대상은 {iterable_preview} 입니다.{current_text}"
            )
        return f"`for` 문에서 `{target}` 이 `{iterable_expr}` 를 순회합니다.{current_text}"

    def _describe_assign_detail(self, node: ast.Assign, frame: FrameType) -> str:
        if not node.targets:
            return ""
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Tuple)
            and isinstance(node.value, ast.Tuple)
            and len(node.targets[0].elts) == len(node.value.elts)
        ):
            targets = [ast.unparse(target) for target in node.targets[0].elts]
            values = []
            for value_node in node.value.elts:
                resolved = self._safe_eval_node(value_node, frame)
                values.append(
                    self._short_repr(resolved)
                    if resolved is not None
                    else ast.unparse(value_node)
                )
            return (
                "여러 값을 한 번에 다시 대입합니다. "
                f"`{', '.join(targets)}` 에 `{', '.join(values)}` 순서로 넣습니다."
            )
        target = ast.unparse(node.targets[0])
        value_expr = ast.unparse(node.value)
        value = self._safe_eval_node(node.value, frame)
        if value is None:
            return f"`{target}` 에 `{value_expr}` 결과를 대입합니다."
        return f"`{target}` 에 `{value_expr}` 의 값 {self._short_repr(value)} 를 대입합니다."

    def _describe_augassign_detail(self, node: ast.AugAssign, frame: FrameType) -> str:
        target_expr = ast.unparse(node.target)
        value_expr = ast.unparse(node.value)
        before = self._safe_eval_node(node.target, frame)
        delta = self._safe_eval_node(node.value, frame)
        op_text = self._operator_text(node.op)
        if before is None or delta is None:
            return f"`{target_expr} {op_text}= {value_expr}` 를 계산합니다."
        return (
            f"`{target_expr}` 의 현재 값 {self._short_repr(before)} 에 "
            f"`{value_expr}` 의 값 {self._short_repr(delta)} 를 {op_text} 연산합니다."
        )

    def _describe_return_detail(self, node: ast.Return, frame: FrameType) -> str:
        if node.value is None:
            return "`return` 으로 현재 함수를 종료합니다."
        value_expr = ast.unparse(node.value)
        value = self._safe_eval_node(node.value, frame)
        if value is None:
            return f"`return {value_expr}` 를 실행합니다."
        return f"`return {value_expr}` 는 {self._short_repr(value)} 를 반환합니다."

    def _describe_call_detail(self, node: ast.Call, frame: FrameType) -> str:
        func_expr = ast.unparse(node.func)
        arg_bits: list[str] = []
        for arg in node.args[:4]:
            arg_expr = ast.unparse(arg)
            arg_value = self._safe_eval_node(arg, frame)
            if arg_value is None:
                arg_bits.append(arg_expr)
            else:
                arg_bits.append(f"{arg_expr}={self._short_repr(arg_value)}")
        if arg_bits:
            return f"`{func_expr}` 호출에 전달되는 값은 {', '.join(arg_bits)} 입니다."
        return f"`{func_expr}` 함수를 호출합니다."

    def _describe_test_operands(self, test: ast.AST, frame: FrameType) -> str:
        if isinstance(test, ast.Compare):
            expressions = [test.left, *test.comparators]
            values = [self._safe_eval_node(expr, frame) for expr in expressions]
            if any(value is None for value in values):
                return ""
            op_texts = [self._compare_operator_text(op) for op in test.ops]
            pieces = [self._short_repr(values[0])]
            for op_text, value in zip(op_texts, values[1:]):
                pieces.append(f"{op_text} {self._short_repr(value)}")
            return "실제 비교는 `" + " ".join(pieces) + "`"

        if isinstance(test, ast.BoolOp):
            rendered: list[str] = []
            for expr in test.values:
                value = self._safe_eval_node(expr, frame)
                if value is None:
                    continue
                rendered.append(f"{ast.unparse(expr)}={self._short_repr(value)}")
            if rendered:
                joiner = " and " if isinstance(test.op, ast.And) else " or "
                return "세부 조건은 `" + joiner.join(rendered) + "`"

        return ""

    def _safe_eval_node(self, node: ast.AST, frame: FrameType) -> Any | None:
        if self._contains_unsafe_call(node):
            return None
        try:
            compiled = compile(ast.Expression(node), USER_FILENAME, "eval")
            return eval(compiled, self.globals_env, frame.f_locals)
        except Exception:  # noqa: BLE001
            return None

    def _parse_line_node(self, stripped: str) -> ast.stmt | None:
        candidates = [stripped]
        if stripped.endswith(":"):
            candidates.insert(0, f"{stripped}\n    pass")

        for source in candidates:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            if tree.body:
                return tree.body[0]
        return None

    def _contains_unsafe_call(self, node: ast.AST) -> bool:
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            call_name = self._ast_call_name(child.func)
            if call_name in {"range", "len"}:
                continue
            return True
        return False

    def _ast_call_name(self, func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            root = self._ast_call_name(func.value)
            return f"{root}.{func.attr}" if root else func.attr
        return ""

    def _preview_iterable(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, range):
            preview = list(value[:8])
            suffix = " ..." if len(value) > 8 else ""
            return f"`{preview}{suffix}`"
        if isinstance(value, (list, tuple)):
            preview = list(value[:8])
            suffix = " ..." if len(value) > 8 else ""
            return f"`{preview}{suffix}`"
        return f"`{self._short_repr(value)}`"

    def _compare_operator_text(self, operator_node: ast.cmpop) -> str:
        mapping = {
            ast.Eq: "==",
            ast.NotEq: "!=",
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.Gt: ">",
            ast.GtE: ">=",
            ast.In: "in",
            ast.NotIn: "not in",
            ast.Is: "is",
            ast.IsNot: "is not",
        }
        for operator_type, symbol in mapping.items():
            if isinstance(operator_node, operator_type):
                return symbol
        return "?"

    def _operator_text(self, operator_node: ast.operator) -> str:
        mapping = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.FloorDiv: "//",
            ast.Mod: "%",
        }
        for operator_type, symbol in mapping.items():
            if isinstance(operator_node, operator_type):
                return symbol
        return "?"

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
            return self._generic_summary_text()

        labels = {
            "stack": "스택으로 판단해 top 중심으로 보여줍니다.",
            "queue": "큐로 판단해 front / back 흐름을 보여줍니다.",
            "tree": "트리로 판단해 현재 노드와 전체 구조를 함께 보여줍니다.",
            "linked-list": "연결 리스트로 판단해 노드 간 next/prev 포인터 흐름을 보여줍니다.",
        }
        return labels.get(structure.get("kind"), "")

    def _generic_summary_text(self) -> str:
        return "특정 자료구조가 감지되지 않아 실행 상태 요약을 유지합니다."

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
