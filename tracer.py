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

USER_FILENAME = "<visualizer>"
MAX_ITEMS = 8
MAX_DEPTH = 3
MAX_REPR_LENGTH = 96


class TraceLimitExceeded(RuntimeError):
    pass


@dataclass
class TraceConfig:
    step_limit: int = 350
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

        return {
            "index": len(self.steps) + 1,
            "event": event,
            "line": line_number,
            "line_source": self._line_source(line_number),
            "message": self._build_message(frame, event, arg),
            "stdout": self.stdout_buffer.getvalue(),
            "stack": [self._serialize_frame(stack_frame) for stack_frame in stack_frames],
            "globals": self._serialize_namespace(self.globals_env),
            "call_tree": self._snapshot_tree(self.call_root, set(active_ids)),
            "graph": self._detect_graph_state(stack_frames),
            "structure": self._detect_structure_state(stack_frames),
        }

    def _append_terminal_step(self) -> None:
        terminal_event = "error" if self.error else "end"
        self.steps.append(
            {
                "index": len(self.steps) + 1,
                "event": terminal_event,
                "line": None,
                "line_source": "",
                "message": self.error or "프로그램 실행이 끝났습니다.",
                "stdout": self.stdout,
                "stack": [],
                "globals": self._serialize_namespace(self.globals_env),
                "call_tree": self._snapshot_tree(self.call_root, set()),
                "graph": self._detect_graph_state([]),
                "structure": self._detect_structure_state([]),
            }
        )

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

    def _detect_graph_state(self, stack_frames: list[FrameType]) -> dict[str, Any] | None:
        scopes = [frame.f_locals for frame in reversed(stack_frames)]
        scopes.append(self.globals_env)

        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for scope in scopes:
            for name, value in scope.items():
                graph = self._coerce_graph(value)
                if graph:
                    score = 20 if name in {"graph", "tree", "adj", "adj_list"} else 10
                    candidates.append((score, name, graph))

        if not candidates:
            return None

        _, graph_name, graph = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
        node_values = {node["id"] for node in graph["nodes"]}
        current_node = self._detect_current_node(scopes, node_values)
        visited_nodes = self._detect_visited_nodes(scopes, node_values)

        return {
            "name": graph_name,
            "nodes": [
                {
                    **node,
                    "current": node["id"] == current_node,
                    "visited": node["id"] in visited_nodes,
                }
                for node in graph["nodes"]
            ],
            "edges": graph["edges"],
            "tree_mode": graph["tree_mode"],
        }

    def _detect_structure_state(self, stack_frames: list[FrameType]) -> dict[str, Any] | None:
        scopes = [frame.f_locals for frame in reversed(stack_frames)]
        scopes.append(self.globals_env)

        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for scope in scopes:
            for name, value in scope.items():
                structure = self._coerce_structure(name, value, scopes)
                if structure:
                    candidates.append((structure.pop("_score"), name, structure))

        if not candidates:
            return None

        _, _, structure = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
        return structure

    def _coerce_structure(
        self,
        name: str,
        value: Any,
        scopes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        tree = self._coerce_tree(name, value, scopes)
        if tree:
            return tree

        queue = self._coerce_queue(name, value)
        if queue:
            return queue

        stack = self._coerce_stack(name, value)
        if stack:
            return stack

        return None

    def _coerce_stack(self, name: str, value: Any) -> dict[str, Any] | None:
        lowered = name.lower()
        if lowered not in {"stack", "stk"} and "stack" not in lowered:
            return None

        if not isinstance(value, (list, tuple)):
            return None

        items = list(value)
        return {
            "_score": 55 if lowered == "stack" else 45,
            "kind": "stack",
            "name": name,
            "items": [self._short_repr(item) for item in items[:MAX_ITEMS]],
            "truncated": len(items) > MAX_ITEMS,
            "top_index": len(items) - 1 if items else None,
        }

    def _coerce_queue(self, name: str, value: Any) -> dict[str, Any] | None:
        lowered = name.lower()
        queue_names = {"queue", "deque", "dq"}
        if lowered not in queue_names and "queue" not in lowered and "deque" not in lowered:
            return None

        if isinstance(value, collections.deque):
            items = list(value)
        elif isinstance(value, list):
            items = list(value)
        else:
            return None

        return {
            "_score": 55 if lowered == "queue" else 45,
            "kind": "queue",
            "name": name,
            "items": [self._short_repr(item) for item in items[:MAX_ITEMS]],
            "truncated": len(items) > MAX_ITEMS,
            "front_index": 0 if items else None,
            "back_index": len(items) - 1 if items else None,
        }

    def _coerce_tree(
        self,
        name: str,
        value: Any,
        scopes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        root = self._build_tree_payload(value, seen=set())
        if not root:
            return None

        current_id = self._detect_current_tree_node(scopes, root["node_ids"])
        return {
            "_score": 70 if name.lower() in {"root", "tree"} else 52,
            "kind": "tree",
            "name": name,
            "root": root["tree"],
            "current_id": current_id,
        }

    def _build_tree_payload(
        self,
        value: Any,
        seen: set[int],
    ) -> dict[str, Any] | None:
        node_value_id = id(value)
        if node_value_id in seen:
            return None

        children = self._extract_tree_children(value)
        if children is None:
            return None

        next_seen = seen | {node_value_id}
        node_id = self._tree_node_id(value)
        built_children = []
        node_ids = {node_id}
        for child in children[:MAX_ITEMS]:
            if child is None:
                continue
            built_child = self._build_tree_payload(child, next_seen)
            if built_child:
                built_children.append(built_child["tree"])
                node_ids |= built_child["node_ids"]

        return {
            "tree": {
                "id": node_id,
                "label": self._extract_tree_label(value),
                "children": built_children,
            },
            "node_ids": node_ids,
        }

    def _extract_tree_children(self, value: Any) -> list[Any] | None:
        if isinstance(value, dict):
            keys = set(value.keys())
            if {"left", "right"} & keys:
                return [value.get("left"), value.get("right")]
            if "children" in value and isinstance(value["children"], (list, tuple)):
                return list(value["children"])
            return None

        attr_names = dir(value)
        if "children" in attr_names:
            children = getattr(value, "children", None)
            if isinstance(children, (list, tuple)):
                return list(children)

        if "left" in attr_names or "right" in attr_names:
            return [getattr(value, "left", None), getattr(value, "right", None)]

        return None

    def _extract_tree_label(self, value: Any) -> str:
        if isinstance(value, dict):
            for key in ("value", "val", "data", "key"):
                if key in value:
                    return self._short_repr(value[key])
            return self._short_repr(value)

        for attr_name in ("value", "val", "data", "key"):
            if hasattr(value, attr_name):
                return self._short_repr(getattr(value, attr_name))
        return self._short_repr(value)

    def _detect_current_tree_node(
        self,
        scopes: list[dict[str, Any]],
        node_ids: set[str],
    ) -> str | None:
        current_names = ["node", "cur", "current", "root"]
        for scope in scopes:
            for name in current_names:
                if name not in scope:
                    continue
                node_id = self._tree_node_id(scope[name])
                if node_id in node_ids:
                    return node_id
        return None

    def _coerce_graph(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            nodes: set[str] = set()
            edges: list[dict[str, str]] = []
            for raw_source, raw_targets in value.items():
                if not self._is_scalar_node(raw_source):
                    return None
                source = self._node_id(raw_source)
                nodes.add(source)

                if isinstance(raw_targets, dict):
                    targets = raw_targets.keys()
                elif isinstance(raw_targets, (list, tuple, set, frozenset)):
                    targets = raw_targets
                else:
                    return None

                for raw_target in targets:
                    if not self._is_scalar_node(raw_target):
                        return None
                    target = self._node_id(raw_target)
                    nodes.add(target)
                    edges.append({"source": source, "target": target})
            return self._graph_payload(nodes, edges)

        if isinstance(value, (list, tuple)):
            if not value:
                return None

            if all(
                isinstance(item, (list, tuple, set, frozenset))
                for item in value
            ):
                start_index = 1 if value and not value[0] else 0
                nodes: set[str] = set()
                edges: list[dict[str, str]] = []
                for index, raw_targets in enumerate(value[start_index:], start=start_index):
                    source = self._node_id(index)
                    nodes.add(source)
                    for raw_target in raw_targets:
                        if not self._is_scalar_node(raw_target):
                            return None
                        target = self._node_id(raw_target)
                        nodes.add(target)
                        edges.append({"source": source, "target": target})
                return self._graph_payload(nodes, edges)

        return None

    def _graph_payload(self, nodes: set[str], edges: list[dict[str, str]]) -> dict[str, Any]:
        undirected_edge_keys = {
            tuple(sorted((edge["source"], edge["target"])))
            for edge in edges
        }
        sorted_nodes = sorted(nodes, key=self._sort_key)
        return {
            "nodes": [{"id": node_id, "label": node_id} for node_id in sorted_nodes],
            "edges": edges,
            "tree_mode": bool(sorted_nodes) and len(undirected_edge_keys) == len(sorted_nodes) - 1,
        }

    def _detect_current_node(self, scopes: list[dict[str, Any]], node_values: set[str]) -> str | None:
        current_names = ["node", "cur", "current", "v", "u", "start", "vertex"]
        for scope in scopes:
            for name in current_names:
                value = scope.get(name)
                if self._is_scalar_node(value):
                    node_id = self._node_id(value)
                    if node_id in node_values:
                        return node_id
        return None

    def _detect_visited_nodes(self, scopes: list[dict[str, Any]], node_values: set[str]) -> set[str]:
        visited_names = ["visited", "seen"]
        for scope in scopes:
            for name in visited_names:
                value = scope.get(name)
                if isinstance(value, dict):
                    nodes = {self._node_id(key) for key, flag in value.items() if flag}
                elif isinstance(value, (list, tuple, set, frozenset)):
                    nodes = {
                        self._node_id(item)
                        for item in value
                        if self._is_scalar_node(item)
                    }
                else:
                    continue
                return nodes & node_values
        return set()

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

    def _is_scalar_node(self, value: Any) -> bool:
        return isinstance(value, (int, str)) and not isinstance(value, bool)

    def _node_id(self, value: Any) -> str:
        return str(value)

    def _sort_key(self, value: str) -> tuple[int, Any]:
        if value.isdigit():
            return (0, int(value))
        return (1, value)

    def _tree_node_id(self, value: Any) -> str:
        return f"node-{id(value)}"
