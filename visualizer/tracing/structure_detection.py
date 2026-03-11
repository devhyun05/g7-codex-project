from __future__ import annotations

import collections
from types import FrameType
from typing import Any

MAX_ITEMS = 8
LINKED_MAX_ITEMS = 128
LINKED_NEXT_KEYS = ("next", "next_node", "nextNode", "nxt")
LINKED_PREV_KEYS = ("prev", "previous", "prev_node", "prevNode", "prv")
LINKED_POINTER_KEYS = LINKED_NEXT_KEYS + LINKED_PREV_KEYS
LINKED_HEAD_KEYS = ("head", "first", "start")


class StructureDetector:
    def __init__(self, short_repr, code_analysis: dict[str, Any] | None = None):
        self.short_repr = short_repr
        self.code_analysis = code_analysis or {}
        self.intent_map = self.code_analysis.get("intent_map", {})

    def detect_graph_state(
        self,
        stack_frames: list[FrameType],
        globals_env: dict[str, Any],
    ) -> dict[str, Any] | None:
        scopes = [frame.f_locals for frame in reversed(stack_frames)]
        scopes.append(globals_env)

        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for scope in scopes:
            for name, value in scope.items():
                if name.startswith("__"):
                    continue
                graph = self._coerce_graph(value)
                if graph:
                    score = self._graph_score(name)
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

    def detect_structure_state(
        self,
        stack_frames: list[FrameType],
        globals_env: dict[str, Any],
    ) -> dict[str, Any] | None:
        scopes = [frame.f_locals for frame in reversed(stack_frames)]
        scopes.append(globals_env)

        candidates: list[tuple[int, str, dict[str, Any]]] = []
        for scope in scopes:
            for name, value in scope.items():
                if name.startswith("__"):
                    continue
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

        linked_list = self._coerce_linked_list(name, value, scopes)
        if linked_list:
            return linked_list

        queue = self._coerce_queue(name, value)
        if queue:
            return queue

        stack = self._coerce_stack(name, value)
        if stack:
            return stack

        return None

    def _coerce_linked_list(
        self,
        name: str,
        value: Any,
        scopes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        payload = self._build_linked_list_payload(value)
        from_wrapper = False
        if not payload:
            head_value = self._extract_linked_head(value)
            if head_value is not None:
                payload = self._build_linked_list_payload(head_value)
                from_wrapper = bool(payload)
        if not payload:
            return None

        current_id = self._detect_current_linked_node(scopes, payload["node_ids"])
        lowered = name.lower()
        score = 55
        if self.intent_map.get(name) == "linked-list":
            score = 95
        elif lowered in {"head", "list_head", "linked_list", "ll"} or "head" in lowered:
            score = 82
        elif from_wrapper and ("linked" in lowered or "list" in lowered):
            score = 78
        score += min(len(payload["nodes"]), 24)

        return {
            "_score": score,
            "kind": "linked-list",
            "name": name,
            "list_type": payload["list_type"],
            "head_id": payload["head_id"],
            "current_id": current_id,
            "nodes": payload["nodes"],
            "truncated": payload["truncated"],
            "cycle": payload["cycle"],
        }

    def _coerce_stack(self, name: str, value: Any) -> dict[str, Any] | None:
        if self.intent_map.get(name) != "stack" and not self._stack_like_name(name):
            return None

        if not isinstance(value, (list, tuple)):
            return None

        items = list(value)
        return {
            "_score": 92 if self.intent_map.get(name) == "stack" else 54,
            "kind": "stack",
            "name": name,
            "items": [self.short_repr(item) for item in items[:MAX_ITEMS]],
            "truncated": len(items) > MAX_ITEMS,
            "top_index": len(items) - 1 if items else None,
        }

    def _coerce_queue(self, name: str, value: Any) -> dict[str, Any] | None:
        if self.intent_map.get(name) != "queue" and not self._queue_like_name(name):
            return None

        if isinstance(value, collections.deque):
            items = list(value)
        elif isinstance(value, list):
            items = list(value)
        else:
            return None

        return {
            "_score": 92 if self.intent_map.get(name) == "queue" else 54,
            "kind": "queue",
            "name": name,
            "items": [self.short_repr(item) for item in items[:MAX_ITEMS]],
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
            "_score": 94 if self.intent_map.get(name) == "tree" else 70 if name.lower() in {"root", "tree"} else 52,
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

        try:
            attrs = dir(value)
        except Exception:  # noqa: BLE001
            return None

        if "children" in attrs:
            children = getattr(value, "children", None)
            if isinstance(children, (list, tuple)):
                return list(children)

        if "left" in attrs or "right" in attrs:
            return [getattr(value, "left", None), getattr(value, "right", None)]

        return None

    def _build_linked_list_payload(self, value: Any) -> dict[str, Any] | None:
        if not self._is_linked_node(value):
            return None

        nodes: list[dict[str, Any]] = []
        node_ids: set[str] = set()
        seen: set[str] = set()
        cursor = self._resolve_linked_head(value)
        truncated = False
        cycle = False
        is_doubly = False

        while self._is_linked_node(cursor):
            node_id = self._linked_node_id(cursor)
            if node_id in seen:
                cycle = True
                break

            seen.add(node_id)
            node_ids.add(node_id)

            next_node = self._extract_linked_next(cursor)
            prev_node = self._extract_linked_prev(cursor)
            next_id = self._linked_node_id(next_node) if self._is_linked_node(next_node) else None
            prev_id = self._linked_node_id(prev_node) if self._is_linked_node(prev_node) else None
            if self._has_linked_prev_field(cursor) or prev_id:
                is_doubly = True

            nodes.append(
                {
                    "id": node_id,
                    "label": self._extract_linked_label(cursor),
                    "next_id": next_id,
                    "prev_id": prev_id,
                }
            )

            if len(nodes) >= LINKED_MAX_ITEMS:
                if self._is_linked_node(next_node):
                    truncated = True
                break

            if not self._is_linked_node(next_node):
                break
            cursor = next_node

        if not nodes:
            return None

        has_pointer_link = any(
            node.get("next_id") is not None or node.get("prev_id") is not None
            for node in nodes
        )
        if not has_pointer_link:
            # Ignore isolated node allocations and start rendering once links are formed.
            return None

        return {
            "list_type": "doubly" if is_doubly else "singly",
            "head_id": nodes[0]["id"],
            "node_ids": node_ids,
            "nodes": nodes,
            "truncated": truncated,
            "cycle": cycle,
        }

    def _is_linked_node(self, value: Any) -> bool:
        if value is None:
            return False

        if isinstance(value, dict):
            if not any(key in value for key in LINKED_POINTER_KEYS):
                return False
            if any(key in value for key in ("value", "val", "data", "key")):
                return True
            non_link_keys = [key for key in value.keys() if key not in LINKED_POINTER_KEYS]
            return len(non_link_keys) == 1

        try:
            if not any(hasattr(value, key) for key in LINKED_POINTER_KEYS):
                return False
            if any(hasattr(value, key) for key in ("value", "val", "data", "key")):
                return True
            attrs = getattr(value, "__dict__", {})
            return isinstance(attrs, dict) and len(attrs) <= 5
        except Exception:  # noqa: BLE001
            return False

    def _extract_linked_next(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key in LINKED_NEXT_KEYS:
                if key in value:
                    return value.get(key)
            return None
        for key in LINKED_NEXT_KEYS:
            if hasattr(value, key):
                return getattr(value, key, None)
        return None

    def _extract_linked_prev(self, value: Any) -> Any:
        if isinstance(value, dict):
            for key in LINKED_PREV_KEYS:
                if key in value:
                    return value.get(key)
            return None
        for key in LINKED_PREV_KEYS:
            if hasattr(value, key):
                return getattr(value, key, None)
        return None

    def _has_linked_prev_field(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(key in value for key in LINKED_PREV_KEYS)
        return any(hasattr(value, key) for key in LINKED_PREV_KEYS)

    def _resolve_linked_head(self, value: Any) -> Any:
        cursor = value
        seen: set[str] = set()
        for _ in range(LINKED_MAX_ITEMS):
            if not self._is_linked_node(cursor):
                break
            node_id = self._linked_node_id(cursor)
            if node_id in seen:
                break
            seen.add(node_id)
            prev_node = self._extract_linked_prev(cursor)
            if not self._is_linked_node(prev_node):
                break
            cursor = prev_node
        return cursor

    def _extract_linked_head(self, value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, dict):
            for key in LINKED_HEAD_KEYS:
                if key in value:
                    return value.get(key)
            return None

        for key in LINKED_HEAD_KEYS:
            if hasattr(value, key):
                return getattr(value, key, None)
        return None

    def _extract_linked_label(self, value: Any) -> str:
        if isinstance(value, dict):
            for key in ("value", "val", "data", "key"):
                if key in value:
                    return self.short_repr(value[key])
            return self.short_repr(value)

        for attr in ("value", "val", "data", "key"):
            if hasattr(value, attr):
                return self.short_repr(getattr(value, attr))
        return self.short_repr(value)

    def _detect_current_linked_node(
        self,
        scopes: list[dict[str, Any]],
        node_ids: set[str],
    ) -> str | None:
        current_names = ["cur", "current", "node", "cursor", "ptr", "temp", "head", "tail"]
        for scope in scopes:
            for name in current_names:
                if name not in scope:
                    continue
                node_id = self._linked_node_id(scope[name])
                if node_id in node_ids:
                    return node_id
            for value in scope.values():
                if value is None:
                    continue
                for attr in current_names:
                    if not hasattr(value, attr):
                        continue
                    node_id = self._linked_node_id(getattr(value, attr))
                    if node_id in node_ids:
                        return node_id
        return None

    def _extract_tree_label(self, value: Any) -> str:
        if isinstance(value, dict):
            for key in ("value", "val", "data", "key"):
                if key in value:
                    return self.short_repr(value[key])
            return self.short_repr(value)

        for attr_name in ("value", "val", "data", "key"):
            if hasattr(value, attr_name):
                return self.short_repr(getattr(value, attr_name))
        return self.short_repr(value)

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
            if all(isinstance(item, (list, tuple, set, frozenset)) for item in value):
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

    def _graph_score(self, name: str) -> int:
        if self.intent_map.get(name) == "graph":
            return 92
        if name in {"graph", "tree", "adj", "adj_list"}:
            return 70
        return 42

    def _stack_like_name(self, name: str) -> bool:
        lowered = name.lower()
        return lowered in {"stack", "stk"} or "stack" in lowered

    def _queue_like_name(self, name: str) -> bool:
        lowered = name.lower()
        queue_names = {"queue", "deque", "dq"}
        return lowered in queue_names or "queue" in lowered or "deque" in lowered

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

    def _linked_node_id(self, value: Any) -> str:
        return f"ll-{id(value)}"
