(function () {
  window.Visualizer = window.Visualizer || {};

  function runJavaScriptTrace(code, stdin = "") {
    const lineSources = code.split("\n");
    const traceEvents = [];
    const stdoutChunks = [];
    const inputLines = stdin ? stdin.split("\n") : [];
    let inputIndex = 0;

    function traceStep(line) {
      traceEvents.push({
        line,
        stdout: stdoutChunks.join(""),
      });
    }

    const tracedConsole = createTracedConsole(stdoutChunks);

    function input() {
      if (inputIndex >= inputLines.length) {
        throw new Error("No more browser-side input lines are available.");
      }
      const value = inputLines[inputIndex];
      inputIndex += 1;
      return value;
    }

    const browserProcess = createBrowserProcess(stdin, stdoutChunks);
    const browserModule = { exports: {} };
    const browserExports = browserModule.exports;
    const browserRequire = createBrowserRequire(stdin, browserProcess);

    const instrumented = instrumentJavaScript(code);
    let error = null;

    try {
      const runner = new Function(
        "__traceStep",
        "console",
        "input",
        "require",
        "process",
        "module",
        "exports",
        `
${instrumented}
`,
      );
      runner(
        traceStep,
        tracedConsole,
        input,
        browserRequire,
        browserProcess,
        browserModule,
        browserExports,
      );
    } catch (runtimeError) {
      error = runtimeError instanceof Error ? runtimeError.message : String(runtimeError);
    }

    const stdout = stdoutChunks.join("");
    const steps = buildSteps(lineSources, traceEvents, stdout, error);

    return {
      ok: error === null,
      code,
      stdin,
      steps,
      stdout,
      error,
      run_mode: "trace",
      language: {
        key: "javascript",
        label: "JavaScript",
        source: "manual",
        trace_supported: true,
      },
      trace_capabilities: {
        language_key: "javascript",
        line_tracing: true,
        variable_snapshots: false,
        call_tree: true,
        structure_detection: false,
        difficulty: "experimental",
        approach: "Runs directly in the browser with source instrumentation.",
        status: "experimental",
      },
      supported_languages: [],
      analysis: {
        structures: [],
        intent_map: {},
        summary: "",
      },
    };
  }

  function createTracedConsole(stdoutChunks) {
    function writeLine(args) {
      stdoutChunks.push(`${args.map(String).join(" ")}\n`);
    }

    return {
      log(...args) {
        writeLine(args);
      },
      info(...args) {
        writeLine(args);
      },
      warn(...args) {
        writeLine(args);
      },
      error(...args) {
        writeLine(args);
      },
    };
  }

  function instrumentJavaScript(code) {
    const lines = code.split("\n");
    const instrumented = [];
    let braceDepth = 0;

    lines.forEach((line, index) => {
      const lineNumber = index + 1;
      const stripped = line.trim();
      const indent = line.slice(0, line.length - line.trimStart().length);

      if (shouldInstrument(stripped, braceDepth)) {
        instrumented.push(`${indent}__traceStep(${lineNumber});`);
      }

      instrumented.push(line);

      braceDepth += countChar(line, "{");
      braceDepth -= countChar(line, "}");
      braceDepth = Math.max(braceDepth, 0);
    });

    return instrumented.join("\n");
  }

  function shouldInstrument(stripped) {
    if (!stripped) {
      return false;
    }
    if (stripped === "{" || stripped === "}") {
      return false;
    }
    if (stripped.startsWith("//")) {
      return false;
    }
    return true;
  }

  function countChar(text, char) {
    return [...text].filter((value) => value === char).length;
  }

  function createBrowserRequire(stdin, browserProcess) {
    return function require(moduleName) {
      if (moduleName === "fs" || moduleName === "node:fs") {
        return {
          readFileSync(path, encoding) {
            if (!isBrowserStdinPath(path)) {
              throw new Error(
                `Browser fs shim only supports stdin-style reads, received: ${String(path)}`,
              );
            }
            if (encoding && encoding !== "utf8" && encoding !== "utf-8") {
              throw new Error(`Unsupported encoding in browser fs shim: ${String(encoding)}`);
            }
            return stdin;
          },
        };
      }

      if (moduleName === "process") {
        return browserProcess;
      }

      throw new Error(`Browser JavaScript runner does not support require("${String(moduleName)}").`);
    };
  }

  function isBrowserStdinPath(path) {
    if (path === 0 || path === "0") {
      return true;
    }

    const normalized = String(path || "")
      .trim()
      .replaceAll("\\", "/")
      .toLowerCase();

    return [
      "/dev/stdin",
      "./dev/stdin",
      "../dev/stdin",
      "/dev/fd/0",
      "dev/stdin",
      "input.txt",
      "./input.txt",
      "../input.txt",
      "/input.txt",
    ].includes(normalized);
  }

  function createBrowserProcess(stdin, stdoutChunks) {
    let readOffset = 0;

    return {
      platform: "linux",
      argv: ["node", "/browser/main.js"],
      env: {},
      stdin: {
        read() {
          return stdin;
        },
        readline() {
          if (readOffset >= stdin.length) {
            return "";
          }

          const nextBreak = stdin.indexOf("\n", readOffset);
          if (nextBreak === -1) {
            const lastLine = stdin.slice(readOffset);
            readOffset = stdin.length;
            return lastLine;
          }

          const line = stdin.slice(readOffset, nextBreak + 1);
          readOffset = nextBreak + 1;
          return line;
        },
      },
      stdout: {
        write(chunk) {
          stdoutChunks.push(String(chunk));
        },
      },
      stderr: {
        write(chunk) {
          stdoutChunks.push(String(chunk));
        },
      },
      exit(code = 0) {
        if (code !== 0) {
          throw new Error(`Process exited with code ${code}`);
        }
      },
    };
  }

  function buildSteps(lineSources, traceEvents, stdout, error) {
    const steps = traceEvents.map((event, index) => ({
      index: index + 1,
      event: "line",
      line: event.line,
      line_source: lineSources[event.line - 1] || "",
      message: `Executed JavaScript line ${event.line}.`,
      stdout: event.stdout,
      stack: [
        {
          name: "main",
          label: "main()",
          line: event.line,
          active: true,
          node_id: "call-main",
          locals: {},
        },
      ],
      globals: {},
      call_tree: {
        id: "root",
        label: "module",
        status: "running",
        line: event.line,
        active: false,
        return_value: null,
        error: null,
        children: [
          {
            id: "call-main",
            label: "main()",
            status: "running",
            line: event.line,
            active: true,
            return_value: null,
            error: null,
            children: [],
          },
        ],
      },
      graph: null,
      structure: null,
      explanation: `Executed \`${(lineSources[event.line - 1] || "").trim()}\` on JavaScript line ${event.line}.`,
    }));

    steps.push({
      index: steps.length + 1,
      event: error ? "error" : "end",
      line: null,
      line_source: "",
      message: error || "Program execution finished.",
      stdout,
      stack: [],
      globals: {},
      call_tree: {
        id: "root",
        label: "module",
        status: error ? "exception" : "returned",
        line: null,
        active: false,
        return_value: null,
        error,
        children: [],
      },
      graph: null,
      structure: null,
      explanation: error || "Execution finished successfully.",
    });

    return steps;
  }

  window.Visualizer.browserTracers = {
    runJavaScriptTrace,
  };
})();
