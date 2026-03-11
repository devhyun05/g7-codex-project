const sampleCode = `graph = {
    1: [2, 3],
    2: [4, 5],
    3: [6],
    4: [],
    5: [],
    6: []
}

visited = set()

def dfs(node):
    visited.add(node)
    print("visit", node)
    for nxt in graph[node]:
        if nxt not in visited:
            dfs(nxt)

dfs(1)
`;

const state = {
  code: sampleCode,
  steps: [],
  currentIndex: 0,
  timer: null,
  primaryView: "summary",
  detailsExpanded: {
    variables: false,
    stdout: false,
  },
  runResult: {
    ok: true,
    error: null,
    stdout: "",
  },
};

const codeInput = document.getElementById("code-input");
const runButton = document.getElementById("run-button");
const loadExampleButton = document.getElementById("load-example");
const prevStepButton = document.getElementById("prev-step");
const playStepButton = document.getElementById("play-step");
const nextStepButton = document.getElementById("next-step");
const stepSlider = document.getElementById("step-slider");
const stepCounter = document.getElementById("step-counter");
const eventLabel = document.getElementById("event-label");
const messageLabel = document.getElementById("message-label");
const feedbackBanner = document.getElementById("feedback-banner");
const editorWrap = document.getElementById("editor-wrap");
const editCodeButton = document.getElementById("edit-code-button");
const codeViewer = document.getElementById("code-viewer");
const functionPill = document.getElementById("function-pill");
const linePill = document.getElementById("line-pill");
const stageTitle = document.getElementById("stage-title");
const stageSubtitle = document.getElementById("stage-subtitle");
const primaryViewLabel = document.getElementById("primary-view-label");
const primaryStage = document.getElementById("primary-stage");
const variablesDetails = document.getElementById("variables-details");
const stdoutDetails = document.getElementById("stdout-details");
const stackView = document.getElementById("stack-view");
const globalsView = document.getElementById("globals-view");
const stdoutView = document.getElementById("stdout-view");

document.addEventListener("DOMContentLoaded", () => {
  codeInput.value = state.code;
  variablesDetails.addEventListener("toggle", () => {
    state.detailsExpanded.variables = variablesDetails.open;
  });
  stdoutDetails.addEventListener("toggle", () => {
    state.detailsExpanded.stdout = stdoutDetails.open;
  });
  renderIdleState();
});

loadExampleButton.addEventListener("click", () => {
  stopPlayback();
  codeInput.value = sampleCode;
  hideBanner();
  renderIdleState();
});

runButton.addEventListener("click", runVisualization);
editCodeButton.addEventListener("click", () => {
  hideBanner();
  renderIdleState();
});
prevStepButton.addEventListener("click", () => moveStep(-1));
nextStepButton.addEventListener("click", () => moveStep(1));
playStepButton.addEventListener("click", togglePlayback);

stepSlider.addEventListener("input", (event) => {
  state.currentIndex = Number(event.target.value);
  renderTraceState();
});

