from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any


def analyze_code_structures(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {
            "structures": [],
            "intent_map": {},
            "intents": {"sorting": False, "sorting_order": None},
            "summary": "",
        }

    analyzer = CodeStructureAnalyzer()
    analyzer.visit(tree)
    return analyzer.build_result()


class CodeStructureAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.collection_aliases = {"collections"}
        self.deque_aliases: set[str] = set()
        self.node_like_classes: set[str] = set()
        self.method_ops: dict[str, set[str]] = defaultdict(set)
        self.hints: dict[str, dict[str, Any]] = {}
        self.sorting_detected = False
        self.sorting_order: str | None = None

    def build_result(self) -> dict[str, Any]:
        for name, ops in self.method_ops.items():
            if {"appendleft", "popleft", "pop-left"} & ops:
                self._set_hint(
                    name,
                    "queue",
                    "appendleft / popleft / pop(0) 패턴을 사용해 큐로 판단했습니다.",
                    88,
                )
            elif {"append", "pop"} <= ops:
                self._set_hint(
                    name,
                    "stack",
                    "append + pop 패턴을 사용해 스택으로 판단했습니다.",
                    84,
                )

        structures = [
            {"kind": hint["kind"], "name": name, "reason": hint["reason"]}
            for name, hint in sorted(
                self.hints.items(),
                key=lambda item: (-item[1]["score"], item[0]),
            )
        ]
        summary = ", ".join(
            f"{item['kind']}({item['name']})"
            for item in structures
        )
        return {
            "structures": structures,
            "intent_map": {name: hint["kind"] for name, hint in self.hints.items()},
            "intents": {
                "sorting": self.sorting_detected,
                "sorting_order": self.sorting_order,
            },
            "summary": summary,
        }

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "collections":
                self.collection_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "collections":
            for alias in node.names:
                if alias.name == "deque":
                    self.deque_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        attrs: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    attr_name = self._self_attr_name(target)
                    if attr_name:
                        attrs.add(attr_name)
            elif isinstance(child, ast.AnnAssign):
                attr_name = self._self_attr_name(child.target)
                if attr_name:
                    attrs.add(attr_name)

        if {"left", "right"} & attrs or "children" in attrs:
            self.node_like_classes.add(node.name)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if "sort" in node.name.lower():
            self.sorting_detected = True
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for name in self._target_names(node.targets):
            self._inspect_assignment(name, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for name in self._target_names([node.target]):
            self._inspect_assignment(name, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._call_name(node.func)
        if call_name.endswith(".sort") or call_name == "sorted":
            self.sorting_detected = True
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            name = node.func.value.id
            attr = node.func.attr
            if attr in {"append", "appendleft", "popleft"}:
                self.method_ops[name].add(attr)
            elif attr == "pop":
                if node.args and self._is_zero_constant(node.args[0]):
                    self.method_ops[name].add("pop-left")
                else:
                    self.method_ops[name].add("pop")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._looks_like_sort_compare(node):
            self.sorting_detected = True
            inferred_order = self._infer_sort_order(node)
            if inferred_order and self.sorting_order is None:
                self.sorting_order = inferred_order
        self.generic_visit(node)

    def _inspect_assignment(self, name: str, value: ast.AST | None) -> None:
        if value is None:
            return

        if self._is_graph_literal(value):
            self._set_hint(
                name,
                "graph",
                "인접 리스트 형태의 dict를 사용해 그래프로 판단했습니다.",
                92,
            )
            return

        if self._is_queue_constructor(value):
            self._set_hint(
                name,
                "queue",
                "deque 생성 패턴을 사용해 큐로 판단했습니다.",
                90,
            )
            return

        if self._is_tree_literal(value):
            self._set_hint(
                name,
                "tree",
                "left / right / children 형태의 노드 구조를 사용해 트리로 판단했습니다.",
                90,
            )
            return

        if isinstance(value, ast.Call):
            call_name = self._call_name(value.func)
            if call_name in self.node_like_classes:
                self._set_hint(
                    name,
                    "tree",
                    f"{call_name} 노드 객체를 대입해 트리 루트로 판단했습니다.",
                    86,
                )

    def _set_hint(self, name: str, kind: str, reason: str, score: int) -> None:
        existing = self.hints.get(name)
        if existing and existing["score"] >= score:
            return
        self.hints[name] = {"kind": kind, "reason": reason, "score": score}

    def _target_names(self, targets: list[ast.AST]) -> list[str]:
        names: list[str] = []
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                names.extend(self._target_names(list(target.elts)))
        return names

    def _is_graph_literal(self, value: ast.AST) -> bool:
        if not isinstance(value, ast.Dict):
            return False
        if not value.keys:
            return False
        if not all(self._is_scalar_literal(key) for key in value.keys if key is not None):
            return False
        return all(self._is_graph_targets(item) for item in value.values)

    def _is_graph_targets(self, value: ast.AST) -> bool:
        if isinstance(value, ast.Dict):
            return all(self._is_scalar_literal(key) for key in value.keys if key is not None)
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return all(self._is_scalar_literal(item) for item in value.elts)
        return False

    def _is_queue_constructor(self, value: ast.AST) -> bool:
        if not isinstance(value, ast.Call):
            return False
        call_name = self._call_name(value.func)
        if not call_name:
            return False
        return call_name in self.deque_aliases or call_name.endswith(".deque")

    def _is_tree_literal(self, value: ast.AST) -> bool:
        if isinstance(value, ast.Dict):
            keys = {
                key.value
                for key in value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            return bool({"left", "right"} & keys or "children" in keys)

        if not isinstance(value, ast.Call):
            return False

        call_name = self._call_name(value.func)
        if call_name in self.node_like_classes:
            return True

        lowered = call_name.lower() if call_name else ""
        keyword_names = {keyword.arg for keyword in value.keywords if keyword.arg}
        return (
            lowered.endswith("node")
            or "left" in keyword_names
            or "right" in keyword_names
            or "children" in keyword_names
        )

    def _call_name(self, func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            root = self._call_name(func.value)
            return f"{root}.{func.attr}" if root else func.attr
        return ""

    def _is_scalar_literal(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, str))
            and not isinstance(node.value, bool)
        )

    def _is_zero_constant(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value == 0

    def _self_attr_name(self, target: ast.AST) -> str | None:
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            return target.attr
        return None

    def _looks_like_sort_compare(self, node: ast.Compare) -> bool:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return False

        left = node.left
        right = node.comparators[0]
        candidates = (ast.Subscript, ast.Name)
        return isinstance(left, candidates) and isinstance(right, candidates)

    def _infer_sort_order(self, node: ast.Compare) -> str | None:
        op = node.ops[0]
        if isinstance(op, (ast.Gt, ast.GtE, ast.LtE)):
            return "asc"
        if isinstance(op, ast.Lt):
            return "desc"
        return None
