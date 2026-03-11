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


if __name__ == "__main__":
    unittest.main()
