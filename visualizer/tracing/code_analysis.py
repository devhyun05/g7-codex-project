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
            "summary": "",
            "intents": {"sorting": False, "sorting_order": "unknown"},
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
        self.sorting_order = "unknown"

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
        summary = ", ".join(f"{item['kind']}({item['name']})" for item in structures)
        return {
            "structures": structures,
            "intent_map": {name: hint["kind"] for name, hint in self.hints.items()},
            "summary": summary,
            "intents": {
                "sorting": self.sorting_detected,
                "sorting_order": self.sorting_order,
            },
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
        if self._looks_like_sort_name(node.name):
            self.sorting_detected = True
        if self._has_indexed_sorting_pattern(node):
            self.sorting_detected = True
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for name in self._target_names(node.targets):
            self._inspect_assignment(name, node.value)
        if self._is_in_place_swap_assignment(node):
            self.sorting_detected = True
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
            elif attr == "sort":
                self.sorting_detected = True
        elif isinstance(node.func, ast.Name):
            lowered = node.func.id.lower()
            if lowered == "sorted" or self._looks_like_sort_name(lowered):
                self.sorting_detected = True
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        compared = self._compared_subscript_name(node.test)
        if compared:
            compared_name, compared_order = compared
            if any(self._is_in_place_swap_assignment(stmt, compared_name) for stmt in node.body):
                self.sorting_detected = True
                self._register_sort_order(compared_order)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._looks_like_sort_compare(node):
            self.sorting_detected = True
            self._register_sort_order(self._infer_sort_order(node))
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

    def _looks_like_sort_name(self, name: str) -> bool:
        lowered = name.lower()
        if "sort" in lowered:
            return True
        return lowered in {
            "quicksort",
            "quick_sort",
            "mergesort",
            "merge_sort",
            "heapsort",
            "heap_sort",
            "insertionsort",
            "insertion_sort",
            "selectionsort",
            "selection_sort",
            "bubblesort",
            "bubble_sort",
            "radixsort",
            "radix_sort",
            "countingsort",
            "counting_sort",
            "shellsort",
            "shell_sort",
        }

    def _register_sort_order(self, order: str | None) -> None:
        if not order or order == "unknown":
            return
        if self.sorting_order == "unknown":
            self.sorting_order = order
            return
        if self.sorting_order != order:
            self.sorting_order = "unknown"

    def _has_indexed_sorting_pattern(self, node: ast.FunctionDef) -> bool:
        loop_exists = False
        compared_names: set[str] = set()
        written_lists: set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, (ast.For, ast.While)):
                loop_exists = True

            if isinstance(child, ast.Compare):
                for name in self._subscripted_list_names(child):
                    compared_names.add(name)
                inferred = self._insertion_like_order(child)
                if inferred:
                    self._register_sort_order(inferred[1])

            if isinstance(child, ast.Assign):
                for target in child.targets:
                    for name in self._written_subscript_names(target):
                        written_lists.add(name)
            elif isinstance(child, ast.AugAssign):
                for name in self._written_subscript_names(child.target):
                    written_lists.add(name)

        if not loop_exists:
            return False

        return bool(compared_names & written_lists)

    def _subscripted_list_names(self, node: ast.AST) -> set[str]:
        names: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Subscript) and isinstance(child.value, ast.Name):
                names.add(child.value.id)
        return names

    def _written_subscript_names(self, node: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            names.add(node.value.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                names |= self._written_subscript_names(elt)
        return names

    def _operator_order(self, op: ast.cmpop) -> str:
        if isinstance(op, (ast.Gt, ast.GtE)):
            return "asc"
        if isinstance(op, (ast.Lt, ast.LtE)):
            return "desc"
        return "unknown"

    def _insertion_like_order(self, node: ast.Compare) -> tuple[str, str] | None:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return None
        left_names = self._subscripted_list_names(node.left)
        right_names = self._subscripted_list_names(node.comparators[0])
        if not left_names and not right_names:
            return None

        if left_names and not right_names and len(left_names) == 1:
            return (next(iter(left_names)), self._operator_order(node.ops[0]))
        if right_names and not left_names and len(right_names) == 1:
            reversed_order = self._reverse_order(self._operator_order(node.ops[0]))
            return (next(iter(right_names)), reversed_order)
        return None

    def _reverse_order(self, order: str) -> str:
        if order == "asc":
            return "desc"
        if order == "desc":
            return "asc"
        return "unknown"

    def _compared_subscript_name(self, node: ast.AST) -> tuple[str, str] | None:
        if not isinstance(node, ast.Compare):
            return None
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return None
        if not isinstance(node.ops[0], (ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq)):
            return None

        left = self._subscript_key(node.left)
        right = self._subscript_key(node.comparators[0])
        if not left or not right:
            return None
        if left[0] != right[0] or left[1] == right[1]:
            return None

        if isinstance(node.ops[0], (ast.Gt, ast.GtE)):
            order = "asc"
        elif isinstance(node.ops[0], (ast.Lt, ast.LtE)):
            order = "desc"
        else:
            order = "unknown"
        return (left[0], order)

    def _is_in_place_swap_assignment(
        self,
        node: ast.AST,
        constrained_name: str | None = None,
    ) -> bool:
        if not isinstance(node, ast.Assign):
            return False
        if len(node.targets) != 1:
            return False
        left_elements = self._tuple_elements(node.targets[0])
        right_elements = self._tuple_elements(node.value)
        if len(left_elements) != 2 or len(right_elements) != 2:
            return False

        left0 = self._subscript_key(left_elements[0])
        left1 = self._subscript_key(left_elements[1])
        right0 = self._subscript_key(right_elements[0])
        right1 = self._subscript_key(right_elements[1])
        if not all([left0, left1, right0, right1]):
            return False

        if constrained_name and (left0[0] != constrained_name or left1[0] != constrained_name):
            return False

        if left0[0] != left1[0]:
            return False

        return (
            left0[1] == right1[1]
            and left1[1] == right0[1]
            and right0[0] == left0[0]
            and right1[0] == left0[0]
        )

    def _tuple_elements(self, node: ast.AST) -> list[ast.AST]:
        if isinstance(node, (ast.Tuple, ast.List)):
            return list(node.elts)
        return []

    def _subscript_key(self, node: ast.AST) -> tuple[str, str] | None:
        if not isinstance(node, ast.Subscript):
            return None
        if not isinstance(node.value, ast.Name):
            return None
        return (
            node.value.id,
            ast.dump(node.slice, annotate_fields=True, include_attributes=False),
        )