async function runVisualization() {
  stopPlayback();
  const code = codeInput.value;

  if (!code.trim()) {
    showBanner("시각화할 코드를 입력하세요.");
    return;
  }

  runButton.disabled = true;
  showBanner("trace를 생성하는 중입니다...", "success");

  try {
    const response = await fetch("/api/visualize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    const payload = await response.json();

    state.code = payload.code || code;
    state.steps = payload.steps || [];
    state.currentIndex = 0;
    state.runResult = {
      ok: Boolean(payload.ok),
      error: payload.error || null,
      stdout: payload.stdout || "",
    };
    state.detailsExpanded = {
      variables: false,
      stdout: !payload.ok,
    };

    configureControls();
    syncDetails();
    renderTraceState();

    if (payload.ok) {
      showBanner(
        `총 ${payload.steps.length}개의 step을 생성했습니다. 핵심 흐름은 오른쪽 시각화에 먼저 표시됩니다.`,
        "success",
      );
    } else {
      showBanner(payload.error || "실행 중 오류가 발생했습니다.");
    }
  } catch (error) {
    renderIdleState();
    showBanner(error.message || "요청 처리에 실패했습니다.");
  } finally {
    runButton.disabled = false;
  }
}

function configureControls() {
  const hasSteps = state.steps.length > 0;
  prevStepButton.disabled = !hasSteps;
  playStepButton.disabled = !hasSteps;
  nextStepButton.disabled = !hasSteps;
  stepSlider.disabled = !hasSteps;
  stepSlider.min = 0;
  stepSlider.max = hasSteps ? String(state.steps.length - 1) : "0";
  stepSlider.value = "0";
}

function moveStep(direction) {
  if (!state.steps.length) {
    return;
  }

  const nextIndex = Math.min(
    state.steps.length - 1,
    Math.max(0, state.currentIndex + direction),
  );
  state.currentIndex = nextIndex;
  renderTraceState();
}

function togglePlayback() {
  if (state.timer) {
    stopPlayback();
    return;
  }

  if (!state.steps.length) {
    return;
  }

  if (state.currentIndex >= state.steps.length - 1) {
    state.currentIndex = 0;
    renderTraceState();
  }

  playStepButton.textContent = "일시정지";
  state.timer = window.setInterval(() => {
    if (state.currentIndex >= state.steps.length - 1) {
      stopPlayback();
      return;
    }
    state.currentIndex += 1;
    renderTraceState();
  }, 900);
}

function stopPlayback() {
  if (state.timer) {
    window.clearInterval(state.timer);
    state.timer = null;
  }
  playStepButton.textContent = "재생";
}

function renderIdleState() {
  stopPlayback();
  state.steps = [];
  state.currentIndex = 0;
  state.primaryView = "summary";
  state.runResult = {
    ok: true,
    error: null,
    stdout: "",
  };
  state.detailsExpanded = {
    variables: false,
    stdout: false,
  };

  setInterfaceMode("edit");
  configureControls();
  syncDetails();
  updateHeaderMeta({
    stepText: "0 / 0",
    functionText: "module",
    lineText: "-",
    eventText: "대기 중",
    messageText: "코드를 실행하면 핵심 흐름만 먼저 보여줍니다.",
  });

  codeViewer.className = "code-viewer empty-state hidden";
  codeViewer.textContent = "아직 실행 기록이 없습니다.";

  stageTitle.textContent = "주 시각화";
  stageSubtitle.textContent =
    "그래프가 있으면 그래프를, 재귀가 있으면 호출 트리를 먼저 보여줍니다.";
  primaryViewLabel.textContent = "SUMMARY";
  primaryStage.className = "visual-stage empty-state";
  primaryStage.textContent = "실행 결과가 여기에 표시됩니다.";

  renderVariables(null);
  renderStdout("");
}

function renderTraceState() {
  setInterfaceMode("trace");

  const step = getCurrentStep();
  const activeFrame = getActiveFrame(step);
  const stepText = state.steps.length
    ? `${state.currentIndex + 1} / ${state.steps.length}`
    : "0 / 0";
  const eventText = step ? formatEvent(step.event) : state.runResult.ok ? "end" : "error";
  const messageText =
    (step && step.message) ||
    state.runResult.error ||
    "실행 기록이 없어 요약만 표시합니다.";

  updateHeaderMeta({
    stepText,
    functionText: activeFrame ? activeFrame.name : "module",
    lineText: step && step.line ? String(step.line) : "-",
    eventText,
    messageText,
  });

  renderCode(step);
  renderPrimaryStage(step, activeFrame);
  renderVariables(step);
  renderStdout(step ? step.stdout || state.runResult.stdout : state.runResult.stdout);
}

function setInterfaceMode(mode) {
  const traceMode = mode === "trace";
  editorWrap.classList.toggle("hidden", traceMode);
  codeViewer.classList.toggle("hidden", !traceMode);
  editCodeButton.classList.toggle("hidden", !traceMode);
}

function syncDetails() {
  if (variablesDetails.open !== state.detailsExpanded.variables) {
    variablesDetails.open = state.detailsExpanded.variables;
  }
  if (stdoutDetails.open !== state.detailsExpanded.stdout) {
    stdoutDetails.open = state.detailsExpanded.stdout;
  }
}

function getCurrentStep() {
  if (!state.steps.length) {
    return null;
  }
  return state.steps[state.currentIndex];
}

function getActiveFrame(step) {
  if (!step || !Array.isArray(step.stack) || !step.stack.length) {
    return null;
  }
  return step.stack[step.stack.length - 1];
}

function updateHeaderMeta({
  stepText,
  functionText,
  lineText,
  eventText,
  messageText,
}) {
  stepCounter.textContent = stepText;
  functionPill.textContent = functionText;
  linePill.textContent = lineText;
  eventLabel.textContent = eventText;
  messageLabel.textContent = messageText;
}

function renderCode(step) {
  const lines = state.code.split("\n");
  codeViewer.className = "code-viewer";
  codeViewer.innerHTML = lines
    .map((line, index) => {
      const lineNumber = index + 1;
      const active = step && step.line === lineNumber ? "active" : "";
      return `
        <div class="code-line ${active}">
          <span class="code-line-number">${lineNumber}</span>
          <span class="code-line-text">${escapeHtml(line || " ")}</span>
        </div>
      `;
    })
    .join("");

  const activeLine = codeViewer.querySelector(".code-line.active");
  if (activeLine) {
    activeLine.scrollIntoView({ block: "center", inline: "nearest" });
  }
}

function renderPrimaryStage(step, activeFrame) {
  state.primaryView = detectPrimaryView(step);
  primaryViewLabel.textContent = state.primaryView.toUpperCase();

  if (state.primaryView === "graph") {
    stageTitle.textContent = "그래프 흐름";
    stageSubtitle.textContent = "현재 노드와 방문 완료 노드를 가장 먼저 보여줍니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildGraphMarkup(step.graph);
    return;
  }

  if (state.primaryView === "tree") {
    stageTitle.textContent = "호출 트리";
    stageSubtitle.textContent = "재귀 깊이와 활성 호출만 간단하게 추적합니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildTreeMarkup(step.call_tree);
    return;
  }

  stageTitle.textContent = state.runResult.ok ? "실행 요약" : "오류 요약";
  stageSubtitle.textContent = state.runResult.ok
    ? "그래프나 재귀가 없는 코드는 핵심 실행 정보만 요약합니다."
    : "trace가 충분하지 않아도 오류를 같은 화면에서 바로 확인할 수 있습니다.";
  primaryStage.className = "visual-stage";
  primaryStage.innerHTML = buildSummaryMarkup(step, activeFrame);
}

function detectPrimaryView(step) {
  if (step && step.graph && Array.isArray(step.graph.nodes) && step.graph.nodes.length) {
    return "graph";
  }

  if (
    step &&
    step.call_tree &&
    Array.isArray(step.call_tree.children) &&
    step.call_tree.children.length
  ) {
    return "tree";
  }

  return "summary";
}

function buildSummaryMarkup(step, activeFrame) {
  const stdout = step ? step.stdout || state.runResult.stdout : state.runResult.stdout;
  const outputCount = countOutputLines(stdout);
  const lineSource = step && step.line_source ? step.line_source.trim() : "";
  const stackDepth = step && Array.isArray(step.stack) ? step.stack.length : 0;
  const errorText = state.runResult.error || "오류 없음";

  return `
    <div class="stage-scroll">
      <div class="summary-grid">
        <article class="summary-card ${state.runResult.ok ? "" : "error"}">
          <span class="summary-label">상태</span>
          <strong>${escapeHtml(state.runResult.ok ? formatEvent(step?.event || "end") : "error")}</strong>
          <p>${escapeHtml((step && step.message) || errorText)}</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">현재 함수</span>
          <strong>${escapeHtml(activeFrame ? activeFrame.name : "module")}</strong>
          <p>${escapeHtml(lineSource || "현재 강조할 줄이 없습니다.")}</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">호출 깊이</span>
          <strong>${stackDepth}</strong>
          <p>현재 활성화된 프레임 수</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">출력 줄 수</span>
          <strong>${outputCount}</strong>
          <p>${escapeHtml(stdout ? "stdout 패널에서 전체 출력을 확인할 수 있습니다." : "아직 출력이 없습니다.")}</p>
        </article>
      </div>
    </div>
  `;
}

function buildGraphMarkup(graph) {
  const size = 360;
  const center = size / 2;
  const radius = 118;
  const positionedNodes = graph.nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / graph.nodes.length - Math.PI / 2;
    return {
      ...node,
      x: center + radius * Math.cos(angle),
      y: center + radius * Math.sin(angle),
    };
  });
  const positionMap = Object.fromEntries(
    positionedNodes.map((node) => [node.id, node]),
  );

  return `
    <div class="stage-scroll">
      <div class="visual-caption">
        <span><span class="legend-dot current"></span>현재 노드</span>
        <span><span class="legend-dot visited"></span>방문 완료</span>
        <span><span class="legend-dot"></span>미방문</span>
      </div>
      <svg class="graph-svg" viewBox="0 0 440 420" preserveAspectRatio="xMidYMid meet">
        <text class="graph-meta" x="18" y="26">${escapeXml(graph.name)}${graph.tree_mode ? " (tree-like)" : ""}</text>
        ${graph.edges
          .map((edge) => {
            const source = positionMap[edge.source];
            const target = positionMap[edge.target];
            if (!source || !target) {
              return "";
            }
            return `
              <line class="graph-edge" x1="${source.x + 40}" y1="${source.y + 24}" x2="${target.x + 40}" y2="${target.y + 24}" />
            `;
          })
          .join("")}
        ${positionedNodes
          .map(
            (node) => `
              <g class="graph-node ${node.visited ? "visited" : ""} ${node.current ? "current" : ""}">
                <circle cx="${node.x + 40}" cy="${node.y + 24}" r="24"></circle>
                <text class="graph-label" x="${node.x + 40}" y="${node.y + 29}" text-anchor="middle">${escapeXml(node.label)}</text>
              </g>
            `,
          )
          .join("")}
      </svg>
    </div>
  `;
}

