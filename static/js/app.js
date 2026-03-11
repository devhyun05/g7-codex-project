const EXAMPLES = {
  graphDfs: {
    label: "그래프 DFS",
    stdin: "",
    code: `graph = {
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
`,
  },
  stackPushPop: {
    label: "스택 push/pop",
    stdin: "",
    code: `stack = []

for value in [3, 7, 11]:
    stack.append(value)
    print("push", value, stack)

removed = stack.pop()
print("pop", removed)
print("left", stack)
`,
  },
  queueDeque: {
    label: "큐 enqueue/dequeue",
    stdin: "",
    code: `from collections import deque

queue = deque([10, 20, 30])
print("start", list(queue))

queue.append(40)
print("enqueue", list(queue))

front = queue.popleft()
print("dequeue", front)
print("left", list(queue))
`,
  },
  binaryTree: {
    label: "이진 트리 순회",
    stdin: "",
    code: `class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

root = Node(
    "A",
    Node("B", Node("D"), Node("E")),
    Node("C", None, Node("F"))
)

def inorder(node):
    if node is None:
        return
    inorder(node.left)
    print(node.value)
    inorder(node.right)

inorder(root)
`,
  },
  stdinExample: {
    label: "input() 처리",
    stdin: `5
1 2 3 4 5`,
    code: `n = int(input())
nums = list(map(int, input().split()))

queue = nums[:n]
print("sum", sum(queue))
print("first", queue[0])
`,
  },
};

const DEFAULT_EXAMPLE_KEY = "graphDfs";

const state = {
  code: EXAMPLES[DEFAULT_EXAMPLE_KEY].code,
  stdin: EXAMPLES[DEFAULT_EXAMPLE_KEY].stdin,
  steps: [],
  currentIndex: 0,
  timer: null,
  primaryView: "summary",
  drawerView: null,
  runResult: {
    ok: true,
    error: null,
    stdout: "",
    stdin: "",
  },
};

const codeInput = document.getElementById("code-input");
const stdinInput = document.getElementById("stdin-input");
const exampleSelect = document.getElementById("example-select");
const runButton = document.getElementById("run-button");
const loadExampleButton = document.getElementById("load-example");
const prevStepButton = document.getElementById("prev-step");
const playStepButton = document.getElementById("play-step");
const nextStepButton = document.getElementById("next-step");
const stepSlider = document.getElementById("step-slider");
const stepCounter = document.getElementById("step-counter");
const eventLabel = document.getElementById("event-label");
const messageLabel = document.getElementById("message-label");
const editorWrap = document.getElementById("editor-wrap");
const editCodeButton = document.getElementById("edit-code-button");
const codeViewer = document.getElementById("code-viewer");
const functionPill = document.getElementById("function-pill");
const linePill = document.getElementById("line-pill");
const stageTitle = document.getElementById("stage-title");
const stageSubtitle = document.getElementById("message-label");
const primaryViewLabel = document.getElementById("primary-view-label");
const primaryStage = document.getElementById("primary-stage");
const detailDock = document.getElementById("detail-dock");
const detailDrawer = document.getElementById("detail-drawer");
const detailDrawerTitle = document.getElementById("detail-drawer-title");
const variablesToggle = document.getElementById("variables-toggle");
const stdoutToggle = document.getElementById("stdout-toggle");
const variablesArrow = variablesToggle.querySelector(".drawer-arrow");
const stdoutArrow = stdoutToggle.querySelector(".drawer-arrow");
const closeDrawerButton = document.getElementById("close-drawer");
const variablesPanel = document.getElementById("variables-panel");
const stdoutPanel = document.getElementById("stdout-panel");
const stackView = document.getElementById("stack-view");
const globalsView = document.getElementById("globals-view");
const stdoutView = document.getElementById("stdout-view");

document.addEventListener("DOMContentLoaded", () => {
  populateExamples();
  loadExampleByKey(DEFAULT_EXAMPLE_KEY);
  variablesToggle.addEventListener("click", () => toggleDrawer("variables"));
  stdoutToggle.addEventListener("click", () => toggleDrawer("stdout"));
  closeDrawerButton.addEventListener("click", () => {
    state.drawerView = null;
    syncDrawer();
  });

  renderIdleState();
});

