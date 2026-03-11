from __future__ import annotations

import shutil
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Any

from .runtime_locator import find_node_runtime


class CodeExecutionService:
    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def execute(self, code: str, stdin: str, language_key: str) -> dict[str, Any]:
        handler = getattr(self, f"_run_{language_key}", None)
        if handler is None:
            return self._missing_runtime_result(
                code,
                stdin,
                language_key,
                [],
                "Execution support is not wired for this language yet.",
            )
        return handler(code, stdin)

    def _run_cpp(self, code: str, stdin: str) -> dict[str, Any]:
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            return self._missing_runtime_result(code, stdin, "cpp", ["g++", "clang++", "cl"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.cpp"
            output_path = temp_path / "main.exe"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process(
                [compiler, str(source_path), "-std=c++17", "-O2", "-o", str(output_path)],
                temp_path,
            )
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "cpp",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "C++ compilation failed.",
                )

            run_result = self._run_process([str(output_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "cpp",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_java(self, code: str, stdin: str) -> dict[str, Any]:
        javac = shutil.which("javac")
        java = shutil.which("java")
        if javac is None or java is None:
            return self._missing_runtime_result(code, stdin, "java", ["javac", "java"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "Main.java"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process([javac, str(source_path)], temp_path)
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "java",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "Java compilation failed.",
                )

            run_result = self._run_process([java, "-cp", str(temp_path), "Main"], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "java",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_c(self, code: str, stdin: str) -> dict[str, Any]:
        compiler = shutil.which("gcc") or shutil.which("clang")
        if compiler is None:
            return self._missing_runtime_result(code, stdin, "c", ["gcc", "clang", "cl"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.c"
            output_path = temp_path / "main.exe"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process(
                [compiler, str(source_path), "-O2", "-o", str(output_path)],
                temp_path,
            )
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "c",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "C compilation failed.",
                )

            run_result = self._run_process([str(output_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "c",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_javascript(self, code: str, stdin: str) -> dict[str, Any]:
        node = find_node_runtime()
        if node is None:
            return self._missing_runtime_result(code, stdin, "javascript", ["node"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.js"
            source_path.write_text(code, encoding="utf-8")
            run_result = self._run_process([node, str(source_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "javascript",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_typescript(self, code: str, stdin: str) -> dict[str, Any]:
        node = find_node_runtime()
        npx = shutil.which("npx")
        if node is None or npx is None:
            return self._missing_runtime_result(code, stdin, "typescript", ["node", "npx", "tsc"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.ts"
            js_path = temp_path / "main.js"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process(
                [npx, "tsc", str(source_path), "--target", "es2020", "--module", "commonjs"],
                temp_path,
            )
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "typescript",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "TypeScript compilation failed.",
                )

            run_result = self._run_process([node, str(js_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "typescript",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_kotlin(self, code: str, stdin: str) -> dict[str, Any]:
        kotlinc = shutil.which("kotlinc")
        java = shutil.which("java")
        if kotlinc is None or java is None:
            return self._missing_runtime_result(code, stdin, "kotlin", ["kotlinc", "java"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "Main.kt"
            jar_path = temp_path / "main.jar"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process(
                [kotlinc, str(source_path), "-include-runtime", "-d", str(jar_path)],
                temp_path,
            )
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "kotlin",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "Kotlin compilation failed.",
                )

            run_result = self._run_process([java, "-jar", str(jar_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "kotlin",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_go(self, code: str, stdin: str) -> dict[str, Any]:
        go = shutil.which("go")
        if go is None:
            return self._missing_runtime_result(code, stdin, "go", ["go"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.go"
            source_path.write_text(code, encoding="utf-8")
            run_result = self._run_process([go, "run", str(source_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "go",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_rust(self, code: str, stdin: str) -> dict[str, Any]:
        rustc = shutil.which("rustc")
        if rustc is None:
            return self._missing_runtime_result(code, stdin, "rust", ["rustc"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "main.rs"
            output_path = temp_path / "main.exe"
            source_path.write_text(code, encoding="utf-8")

            compile_result = self._run_process([rustc, str(source_path), "-O", "-o", str(output_path)], temp_path)
            if compile_result.returncode != 0:
                return self._process_result(
                    code,
                    stdin,
                    "rust",
                    ok=False,
                    stdout=compile_result.stdout,
                    error=compile_result.stderr or "Rust compilation failed.",
                )

            run_result = self._run_process([str(output_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "rust",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_csharp(self, code: str, stdin: str) -> dict[str, Any]:
        dotnet = shutil.which("dotnet")
        if dotnet is None:
            return self._missing_runtime_result(code, stdin, "csharp", ["dotnet"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "Program.cs"
            project_path = temp_path / "Runner.csproj"
            source_path.write_text(code, encoding="utf-8")
            project_path.write_text(
                "\n".join(
                    [
                        '<Project Sdk="Microsoft.NET.Sdk">',
                        "  <PropertyGroup>",
                        "    <OutputType>Exe</OutputType>",
                        "    <TargetFramework>net6.0</TargetFramework>",
                        "    <ImplicitUsings>enable</ImplicitUsings>",
                        "    <Nullable>enable</Nullable>",
                        "  </PropertyGroup>",
                        "</Project>",
                    ]
                ),
                encoding="utf-8",
            )

            run_result = self._run_process([dotnet, "run", "--project", str(project_path)], temp_path, stdin)
            return self._process_result(
                code,
                stdin,
                "csharp",
                ok=run_result.returncode == 0,
                stdout=run_result.stdout,
                error=run_result.stderr if run_result.returncode != 0 else None,
            )

    def _run_process(
        self,
        command: list[str],
        cwd: Path,
        stdin: str = "",
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
                env={
                    **os.environ,
                    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                    "DOTNET_NOLOGO": "1",
                    "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                },
                check=False,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                command,
                124,
                stdout="",
                stderr=f"Execution exceeded {self.timeout_seconds:.1f} seconds.",
            )

    def _missing_runtime_result(
        self,
        code: str,
        stdin: str,
        language_key: str,
        runtime_names: list[str],
        extra_message: str | None = None,
    ) -> dict[str, Any]:
        runtime_text = ", ".join(runtime_names) if runtime_names else "runtime"
        message = extra_message or f"Required runtime was not found: {runtime_text}."
        return self._process_result(
            code,
            stdin,
            language_key,
            ok=False,
            stdout="",
            error=message,
        )

    def _process_result(
        self,
        code: str,
        stdin: str,
        language_key: str,
        *,
        ok: bool,
        stdout: str,
        error: str | None,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "code": code,
            "stdin": stdin,
            "steps": [],
            "stdout": stdout,
            "error": error,
            "analysis": {"structures": [], "intent_map": {}, "summary": ""},
            "run_mode": "execution",
            "execution": {
                "language_key": language_key,
                "ran": ok,
            },
        }
