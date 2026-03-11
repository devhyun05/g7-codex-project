from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageSpec:
    key: str
    label: str
    trace_supported: bool = False


SUPPORTED_LANGUAGES = [
    LanguageSpec("python", "Python", trace_supported=True),
    LanguageSpec("cpp", "C++"),
    LanguageSpec("java", "Java"),
    LanguageSpec("c", "C"),
    LanguageSpec("javascript", "JavaScript", trace_supported=True),
    LanguageSpec("typescript", "TypeScript"),
    LanguageSpec("kotlin", "Kotlin"),
    LanguageSpec("go", "Go"),
    LanguageSpec("rust", "Rust"),
    LanguageSpec("csharp", "C#", trace_supported=True),
]

LANGUAGE_BY_KEY = {language.key: language for language in SUPPORTED_LANGUAGES}
UNKNOWN_LANGUAGE = LanguageSpec("unknown", "Unknown")


class LanguageDetector:
    def detect(self, code: str, requested: str = "auto") -> dict[str, object]:
        normalized_requested = (requested or "auto").strip().lower()
        if normalized_requested in LANGUAGE_BY_KEY:
            language = LANGUAGE_BY_KEY[normalized_requested]
            return self._build_result(language, source="manual")

        scores = self._score_languages(code)
        language = max(
            SUPPORTED_LANGUAGES,
            key=lambda item: (scores.get(item.key, 0), item.label),
        )
        if scores.get(language.key, 0) <= 0:
            return self._build_result(UNKNOWN_LANGUAGE, source="auto")
        return self._build_result(language, source="auto")

    def options(self) -> list[dict[str, object]]:
        return [
            {
                "key": "auto",
                "label": "Auto Detect",
                "trace_supported": False,
            },
            *[
                {
                    "key": item.key,
                    "label": item.label,
                    "trace_supported": item.trace_supported,
                }
                for item in SUPPORTED_LANGUAGES
            ],
        ]

    def _build_result(self, language: LanguageSpec, source: str) -> dict[str, object]:
        return {
            "key": language.key,
            "label": language.label,
            "source": source,
            "trace_supported": language.trace_supported,
        }

    def _score_languages(self, code: str) -> dict[str, int]:
        text = code or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        scores = {language.key: 0 for language in SUPPORTED_LANGUAGES}

        def add(language_key: str, points: int, *needles: str) -> None:
            if any(needle in text for needle in needles):
                scores[language_key] += points

        add("python", 8, "def ", "if __name__ == \"__main__\":", "elif ", "print(")
        add("python", 6, "from collections import", "import math", "for _ in range(")
        if any(line.endswith(":") for line in lines):
            scores["python"] += 5

        add("cpp", 12, "#include <bits/stdc++.h>", "using namespace std;", "cout <<", "cin >>")
        add("cpp", 7, "vector<", "pair<", "ios::sync_with_stdio(false)", "std::")
        add("cpp", 5, "int main()", "long long")

        add("c", 12, "#include <stdio.h>", "scanf(", "printf(")
        add("c", 7, "#include <stdlib.h>", "malloc(", "free(", "sizeof(")
        add("c", 5, "int main(void)", "char *", "struct ")

        add("java", 12, "public class", "class Main", "static void main(String[] args)")
        add("java", 9, "System.out.println", "BufferedReader", "StringTokenizer", "ArrayList<")
        add("java", 5, "import java.", "throws Exception")

        add("javascript", 10, "console.log(", "function ", "=>", "require(")
        add("javascript", 6, "let ", "const ", "process.stdin", "module.exports")

        add("typescript", 10, "interface ", "type ", "implements ", "readonly ")
        add("typescript", 8, ": number", ": string", ": boolean", "Array<number>")
        add("typescript", 5, " as ", "<T>")

        add("kotlin", 12, "fun main()", "readLine()", "mutableListOf(", "ArrayDeque<")
        add("kotlin", 8, "val ", "var ", "println(", "when (")
        add("kotlin", 5, "data class ", "?.", "!!")

        add("go", 12, "package main", "func main()", "fmt.Println(", "fmt.Fscan(")
        add("go", 8, ":=", "bufio.NewReader", "make([]", "range ")
        add("go", 5, "var ", "func solution(")

        add("rust", 12, "fn main()", "println!(", "let mut ", "Vec<")
        add("rust", 8, "HashMap<", "usize", "stdin()", "collect::<")
        add("rust", 5, "match ", "Some(", "None")

        add("csharp", 12, "using System;", "Console.WriteLine(", "static void Main(")
        add("csharp", 8, "namespace ", "class Program", "List<int>", "string[] args")
        add("csharp", 5, "public static", "new List<")

        if "console.log(" in text or "process.stdin" in text:
            scores["typescript"] -= 2
        if "interface " in text or ": number" in text:
            scores["javascript"] -= 3
        if "#include <stdio.h>" in text:
            scores["cpp"] -= 3
        if "#include <bits/stdc++.h>" in text or "using namespace std;" in text:
            scores["c"] -= 5
        if "fun main()" in text:
            scores["javascript"] -= 2
            scores["typescript"] -= 2

        return scores