loadExampleButton.addEventListener("click", () => {
  stopPlayback();
  loadExampleByKey(exampleSelect.value || DEFAULT_EXAMPLE_KEY);
  renderIdleState();
});

runButton.addEventListener("click", runVisualization);
editCodeButton.addEventListener("click", () => {
  stopPlayback();
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
  const stdin = stdinInput.value;

  if (!code.trim()) {
    updateIdleMessage("시각화할 코드를 입력하세요.");
    return;
  }

  runButton.disabled = true;
  playStepButton.disabled = true;
  runButton.textContent = "실행 중...";
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch("/api/visualize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: controller.signal,
      body: JSON.stringify({ code, stdin }),
    });
    window.clearTimeout(timeoutId);
    const payload = await response.json();

    state.code = payload.code || code;
    state.stdin = payload.stdin || stdin;
    state.steps = payload.steps || [];
    state.currentIndex = 0;
    state.runResult = {
      ok: Boolean(payload.ok),
      error: payload.error || null,
      stdout: payload.stdout || "",
      stdin: payload.stdin || stdin,
    };
    state.drawerView = payload.ok ? null : "stdout";

    configureControls();
    renderTraceState();
  } catch (error) {
    window.clearTimeout(timeoutId);
    renderIdleState();
    if (error.name === "AbortError") {
      updateIdleMessage("서버 응답이 지연되고 있습니다. 개발 서버가 실행 중인지 확인하세요.");
      return;
    }
    updateIdleMessage("서버에 연결하지 못했습니다. `python app.py`로 서버가 실행 중인지 확인하세요.");
  } finally {
    runButton.disabled = false;
    runButton.textContent = "실행 시작";
  }
}

function populateExamples() {
  exampleSelect.innerHTML = Object.entries(EXAMPLES)
    .map(
      ([key, example]) =>
        `<option value="${escapeHtml(key)}">${escapeHtml(example.label)}</option>`,
    )
    .join("");
}

function loadExampleByKey(exampleKey) {
  const example = EXAMPLES[exampleKey] || EXAMPLES[DEFAULT_EXAMPLE_KEY];
  state.code = example.code;
  state.stdin = example.stdin;
  codeInput.value = example.code;
  stdinInput.value = example.stdin;
  exampleSelect.value = exampleKey;
}

function configureControls() {
  const hasSteps = state.steps.length > 0;
  prevStepButton.disabled = !hasSteps;
  playStepButton.disabled = !hasSteps;
  nextStepButton.disabled = !hasSteps;
  stepSlider.disabled = !hasSteps;
  stepSlider.min = 0;
  stepSlider.max = hasSteps ? String(state.steps.length - 1) : "0";
  stepSlider.value = hasSteps ? String(state.currentIndex) : "0";
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
  state.drawerView = null;
  state.runResult = {
    ok: true,
    error: null,
    stdout: "",
    stdin: stdinInput.value,
  };

  setInterfaceMode("edit");
  configureControls();
  syncDrawer();
  updateHeaderMeta({
    stepText: "0 / 0",
    functionText: "module",
    lineText: "-",
    eventText: "대기 중",
    messageText: "그래프, 스택, 큐, 트리, 재귀 호출을 자동으로 골라 보여줍니다.",
  });

  codeViewer.className = "code-viewer empty-state hidden";
  codeViewer.textContent = "아직 실행 기록이 없습니다.";

  stageTitle.textContent = "주 시각화";
  stageSubtitle.textContent =
    "감지된 자료구조가 있으면 우선 보여주고, 없으면 실행 요약을 표시합니다.";
  primaryViewLabel.textContent = "SUMMARY";
  primaryStage.className = "visual-stage empty-state";
  primaryStage.textContent = "실행 결과가 여기에 표시됩니다.";

  renderVariables(null);
  renderStdout("");
}