function buildTreeMarkup(tree) {
  const layout = buildTreeLayout(normalizeTreeRoot(tree));
  return `
    <div class="stage-scroll">
      <div class="visual-caption">
        <span><span class="legend-dot current"></span>활성 호출</span>
        <span><span class="legend-dot"></span>비활성 호출</span>
      </div>
      <svg class="tree-svg" viewBox="0 0 ${layout.width} ${layout.height}" preserveAspectRatio="xMidYMid meet">
        ${layout.edges
          .map(
            (edge) => `
              <path
                class="tree-edge"
                d="M ${edge.from.x} ${edge.from.y} C ${edge.from.x + 70} ${edge.from.y}, ${edge.to.x - 70} ${edge.to.y}, ${edge.to.x} ${edge.to.y}"
                fill="none"
              />
            `,
          )
          .join("")}
        ${layout.nodes
          .map(
            (node) => `
              <g class="tree-node ${node.active ? "active" : ""} ${node.status === "exception" ? "exception" : ""}" transform="translate(${node.x - 70}, ${node.y - 24})">
                <rect rx="14" ry="14" width="140" height="48"></rect>
                <text x="12" y="20">${escapeXml(trimLabel(node.label, 19))}</text>
                <text x="12" y="36">${escapeXml(shortStatus(node.status))}</text>
              </g>
            `,
          )
          .join("")}
      </svg>
    </div>
  `;
}

