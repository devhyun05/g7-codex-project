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

    def test_supports_sys_stdin_readline_and_recursionlimit(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "import sys",
                    "sys.setrecursionlimit(10**6)",
                    "n = int(sys.stdin.readline())",
                    "nums = list(map(int, sys.stdin.readline().split()))",
                    "print(n, sum(nums))",
                ]
            ),
            stdin="4\n1 2 3 4\n",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "4 10")

    def test_supports_common_algorithm_modules(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "from bisect import bisect_left",
                    "from functools import reduce",
                    "arr = [1, 3, 5]",
                    "print(bisect_left(arr, 4))",
                    "print(reduce(lambda a, b: a + b, arr, 0))",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip().splitlines(), ["2", "9"])

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

    def test_keeps_frame_locals_after_recursive_return(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "def walk(n):",
                    "    if n == 0:",
                    "        return n",
                    "    child = walk(n - 1)",
                    "    return child + 1",
                    "",
                    "walk(2)",
                ]
            )
        )

        self.assertTrue(result["ok"])
        return_steps = [step for step in result["steps"] if step["event"] == "return"]
        self.assertTrue(return_steps)

        latest_tree = return_steps[-1]["call_tree"]
        returned_nodes = []

        def walk(node):
            if node.get("status") == "returned":
                returned_nodes.append(node)
            for child in node.get("children", []):
                walk(child)

        walk(latest_tree)
        self.assertTrue(returned_nodes)
        self.assertTrue(any("n" in node.get("locals", {}) for node in returned_nodes))


if __name__ == "__main__":
    unittest.main()
