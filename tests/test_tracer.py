import unittest

from tracer import ExecutionTracer


class ExecutionTracerTest(unittest.TestCase):
    def setUp(self):
        self.tracer = ExecutionTracer()

    def test_collects_basic_steps_and_stdout(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "x = 1",
                    "x += 2",
                    "print(x)",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["steps"]), 4)
        self.assertEqual(result["stdout"].strip(), "3")
        self.assertIn("x", result["steps"][-1]["globals"])

    def test_builds_recursive_call_tree_for_dfs(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "graph = {1: [2, 3], 2: [], 3: []}",
                    "visited = set()",
                    "",
                    "def dfs(node):",
                    "    visited.add(node)",
                    "    for nxt in graph[node]:",
                    "        if nxt not in visited:",
                    "            dfs(nxt)",
                    "",
                    "dfs(1)",
                ]
            )
        )

        self.assertTrue(result["ok"])
        last_tree = result["steps"][-1]["call_tree"]
        labels = []

        def walk(node):
            labels.append(node["label"])
            for child in node.get("children", []):
                walk(child)

        walk(last_tree)
        self.assertTrue(any(label.startswith("dfs(") for label in labels))
        self.assertIsNotNone(result["steps"][-1]["graph"])

    def test_blocks_disallowed_imports(self):
        result = self.tracer.trace("import os\n")

        self.assertFalse(result["ok"])
        self.assertIn("blocked", result["error"])

    def test_supports_stdin_input(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "name = input()",
                    'print("hello", name)',
                ]
            ),
            stdin="codex",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "hello codex")

    def test_detects_stack_and_queue_structures(self):
        stack_result = self.tracer.trace(
            "\n".join(
                [
                    "stack = []",
                    "stack.append(1)",
                    "stack.append(2)",
                    "stack.pop()",
                ]
            )
        )
        queue_result = self.tracer.trace(
            "\n".join(
                [
                    "from collections import deque",
                    "queue = deque([1, 2])",
                    "queue.append(3)",
                    "queue.popleft()",
                ]
            )
        )

        self.assertEqual(stack_result["steps"][-1]["structure"]["kind"], "stack")
        self.assertEqual(queue_result["steps"][-1]["structure"]["kind"], "queue")
        self.assertTrue(
            any(item["kind"] == "stack" for item in stack_result["analysis"]["structures"])
        )
        self.assertTrue(
            any(item["kind"] == "queue" for item in queue_result["analysis"]["structures"])
        )

    def test_infers_structure_from_code_pattern_without_explicit_names(self):
        stack_result = self.tracer.trace(
            "\n".join(
                [
                    "history = []",
                    "history.append(1)",
                    "history.append(2)",
                    "history.pop()",
                ]
            )
        )
        queue_result = self.tracer.trace(
            "\n".join(
                [
                    "from collections import deque",
                    "tasks = deque([1, 2])",
                    "tasks.append(3)",
                    "tasks.popleft()",
                ]
            )
        )

        self.assertEqual(stack_result["steps"][-1]["structure"]["name"], "history")
        self.assertEqual(stack_result["steps"][-1]["structure"]["kind"], "stack")
        self.assertEqual(queue_result["steps"][-1]["structure"]["name"], "tasks")
        self.assertEqual(queue_result["steps"][-1]["structure"]["kind"], "queue")

    def test_detects_binary_tree_structure(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "class Node:",
                    "    def __init__(self, value, left=None, right=None):",
                    "        self.value = value",
                    "        self.left = left",
                    "        self.right = right",
                    "",
                    'root = Node("A", Node("B"), Node("C"))',
                    "",
                    "def visit(node):",
                    "    if node is None:",
                    "        return",
                    "    print(node.value)",
                    "    visit(node.left)",
                    "    visit(node.right)",
                    "",
                    "visit(root)",
                ]
            )
        )

        structure = result["steps"][-1]["structure"]
        self.assertEqual(structure["kind"], "tree")
        self.assertEqual(structure["root"]["label"], "'A'")
        self.assertTrue(
            any(item["kind"] == "tree" for item in result["analysis"]["structures"])
        )

    def test_marks_sorting_intent_and_collects_call_tree(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "def merge_sort(arr):",
                    "    if len(arr) <= 1:",
                    "        return arr",
                    "    mid = len(arr) // 2",
                    "    left = merge_sort(arr[:mid])",
                    "    right = merge_sort(arr[mid:])",
                    "    merged = []",
                    "    i = j = 0",
                    "    while i < len(left) and j < len(right):",
                    "        if left[i] <= right[j]:",
                    "            merged.append(left[i])",
                    "            i += 1",
                    "        else:",
                    "            merged.append(right[j])",
                    "            j += 1",
                    "    merged.extend(left[i:])",
                    "    merged.extend(right[j:])",
                    "    return merged",
                    "",
                    "nums = [5, 1, 4, 2, 8]",
                    "print(merge_sort(nums))",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["analysis"]["intents"]["sorting"])
        self.assertTrue(
            any(
                step.get("call_tree")
                and step["call_tree"].get("children")
                for step in result["steps"]
            )
        )

    def test_detects_sorting_intent_from_compare_swap_pattern(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "def reorder(values):",
                    "    n = len(values)",
                    "    for i in range(n):",
                    "        for j in range(0, n - i - 1):",
                    "            if values[j] > values[j + 1]:",
                    "                values[j], values[j + 1] = values[j + 1], values[j]",
                    "    return values",
                    "",
                    "data = [9, 1, 4, 2]",
                    "print(reorder(data))",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["analysis"]["intents"]["sorting"])
        self.assertEqual(result["analysis"]["intents"]["sorting_order"], "asc")

    def test_detects_descending_sort_order_from_compare_swap_pattern(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "def reorder_desc(values):",
                    "    n = len(values)",
                    "    for i in range(n):",
                    "        for j in range(0, n - i - 1):",
                    "            if values[j] < values[j + 1]:",
                    "                values[j], values[j + 1] = values[j + 1], values[j]",
                    "    return values",
                    "",
                    "data = [1, 9, 3, 7]",
                    "print(reorder_desc(data))",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["analysis"]["intents"]["sorting"])
        self.assertEqual(result["analysis"]["intents"]["sorting_order"], "desc")

    def test_detects_insertion_pattern_without_sort_name(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "def reorder(values):",
                    "    for i in range(1, len(values)):",
                    "        key = values[i]",
                    "        j = i - 1",
                    "        while j >= 0 and values[j] > key:",
                    "            values[j + 1] = values[j]",
                    "            j -= 1",
                    "        values[j + 1] = key",
                    "    return values",
                    "",
                    "data = [9, 3, 7, 1]",
                    "print(reorder(data))",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["analysis"]["intents"]["sorting"])
        self.assertEqual(result["analysis"]["intents"]["sorting_order"], "asc")


if __name__ == "__main__":
    unittest.main()