function normalizeTreeRoot(tree) {
  if (
    tree &&
    tree.label === "module" &&
    Array.isArray(tree.children) &&
    tree.children.length === 1
  ) {
    return tree.children[0];
  }

  return tree;
}

function buildTreeLayout(tree) {
  const nodes = [];
  const edges = [];
  const xGap = 188;
  const yGap = 92;
  const tracker = { nextY: 76, maxDepth: 0 };

  function assign(node, depth) {
    tracker.maxDepth = Math.max(tracker.maxDepth, depth);
    const children = node.children || [];

    if (!children.length) {
      node.x = 90 + depth * xGap;
      node.y = tracker.nextY;
      tracker.nextY += yGap;
      return;
    }

    children.forEach((child) => assign(child, depth + 1));
    node.x = 90 + depth * xGap;
    node.y = average(children.map((child) => child.y));
  }

  function collect(node, parent = null) {
    nodes.push(node);
    if (parent) {
      edges.push({
        from: { x: parent.x + 70, y: parent.y },
        to: { x: node.x - 70, y: node.y },
      });
    }
    (node.children || []).forEach((child) => collect(child, node));
  }

  assign(tree, 0);
  collect(tree);

  return {
    nodes,
    edges,
    width: Math.max(420, 240 + tracker.maxDepth * xGap),
    height: Math.max(300, tracker.nextY),
  };
}

