(function () {
  window.Visualizer = window.Visualizer || {};

  const MAX_ITEMS = 8;
  const MAX_DEPTH = 3;
  const MAX_REPR_LENGTH = 96;
  const TRACE_UNAVAILABLE = "__TRACE_UNAVAILABLE__";

  function runJavaScriptTrace(code, stdin = "") {
    const lineSources = code.split("\n");
    const stdoutChunks = [];
    const inputLines = stdin ? stdin.split("\n") : [];
    const analysis = analyzeJavaScript(code);
    const steps = [];
    let inputIndex = 0;
    let error = null;

    function traceStep(line, rawSnapshot, meta = {}) {
      const callFrames = captureCallFrames();
      const snapshot = buildSnapshot(rawSnapshot, meta);
      const structure = detectStructure(snapshot, rawSnapshot, callFrames);
      const stack = buildStackFrames(callFrames, snapshot.locals);

      steps.push({
        index: steps.length + 1,
        event: "line",
        line,
        line_source: lineSources[line - 1] || "",
        message: buildMessage(callFrames, line),
        stdout: stdoutChunks.join(""),
        stack,
        globals: snapshot.globals,
        call_tree: buildCallTree(stack),
        graph: null,
        structure,
        explanation: buildExplanation(lineSources[line - 1] || "", callFrames, structure),
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

    const instrumented = instrumentJavaScript(code, analysis.linePlans);

    try {
      const runner = new Function(
        "__traceStep",
        "console",
        "input",
        "require",
        "process",
        "module",
        "exports",
        instrumented,
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
    steps.push({
      index: steps.length + 1,
      event: error ? "error" : "end",
      line: null,
      line_source: "",
      message: error || "Program execution finished.",
      stdout,
      stack: [],
      globals: findLastGlobals(steps),
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
      structure: findLastStructure(steps),
      explanation: error || "Execution finished successfully.",
    });

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
        variable_snapshots: true,
        call_tree: true,
        structure_detection: true,
        difficulty: "experimental",
        approach: "Runs directly in the browser with source instrumentation and lightweight scope snapshots.",
        status: "experimental",
      },
      supported_languages: [],
      analysis: {
        structures: analysis.structures,
        intent_map: {},
        summary: analysis.summary,
      },
    };
  }

  function analyzeJavaScript(code) {
    const lines = code.split("\n");
    const linePlans = [];
    const structures = [];
    const globalScope = {
      kind: "global",
      names: [],
      depth: 0,
      functionName: "module",
    };
    const functionScopes = [];
    let braceDepth = 0;

    lines.forEach((line, index) => {
      while (functionScopes.length && braceDepth < functionScopes[functionScopes.length - 1].depth) {
        functionScopes.pop();
      }

      const lineNumber = index + 1;
      const currentFunctionScope = functionScopes.length ? functionScopes[functionScopes.length - 1] : null;
      linePlans.push({
        globals: [...globalScope.names],
        locals: currentFunctionScope ? [...currentFunctionScope.names] : [],
      });

      const declaredNames = extractDeclaredNames(line);
      const functionInfo = extractFunctionInfo(line);

      if (functionInfo && functionInfo.name && !globalScope.names.includes(functionInfo.name) && !currentFunctionScope) {
        globalScope.names.push(functionInfo.name);
      } else if (functionInfo && functionInfo.name && currentFunctionScope && !currentFunctionScope.names.includes(functionInfo.name)) {
        currentFunctionScope.names.push(functionInfo.name);
      }

      declaredNames.forEach((name) => {
        if (!name) {
          return;
        }
        const targetScope = currentFunctionScope || globalScope;
        if (!targetScope.names.includes(name)) {
          targetScope.names.push(name);
        }
        const kind = detectStructureKind(name);
        if (kind && !structures.some((item) => item.name === name && item.kind === kind)) {
          structures.push({
            kind,
            name,
            reason: `The variable name "${name}" looks like a ${kind}.`,
            line: lineNumber,
          });
        }
      });

      const opens = countChar(line, "{");
      const closes = countChar(line, "}");
      braceDepth += opens - closes;

      if (functionInfo && functionInfo.hasBlock) {
        const functionName = functionInfo.name || "anonymous";
        functionScopes.push({
          kind: "function",
          names: [...functionInfo.params],
          depth: Math.max(braceDepth, 0),
          functionName,
        });
      }

      while (functionScopes.length && braceDepth < functionScopes[functionScopes.length - 1].depth) {
        functionScopes.pop();
      }
    });

    return {
      linePlans,
      structures,
      summary: structures.length
        ? structures.map((item) => `${item.name} (${item.kind})`).join(", ")
        : "No special JavaScript structure pattern was detected.",
    };
  }

  function instrumentJavaScript(code, linePlans) {
    const lines = code.split("\n");
    const helperLines = [
      "const __TRACE_UNAVAILABLE__ = '__TRACE_UNAVAILABLE__';",
      "function __captureValue(getter) {",
      "  try {",
      "    return getter();",
      "  } catch (error) {",
      "    return __TRACE_UNAVAILABLE__;",
      "  }",
      "}",
      "",
    ];
    const instrumented = [];

    lines.forEach((line, index) => {
      const stripped = line.trim();
      const indent = line.slice(0, line.length - line.trimStart().length);
      const lineNumber = index + 1;
      const plan = linePlans[index] || { globals: [], locals: [] };

      if (shouldInstrument(stripped)) {
        instrumented.push(buildTraceStatement(lineNumber, plan, indent));
      }

      instrumented.push(line);
    });

    return `${helperLines.join("\n")}${instrumented.join("\n")}`;
  }

  function buildTraceStatement(lineNumber, plan, indent) {
    const names = [...new Set([...(plan.globals || []), ...(plan.locals || [])])];
    const fields = names.map(
      (name) => `${JSON.stringify(name)}: __captureValue(() => ${name})`,
    );
    const snapshotObject = fields.length ? `{\n${indent}  ${fields.join(`,\n${indent}  `)}\n${indent}}` : "{}";
    const meta = {
      globals: plan.globals || [],
      locals: plan.locals || [],
    };

    return `${indent}__traceStep(${lineNumber}, ${snapshotObject}, ${JSON.stringify(meta)});`;
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
    if (
      stripped.startsWith("else")
      || stripped.startsWith("catch")
      || stripped.startsWith("finally")
      || stripped.startsWith("case ")
      || stripped.startsWith("default:")
    ) {
      return false;
    }
    return true;
  }

  function buildSnapshot(rawSnapshot, meta) {
    const globals = {};
    const locals = {};
    const allValues = rawSnapshot || {};

    (meta.globals || []).forEach((name) => {
      if (!Object.prototype.hasOwnProperty.call(allValues, name)) {
        return;
      }
      if (allValues[name] === TRACE_UNAVAILABLE) {
        return;
      }
      globals[name] = serializeValue(allValues[name], 0, new Set());
    });

    (meta.locals || []).forEach((name) => {
      if (!Object.prototype.hasOwnProperty.call(allValues, name)) {
        return;
      }
      if (allValues[name] === TRACE_UNAVAILABLE) {
        return;
      }
      locals[name] = serializeValue(allValues[name], 0, new Set());
    });

    return { globals, locals };
  }

  function buildStackFrames(callFrames, locals) {
    if (!callFrames.length) {
      return [];
    }

    return callFrames.map((frameName, index) => {
      const nodeId = buildNodeId(callFrames.slice(0, index + 1));
      return {
        name: frameName,
        label: formatCallLabel(frameName, index === callFrames.length - 1 ? locals : {}),
        line: null,
        active: index === callFrames.length - 1,
        node_id: nodeId,
        locals: index === callFrames.length - 1 ? locals : {},
      };
    });
  }

  function buildCallTree(stack) {
    const root = {
      id: "root",
      label: "module",
      status: "running",
      line: null,
      active: false,
      return_value: null,
      error: null,
      children: [],
    };

    let cursor = root;
    stack.forEach((frame, index) => {
      const child = {
        id: frame.node_id,
        label: frame.label,
        status: index === stack.length - 1 ? "running" : "active",
        line: frame.line,
        active: Boolean(frame.active),
        return_value: null,
        error: null,
        locals: frame.locals || {},
        children: [],
      };
      cursor.children.push(child);
      cursor = child;
    });

    return root;
  }

  function detectStructure(snapshot, rawSnapshot, callFrames) {
    const mergedNames = [
      ...Object.keys(snapshot.locals || {}),
      ...Object.keys(snapshot.globals || {}),
    ];
    const mergedRaw = rawSnapshot || {};

    const stackName = mergedNames.find((name) => /stack|history/i.test(name) && Array.isArray(mergedRaw[name]));
    if (stackName) {
      const items = mergedRaw[stackName].slice(-MAX_ITEMS).map((item) => shortRepr(item));
      return {
        kind: "stack",
        name: stackName,
        items,
        top_index: items.length ? items.length - 1 : null,
      };
    }

    const queueName = mergedNames.find((name) => /queue|deque|tasks/i.test(name) && Array.isArray(mergedRaw[name]));
    if (queueName) {
      const items = mergedRaw[queueName].slice(0, MAX_ITEMS).map((item) => shortRepr(item));
      return {
        kind: "queue",
        name: queueName,
        items,
        front_index: items.length ? 0 : null,
        back_index: items.length ? items.length - 1 : null,
      };
    }

    const arrayName = mergedNames.find((name) => Array.isArray(mergedRaw[name]));
    if (arrayName) {
      return {
        kind: "array",
        name: arrayName,
        items: mergedRaw[arrayName].slice(0, MAX_ITEMS).map((item) => shortRepr(item)),
      };
    }

    if (callFrames.length > 1) {
      return null;
    }

    return null;
  }

  function buildMessage(callFrames, line) {
    const current = callFrames.length ? callFrames[callFrames.length - 1] : "module";
    return `${current} is executing line ${line}.`;
  }

  function buildExplanation(lineSource, callFrames, structure) {
    const parts = [];
    if (lineSource.trim()) {
      parts.push(`Executing \`${lineSource.trim()}\`.`);
    }
    if (callFrames.length) {
      parts.push(`Active frame: ${callFrames[callFrames.length - 1]}.`);
    }
    if (structure) {
      parts.push(`Detected ${structure.kind} view for ${structure.name}.`);
    }
    return parts.join(" ") || "JavaScript execution step.";
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

  function captureCallFrames() {
    const error = new Error();
    const stackText = String(error.stack || "");
    const lines = stackText.split("\n").slice(1);
    const frames = [];

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (
        !trimmed
        || trimmed.includes("traceStep")
        || trimmed.includes("__traceStep")
        || trimmed.includes("runJavaScriptTrace")
        || trimmed.includes("new Function")
      ) {
        return;
      }

      let name = "";
      const atMatch = trimmed.match(/^at\s+([^\s(]+)/);
      const firefoxMatch = trimmed.match(/^([^@]+)@/);
      if (atMatch) {
        name = atMatch[1];
      } else if (firefoxMatch) {
        name = firefoxMatch[1];
      }

      if (!name || name === "eval" || name === "<anonymous>") {
        return;
      }

      frames.push(name.replace(/^Object\./, ""));
    });

    return frames.reverse();
  }

  function serializeValue(value, depth, seen) {
    if (value === null || value === undefined) {
      return {
        type: String(value),
        repr: String(value),
        value,
      };
    }

    const valueType = typeof value;
    if (valueType === "string" || valueType === "number" || valueType === "boolean" || valueType === "bigint") {
      return {
        type: value.constructor && value.constructor.name ? value.constructor.name : valueType,
        repr: shortRepr(value),
        value,
      };
    }

    if (valueType === "function") {
      return {
        type: "function",
        repr: `<function ${value.name || "anonymous"}>`,
      };
    }

    if (depth >= MAX_DEPTH) {
      return {
        type: getTypeName(value),
        repr: shortRepr(value),
      };
    }

    const objectId = value;
    if (seen.has(objectId)) {
      return {
        type: "ref",
        repr: "<recursive reference>",
      };
    }

    const nextSeen = new Set(seen);
    nextSeen.add(objectId);

    if (Array.isArray(value)) {
      return {
        type: "Array",
        repr: shortRepr(value),
        items: value.slice(0, MAX_ITEMS).map((item) => serializeValue(item, depth + 1, nextSeen)),
        truncated: value.length > MAX_ITEMS,
      };
    }

    const entries = Object.entries(value);
    return {
      type: getTypeName(value),
      repr: shortRepr(value),
      attributes: entries.slice(0, MAX_ITEMS).map(([name, item]) => ({
        name,
        value: serializeValue(item, depth + 1, nextSeen),
      })),
      truncated: entries.length > MAX_ITEMS,
    };
  }

  function shortRepr(value) {
    try {
      if (typeof value === "string") {
        return JSON.stringify(value).length > MAX_REPR_LENGTH
          ? `${JSON.stringify(value).slice(0, MAX_REPR_LENGTH - 3)}...`
          : JSON.stringify(value);
      }

      const text = Array.isArray(value)
        ? `[${value.slice(0, MAX_ITEMS).map((item) => shortRepr(item)).join(", ")}${value.length > MAX_ITEMS ? ", ..." : ""}]`
        : String(value);
      return text.length > MAX_REPR_LENGTH ? `${text.slice(0, MAX_REPR_LENGTH - 3)}...` : text;
    } catch (error) {
      return `<${getTypeName(value)}>`;
    }
  }

  function getTypeName(value) {
    if (!value || !value.constructor || !value.constructor.name) {
      return typeof value;
    }
    return value.constructor.name;
  }

  function extractDeclaredNames(line) {
    const declarations = [];
    const declarationRegex = /\b(?:const|let|var)\s+([^;]+)/g;
    let match;
    while ((match = declarationRegex.exec(line)) !== null) {
      const names = match[1]
        .split(",")
        .map((part) => part.split("=")[0].trim())
        .filter(Boolean)
        .filter((name) => /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name));
      declarations.push(...names);
    }
    return declarations;
  }

  function extractFunctionInfo(line) {
    const functionDeclaration = line.match(/\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)?\s*\(([^)]*)\)\s*\{/);
    if (functionDeclaration) {
      return {
        name: functionDeclaration[1] || "anonymous",
        params: extractParams(functionDeclaration[2]),
        hasBlock: true,
      };
    }

    const assignedFunction = line.match(
      /\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*function\s*\(([^)]*)\)\s*\{/,
    );
    if (assignedFunction) {
      return {
        name: assignedFunction[1],
        params: extractParams(assignedFunction[2]),
        hasBlock: true,
      };
    }

    const assignedArrow = line.match(
      /\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*\(([^)]*)\)\s*=>\s*\{/,
    );
    if (assignedArrow) {
      return {
        name: assignedArrow[1],
        params: extractParams(assignedArrow[2]),
        hasBlock: true,
      };
    }

    const simpleArrow = line.match(
      /\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*\{/,
    );
    if (simpleArrow) {
      return {
        name: simpleArrow[1],
        params: [simpleArrow[2]],
        hasBlock: true,
      };
    }

    return null;
  }

  function extractParams(rawParams) {
    return String(rawParams || "")
      .split(",")
      .map((part) => part.trim())
      .map((part) => part.replace(/=.*$/, "").replace(/^\.\.\./, "").trim())
      .filter((name) => /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name));
  }

  function detectStructureKind(name) {
    if (/stack|history/i.test(name)) {
      return "stack";
    }
    if (/queue|deque|tasks/i.test(name)) {
      return "queue";
    }
    if (/arr|list|nums|values|items/i.test(name)) {
      return "array";
    }
    return null;
  }

  function countChar(text, char) {
    return [...text].filter((value) => value === char).length;
  }

  function formatCallLabel(name, locals) {
    const entries = Object.entries(locals || {}).slice(0, 3);
    if (!entries.length) {
      return `${name}()`;
    }
    return `${name}(${entries.map(([key, value]) => `${key}=${value.repr || ""}`).join(", ")})`;
  }

  function buildNodeId(path) {
    return `call-${path.join("-")}`;
  }

  function findLastGlobals(steps) {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      if (steps[index] && steps[index].globals) {
        return steps[index].globals;
      }
    }
    return {};
  }

  function findLastStructure(steps) {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      if (steps[index] && steps[index].structure) {
        return steps[index].structure;
      }
    }
    return null;
  }

  window.Visualizer.browserTracers = {
    runJavaScriptTrace,
  };
})();
