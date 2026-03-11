import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from visualizer.tracing.native_runtime import NativeExecutionTracer


class NativeExecutionTracerTest(unittest.TestCase):
    def setUp(self):
        self.tracer = NativeExecutionTracer()

    def test_runs_java_and_returns_shared_schema(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "public class Main {",
                    "    public static void main(String[] args) {",
                    "        int[] arr = {3, 1, 2};",
                    "        java.util.Arrays.sort(arr);",
                    '        System.out.println(arr[0] + "," + arr[2]);',
                    "    }",
                    "}",
                ]
            ),
            language="java",
        )

        self.assertTrue(result["ok"], result.get("display_error"))
        self.assertEqual(result["language"], "java")
        self.assertTrue(result["steps"])
        self.assertEqual(result["stdout"].strip(), "1,3")
        self.assertTrue(result["analysis"]["intents"]["sorting"])

    def test_reports_java_compile_error(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "public class Main {",
                    "    public static void main(String[] args) {",
                    "        System.out.println(\"oops\")",
                    "    }",
                    "}",
                ]
            ),
            language="java",
        )

        self.assertFalse(result["ok"])
        self.assertIn("compile", result["display_error"].lower())

    @unittest.skipUnless(
        shutil.which("clang++")
        or shutil.which("g++")
        or Path("C:/Program Files/LLVM/bin/clang++.exe").exists(),
        "No C++ compiler installed",
    )
    def test_runs_cpp_and_detects_graph_structure(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "#include <algorithm>",
                    "#include <iostream>",
                    "#include <vector>",
                    "using namespace std;",
                    "int main() {",
                    "    vector<vector<int>> graph = {{1, 2}, {2}, {}};",
                    "    vector<int> values = {4, 2, 3};",
                    "    sort(values.begin(), values.end());",
                    '    cout << values[0] << " " << values[2] << "\\n";',
                    "    return 0;",
                    "}",
                ]
            ),
            language="cpp",
        )

        self.assertTrue(result["ok"], result.get("display_error"))
        self.assertEqual(result["language"], "cpp")
        self.assertEqual(result["stdout"].strip(), "2 4")
        self.assertTrue(result["steps"])
        self.assertIsNotNone(result["steps"][-1]["graph"])

    def test_precise_java_runtime_updates_scalars(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "public class Main {",
                    "    public static void main(String[] args) {",
                    "        int x = 1;",
                    "        x += 2;",
                    "        System.out.println(x);",
                    "    }",
                    "}",
                ]
            ),
            language="java",
        )

        self.assertTrue(result["ok"], result.get("display_error"))
        line_to_x = {
            step["line"]: step["globals"]["x"]["value"]
            for step in result["steps"]
            if step.get("globals", {}).get("x")
        }
        self.assertEqual(line_to_x.get(4), 1)
        self.assertEqual(line_to_x.get(5), 3)

    def test_static_java_call_tree_keeps_recursive_hierarchy(self):
        code = "\n".join(
            [
                "public class Main {",
                "    public static void main(String[] args) {",
                "        hanoi(3, 1, 2, 3);",
                "    }",
                "",
                "    static void hanoi(int n, int fr, int mid, int to) {",
                "        if (n == 1) {",
                "            return;",
                "        }",
                "        hanoi(n - 1, fr, to, mid);",
                "        hanoi(n - 1, mid, fr, to);",
                "    }",
                "}",
            ]
        )

        with patch.object(self.tracer, "_trace_precise", return_value=None):
            with patch.object(
                self.tracer,
                "_compile_and_run",
                return_value={"stdout": "", "error": None, "display_error": None},
            ):
                result = self.tracer.trace(code, language="java")

        self.assertTrue(result["ok"], result.get("display_error"))
        final_tree = result["steps"][-1]["call_tree"]
        main_node = final_tree["children"][0]
        hanoi_node = main_node["children"][0]
        self.assertIn("hanoi(n=3, fr=1, mid=2", hanoi_node["label"])
        self.assertEqual(len(hanoi_node["children"]), 2)
        self.assertIn("n=3 - 1", hanoi_node["children"][0]["label"])
        self.assertEqual(len(hanoi_node["children"][0]["children"]), 2)

    @unittest.skipUnless(
        shutil.which("clang++")
        or shutil.which("g++")
        or Path("C:/Program Files/LLVM/bin/clang++.exe").exists(),
        "No C++ compiler installed",
    )
    def test_precise_cpp_runtime_updates_scalars(self):
        result = self.tracer.trace(
            "\n".join(
                [
                    "#include <iostream>",
                    "int main() {",
                    "    int x = 1;",
                    "    x += 2;",
                    "    std::cout << x << std::endl;",
                    "    return 0;",
                    "}",
                ]
            ),
            language="cpp",
        )

        self.assertTrue(result["ok"], result.get("display_error"))
        line_to_x = {
            step["line"]: step["globals"]["x"]["value"]
            for step in result["steps"]
            if step.get("globals", {}).get("x")
        }
        self.assertEqual(line_to_x.get(3), 0)
        self.assertEqual(line_to_x.get(4), 1)
        self.assertEqual(line_to_x.get(5), 3)


if __name__ == "__main__":
    unittest.main()