function renderVariables(step) {
  renderStack(step ? step.stack || [] : []);
  renderGlobals(step ? step.globals || {} : {});
}

function renderStack(frames) {
  if (!frames.length) {
    stackView.className = "stack-view empty-state";
    stackView.textContent = "현재 활성화된 프레임이 없습니다.";
    return;
  }

  stackView.className = "stack-view";
  stackView.innerHTML = frames
    .map(
      (frame) => `
        <article class="frame-card">
          <div class="frame-head">
            <h3 class="frame-title">${escapeHtml(frame.label || frame.name)}</h3>
            <span class="line-chip">line ${frame.line ?? "-"}</span>
          </div>
          ${renderVariableList(frame.locals)}
        </article>
      `,
    )
    .join("");
}

function renderGlobals(globals) {
  if (!Object.keys(globals).length) {
    globalsView.className = "globals-view empty-state";
    globalsView.textContent = "표시할 전역 변수가 없습니다.";
    return;
  }

  globalsView.className = "globals-view";
  globalsView.innerHTML = `<article class="scope-card">${renderVariableList(globals)}</article>`;
}

function renderVariableList(scope) {
  const entries = Object.entries(scope || {});
  if (!entries.length) {
    return '<div class="var-item">지역 변수가 없습니다.</div>';
  }

  return `
    <div class="var-list">
      ${entries
        .map(
          ([name, value]) => `
            <div class="var-item">
              <span class="var-name">${escapeHtml(name)}</span>
              ${renderValue(value)}
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderValue(value) {
  if (!value) {
    return '<div class="value-inline">None</div>';
  }

  const meta = `<div class="value-meta">${escapeHtml(value.type || "value")} · ${escapeHtml(value.repr || "")}</div>`;

  if (value.items && Array.isArray(value.items)) {
    const children = value.items
      .map((item, index) => {
        if (value.type === "dict") {
          return `
            <div class="value-row">
              <strong>${renderInline(item.key)}</strong> : ${renderValue(item.value)}
            </div>
          `;
        }
        return `
          <div class="value-row">
            <strong>[${index}]</strong> ${renderValue(item)}
          </div>
        `;
      })
      .join("");
    return `${meta}<div class="value-tree">${children}${value.truncated ? '<div class="value-row">...</div>' : ""}</div>`;
  }

  if (value.attributes && Array.isArray(value.attributes)) {
    return `
      ${meta}
      <div class="value-tree">
        ${value.attributes
          .map(
            (attribute) => `
              <div class="value-row">
                <strong>${escapeHtml(attribute.name)}</strong> : ${renderValue(attribute.value)}
              </div>
            `,
          )
          .join("")}
        ${value.truncated ? '<div class="value-row">...</div>' : ""}
      </div>
    `;
  }

  return meta;
}

function renderInline(value) {
  if (!value) {
    return "None";
  }
  return `<span class="value-inline">${escapeHtml(value.repr || "")}</span>`;
}

function renderStdout(stdout) {
  stdoutView.textContent = stdout || "출력이 없습니다.";
}

function countOutputLines(stdout) {
  if (!stdout) {
    return 0;
  }

  return stdout.trim().split("\n").filter(Boolean).length;
}

function formatEvent(event) {
  const labels = {
    line: "line",
    return: "return",
    exception: "exception",
    end: "end",
    error: "error",
  };
  return labels[event] || event || "unknown";
}

function shortStatus(status) {
  const labels = {
    running: "run",
    returned: "ret",
    exception: "err",
  };
  return labels[status] || status || "run";
}

function showBanner(message, variant = "error") {
  feedbackBanner.textContent = message;
  feedbackBanner.className = `feedback-banner ${variant === "success" ? "success" : ""}`;
}

function hideBanner() {
  feedbackBanner.className = "feedback-banner hidden";
  feedbackBanner.textContent = "";
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function trimLabel(value, maxLength) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeXml(value) {
  return escapeHtml(value);
}