function renderTraceState() {
  setInterfaceMode("trace");
  syncDrawer();

  const step = getCurrentStep();
  const activeFrame = getActiveFrame(step);
  const stepText = state.steps.length
    ? `${state.currentIndex + 1} / ${state.steps.length}`
    : "0 / 0";
  const eventText = step
    ? formatEvent(step.event)
    : state.runResult.ok
      ? "end"
      : "error";
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
  detailDock.classList.toggle("hidden", !traceMode);
  if (!traceMode) {
    state.drawerView = null;
  }
}

function toggleDrawer(view) {
  state.drawerView = state.drawerView === view ? null : view;
  syncDrawer();
}

function syncDrawer() {
  const traceMode = !codeViewer.classList.contains("hidden");
  const open = traceMode && Boolean(state.drawerView);

  detailDock.classList.toggle("hidden", !traceMode);
  detailDrawer.classList.toggle("hidden", !open);
  detailDrawer.classList.toggle("open", open);
  detailDrawer.setAttribute("aria-hidden", String(!open));

  variablesPanel.classList.toggle("hidden", state.drawerView !== "variables");
  stdoutPanel.classList.toggle("hidden", state.drawerView !== "stdout");

  variablesToggle.classList.toggle("active", state.drawerView === "variables");
  stdoutToggle.classList.toggle("active", state.drawerView === "stdout");
  variablesArrow.textContent = state.drawerView === "variables" ? "▶" : "◀";
  stdoutArrow.textContent = state.drawerView === "stdout" ? "▶" : "◀";
  variablesToggle.setAttribute(
    "aria-expanded",
    String(state.drawerView === "variables"),
  );
  stdoutToggle.setAttribute(
    "aria-expanded",
    String(state.drawerView === "stdout"),
  );

  if (state.drawerView === "variables") {
    detailDrawerTitle.textContent = "변수 살펴보기";
  } else if (state.drawerView === "stdout") {
    detailDrawerTitle.textContent = "출력 보기";
  } else {
    detailDrawerTitle.textContent = "보조 정보";
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
  primaryViewLabel.textContent = formatViewLabel(state.primaryView);

  if (state.primaryView === "graph") {
    stageTitle.textContent = "그래프 흐름";
    stageSubtitle.textContent = "현재 노드와 방문 완료 노드를 가장 먼저 보여줍니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildGraphMarkup(step.graph);
    return;
  }

  if (state.primaryView === "data-tree") {
    stageTitle.textContent = "트리 구조";
    stageSubtitle.textContent = "현재 가리키는 노드와 전체 트리 구조를 함께 보여줍니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildDataTreeMarkup(step.structure);
    return;
  }

  if (state.primaryView === "stack") {
    stageTitle.textContent = "스택 상태";
    stageSubtitle.textContent = "맨 위 원소를 강조해서 push/pop 흐름을 보여줍니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildStackMarkup(step.structure);
    return;
  }

  if (state.primaryView === "queue") {
    stageTitle.textContent = "큐 상태";
    stageSubtitle.textContent = "front와 back을 구분해서 enqueue/dequeue 흐름을 보여줍니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildQueueMarkup(step.structure);
    return;
  }

  if (state.primaryView === "call-tree") {
    stageTitle.textContent = "호출 트리";
    stageSubtitle.textContent = "재귀 깊이와 활성 호출만 간단하게 추적합니다.";
    primaryStage.className = "visual-stage";
    primaryStage.innerHTML = buildCallTreeMarkup(step.call_tree);
    return;
  }

  stageTitle.textContent = state.runResult.ok ? "실행 요약" : "오류 요약";
  stageSubtitle.textContent = state.runResult.ok
    ? "감지된 구조가 없을 때는 핵심 실행 정보만 요약합니다."
    : "trace가 충분하지 않아도 오류를 같은 화면에서 바로 확인할 수 있습니다.";
  primaryStage.className = "visual-stage";
  primaryStage.innerHTML = buildSummaryMarkup(step, activeFrame);
}

function detectPrimaryView(step) {
  if (step && step.graph && Array.isArray(step.graph.nodes) && step.graph.nodes.length) {
    return "graph";
  }

  if (step && step.structure && step.structure.kind === "tree") {
    return "data-tree";
  }

  if (step && step.structure && step.structure.kind === "stack") {
    return "stack";
  }

  if (step && step.structure && step.structure.kind === "queue") {
    return "queue";
  }

  if (
    step &&
    step.call_tree &&
    Array.isArray(step.call_tree.children) &&
    step.call_tree.children.length
  ) {
    return "call-tree";
  }

  return "summary";
}

function formatViewLabel(view) {
  const labels = {
    graph: "GRAPH",
    "data-tree": "TREE",
    stack: "STACK",
    queue: "QUEUE",
    "call-tree": "CALL",
    summary: "SUMMARY",
  };
  return labels[view] || "SUMMARY";
}

function buildSummaryMarkup(step, activeFrame) {
  const stdout = step ? step.stdout || state.runResult.stdout : state.runResult.stdout;
  const lineSource = step && step.line_source ? step.line_source.trim() : "";
  const stackDepth = step && Array.isArray(step.stack) ? step.stack.length : 0;
  const errorText = state.runResult.error || "오류 없음";
  const stdinLines = countInputLines(state.runResult.stdin);

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
          <span class="summary-label">입력 줄 수</span>
          <strong>${stdinLines}</strong>
          <p>${escapeHtml(stdinLines ? "편집 화면의 입력 데이터로 실행했습니다." : "input() 없이 실행했습니다.")}</p>
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

function buildStackMarkup(structure) {
  const items = structure.items || [];
  return `
    <div class="stage-scroll">
      <div class="visual-caption">
        <span><span class="legend-dot current"></span>top</span>
      </div>
      <div class="structure-board">
        <div class="stack-visual">
          ${items.length
            ? items
                .map(
                  (item, index) => `
                    <div class="stack-item ${index === structure.top_index ? "top" : ""}">
                      <span class="structure-tag">${index === structure.top_index ? "TOP" : `#${index}`}</span>
                      ${escapeHtml(item)}
                    </div>
                  `,
                )
                .join("")
            : '<div class="stack-item">empty</div>'}
        </div>
      </div>
    </div>
  `;
}

function buildQueueMarkup(structure) {
  const items = structure.items || [];
  return `
    <div class="stage-scroll">
      <div class="visual-caption">
        <span><span class="legend-dot current"></span>front</span>
        <span><span class="legend-dot visited"></span>back</span>
      </div>
      <div class="structure-board">
        <div class="queue-visual">
          <div class="queue-end">FRONT</div>
          <div class="queue-lane">
            ${items.length
              ? items
                  .map((item, index) => {
                    const classes = [
                      "queue-item",
                      index === structure.front_index ? "front" : "",
                      index === structure.back_index ? "back" : "",
                    ]
                      .filter(Boolean)
                      .join(" ");
                    return `<div class="${classes}">${escapeHtml(item)}</div>`;
                  })
                  .join("")
              : '<div class="queue-item">empty</div>'}
          </div>
          <div class="queue-end">BACK</div>
        </div>
      </div>
    </div>
  `;
}

function buildDataTreeMarkup(structure) {
  const layout = buildHierarchyLayout(structure.root);
  return `
    <div class="stage-scroll">
      <div class="visual-caption">
        <span><span class="legend-dot current"></span>현재 노드</span>
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
              <g class="data-tree-node ${node.id === structure.current_id ? "current" : ""}" transform="translate(${node.x - 64}, ${node.y - 20})">
                <rect rx="14" ry="14" width="128" height="40"></rect>
                <text x="12" y="24">${escapeXml(trimLabel(node.label, 17))}</text>
              </g>
            `,
          )
          .join("")}
      </svg>
    </div>
  `;
}

function buildCallTreeMarkup(tree) {
  const normalized = normalizeCallTreeRoot(tree);
  const layout = buildHierarchyLayout(normalized);
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

function normalizeCallTreeRoot(tree) {
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

function buildHierarchyLayout(root) {
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

  assign(root, 0);
  collect(root);

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

function countInputLines(stdin) {
  if (!stdin) {
    return 0;
  }
  return stdin.split("\n").length;
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

function updateIdleMessage(message) {
  eventLabel.textContent = "안내";
  messageLabel.textContent = message;
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
