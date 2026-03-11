import unittest
import shutil

from visualizer.services.language_service import LanguageDetector
from visualizer.services.tracing_registry import TracingRegistry
from visualizer.services.trace_service import TraceService
from visualizer.tracing.javascript_tracer import JavaScriptLineTracer
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

    def test_normalizes_smart_quotes_in_source(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "text = “hello”",
                    "print(text)",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "hello")

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
                step.get("call_tree") and step["call_tree"].get("children")
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

    def test_explains_condition_with_runtime_values(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "arr = [3, 2]",
                    "j = 0",
                    "if arr[j] > arr[j + 1]:",
                    "    arr[j], arr[j + 1] = arr[j + 1], arr[j]",
                    "print(arr)",
                ]
            )
        )

        self.assertTrue(result["ok"])
        target_step = next(step for step in result["steps"] if step["line"] == 3)
        self.assertIn("실제 비교는", target_step["explanation"])
        self.assertIn("3 > 2", target_step["explanation"])


class LanguageDetectorTest(unittest.TestCase):
    def setUp(self):
        self.detector = LanguageDetector()

    def test_detects_cpp_code(self):
        result = self.detector.detect(
            "\n".join(
                [
                    "#include <bits/stdc++.h>",
                    "using namespace std;",
                    "int main() {",
                    "  ios::sync_with_stdio(false);",
                    "  cout << 1 << '\\n';",
                    "}",
                ]
            )
        )

        self.assertEqual(result["key"], "cpp")
        self.assertFalse(result["trace_supported"])

    def test_honors_manual_language_selection(self):
        result = self.detector.detect("console.log(1);", requested="javascript")

        self.assertEqual(result["key"], "javascript")
        self.assertEqual(result["source"], "manual")

    def test_trace_service_returns_language_metadata_for_non_python_code(self):
        class FakeExecutor:
            def execute(self, code, stdin, language_key):
                return {
                    "ok": True,
                    "code": code,
                    "stdin": stdin,
                    "steps": [],
                    "stdout": "hello from executor",
                    "error": None,
                    "analysis": {"structures": [], "intent_map": {}, "summary": ""},
                    "run_mode": "execution",
                    "execution": {"language_key": language_key, "ran": True},
                }

        service = TraceService(executor=FakeExecutor())
        result = service.visualize(
            "\n".join(
                [
                    "public class Main {",
                    "  public static void main(String[] args) {",
                    "    System.out.println(1);",
                    "  }",
                    "}",
                ]
            )
        )

        self.assertEqual(result["language"]["key"], "java")
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["stdout"], "hello from executor")
        self.assertEqual(result["run_mode"], "execution")

    def test_trace_service_returns_trace_capabilities(self):
        service = TraceService()
        result = service.visualize("print(1)")

        self.assertEqual(result["trace_capabilities"]["language_key"], "python")
        self.assertTrue(result["trace_capabilities"]["line_tracing"])


class TracingRegistryTest(unittest.TestCase):
    def test_marks_cpp_as_planned_and_hard(self):
        registry = TracingRegistry()

        capabilities = registry.describe("cpp")

        self.assertEqual(capabilities["status"], "planned")
        self.assertEqual(capabilities["difficulty"], "hard")
        self.assertFalse(capabilities["line_tracing"])

    def test_marks_csharp_as_experimental_line_tracer(self):
        registry = TracingRegistry()

        capabilities = registry.describe("csharp")

        self.assertEqual(capabilities["status"], "experimental")
        self.assertTrue(capabilities["line_tracing"])

    def test_marks_javascript_as_experimental_line_tracer(self):
        registry = TracingRegistry()

        capabilities = registry.describe("javascript")

        self.assertEqual(capabilities["status"], "experimental")
        self.assertTrue(capabilities["line_tracing"])


class JavaScriptTracingUnitTest(unittest.TestCase):
    def test_javascript_instrumentation_inserts_trace_calls(self):
        tracer = JavaScriptLineTracer()
        instrumented = tracer._instrument_code(
            "\n".join(
                [
                    "function solve() {",
                    "  let x = 1;",
                    "  x += 2;",
                    "  console.log(x);",
                    "}",
                    "solve();",
                ]
            )
        )

        self.assertIn("__traceStep(2);", instrumented)
        self.assertIn("__traceStep(3);", instrumented)
        self.assertIn("__traceStep(6);", instrumented)

    def test_javascript_tracer_reports_missing_runtime(self):
        tracer = JavaScriptLineTracer()
        result = tracer.trace("console.log(1);")

        if shutil.which("node"):
            self.assertIn("steps", result)
        else:
            self.assertEqual(result["error"], "Required runtime was not found: node.")


@unittest.skipUnless(shutil.which("dotnet"), "dotnet runtime not available")
class CSharpTracingIntegrationTest(unittest.TestCase):
    def test_csharp_generates_line_steps(self):
        service = TraceService()
        result = service.visualize(
            "\n".join(
                [
                    "using System;",
                    "class Program",
                    "{",
                    "    static void Main(string[] args)",
                    "    {",
                    "        int x = 1;",
                    "        x += 2;",
                    "        Console.WriteLine(x);",
                    "    }",
                    "}",
                ]
            )
        )

        self.assertEqual(result["language"]["key"], "csharp")
        self.assertEqual(result["run_mode"], "trace")
        self.assertGreaterEqual(len(result["steps"]), 3)
        self.assertTrue(any(step.get("line") == 6 for step in result["steps"]))
        snapshot_step = next(step for step in result["steps"] if step.get("line") == 6)
        self.assertIn("x", snapshot_step["globals"])
        self.assertEqual(snapshot_step["globals"]["x"]["repr"], "1")

    def test_csharp_builds_recursive_call_tree(self):
        service = TraceService()
        result = service.visualize(
            "\n".join(
                [
                    "using System;",
                    "class Program",
                    "{",
                    "    static void Main(string[] args)",
                    "    {",
                    "        Walk(2);",
                    "    }",
                    "",
                    "    static int Walk(int n)",
                    "    {",
                    "        if (n == 0)",
                    "        {",
                    "            return 0;",
                    "        }",
                    "        return Walk(n - 1) + 1;",
                    "    }",
                    "}",
                ]
            )
        )

        self.assertTrue(result["ok"])
        recursive_steps = [step for step in result["steps"] if len(step.get("stack", [])) >= 2]
        self.assertTrue(recursive_steps)
        self.assertTrue(any(step["event"] == "return" for step in result["steps"]))

        labels = []

        def walk(node):
            labels.append(node["label"])
            for child in node.get("children", []):
                walk(child)

        walk(result["steps"][-1]["call_tree"])
        self.assertTrue(any(label.startswith("Walk(") for label in labels))

        main_node = result["steps"][-1]["call_tree"]["children"][0]
        self.assertEqual(len(main_node["children"]), 1)
        self.assertEqual(main_node["children"][0]["label"], "Walk(n=2)")
        self.assertEqual(main_node["children"][0]["children"][0]["label"], "Walk(n=1)")
        self.assertEqual(main_node["children"][0]["children"][0]["children"][0]["label"], "Walk(n=0)")

    def test_csharp_records_return_values_in_call_tree(self):
        service = TraceService()
        result = service.visualize(
            "\n".join(
                [
                    "using System;",
                    "class Program",
                    "{",
                    "    static void Main(string[] args)",
                    "    {",
                    "        Console.WriteLine(Double(3));",
                    "    }",
                    "",
                    "    static int Double(int n)",
                    "    {",
                    "        return n * 2;",
                    "    }",
                    "}",
                ]
            )
        )

        self.assertTrue(result["ok"])
        double_node = result["steps"][-1]["call_tree"]["children"][0]["children"][0]
        self.assertEqual(double_node["return_value"], "6")

    def test_csharp_detects_array_structure(self):
        service = TraceService()
        result = service.visualize(
            "\n".join(
                [
                    "using System;",
                    "class Program",
                    "{",
                    "    static void Main(string[] args)",
                    "    {",
                    "        int[] arr = new int[4];",
                    "        arr[0] = 1;",
                    "        arr[1] = 3;",
                    "        Console.WriteLine(arr[1]);",
                    "    }",
                    "}",
                ]
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(any(item["kind"] == "array" and item["name"] == "arr" for item in result["analysis"]["structures"]))
        array_steps = [
            step
            for step in result["steps"]
            if step.get("structure") and step["structure"].get("kind") == "array"
        ]
        self.assertTrue(array_steps)
        self.assertEqual(array_steps[-1]["structure"]["name"], "arr")


if __name__ == "__main__":
    unittest.main()
