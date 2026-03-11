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
const codeViewer = document.getElementById("code-viewer");
const callTree = document.getElementById("call-tree");
const graphView = document.getElementById("graph-view");
const stackView = document.getElementById("stack-view");
const globalsView = document.getElementById("globals-view");
const stdoutView = document.getElementById("stdout-view");

document.addEventListener("DOMContentLoaded", () => {
  codeInput.value = state.code;
  renderIdleState();
});

loadExampleButton.addEventListener("click", () => {
  codeInput.value = sampleCode;
  hideBanner();
});

runButton.addEventListener("click", runVisualization);
prevStepButton.addEventListener("click", () => moveStep(-1));
nextStepButton.addEventListener("click", () => moveStep(1));
playStepButton.addEventListener("click", togglePlayback);

stepSlider.addEventListener("input", (event) => {
  state.currentIndex = Number(event.target.value);
  renderCurrentStep();
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

    if (!payload.steps || payload.steps.length === 0) {
      throw new Error(payload.error || "실행 기록을 만들지 못했습니다.");
    }

    configureControls();
    renderCurrentStep();

    if (payload.ok) {
      showBanner(
        `총 ${payload.steps.length}개의 step을 생성했습니다. slider나 재생 버튼으로 이동해 보세요.`,
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
  renderCurrentStep();
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
    renderCurrentStep();
  }

  playStepButton.textContent = "일시정지";
  state.timer = window.setInterval(() => {
    if (state.currentIndex >= state.steps.length - 1) {
      stopPlayback();
      return;
    }
    state.currentIndex += 1;
    renderCurrentStep();
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
  stepCounter.textContent = "0 / 0";
  eventLabel.textContent = "대기 중";
  messageLabel.textContent = "코드를 실행하면 trace가 생성됩니다.";
  codeViewer.className = "code-viewer empty-state";
  codeViewer.textContent = "아직 실행 기록이 없습니다.";
  callTree.className = "visual-surface empty-state";
  callTree.textContent = "재귀 호출이 발생하면 트리 구조가 여기에 표시됩니다.";
  graphView.className = "visual-surface empty-state";
  graphView.textContent = "`graph`, `tree`, `adj` 같은 인접 구조를 찾으면 노드를 그립니다.";
  stackView.className = "stack-view empty-state";
  stackView.textContent = "실행을 시작하면 프레임별 지역 변수가 표시됩니다.";
  globalsView.className = "globals-view empty-state";
  globalsView.textContent = "아직 값이 없습니다.";
  stdoutView.textContent = "실행 출력이 여기에 표시됩니다.";
  prevStepButton.disabled = true;
  playStepButton.disabled = true;
  nextStepButton.disabled = true;
  stepSlider.disabled = true;
  stepSlider.max = "0";
  stepSlider.value = "0";
}

function renderCurrentStep() {
  if (!state.steps.length) {
    renderIdleState();
    return;
  }

  const step = state.steps[state.currentIndex];
  stepSlider.value = String(state.currentIndex);
  stepCounter.textContent = `${state.currentIndex + 1} / ${state.steps.length}`;
  eventLabel.textContent = formatEvent(step.event);
  messageLabel.textContent = step.message || "실행 상태가 갱신되었습니다.";

  renderCode(step);
  renderStack(step.stack || []);
  renderGlobals(step.globals || {});
  renderStdout(step.stdout || "");
  renderCallTree(step.call_tree);
  renderGraph(step.graph);
}

function renderCode(step) {
  const lines = state.code.split("\n");
  codeViewer.className = "code-viewer";
  codeViewer.innerHTML = lines
    .map((line, index) => {
      const lineNumber = index + 1;
      const active = step.line === lineNumber ? "active" : "";
      return `
        <div class="code-line ${active}">
          <span class="code-line-number">${lineNumber}</span>
          <span class="code-line-text">${escapeHtml(line || " ")}</span>
        </div>
      `;
    })
    .join("");
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

function renderCallTree(tree) {
  if (!tree || (!tree.children || !tree.children.length)) {
    callTree.className = "visual-surface empty-state";
    callTree.textContent = "재귀 호출이 발생하면 트리 구조가 여기에 표시됩니다.";
    return;
  }

  callTree.className = "visual-surface";
  const layout = buildTreeLayout(tree);
  const svg = `
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
            <g class="tree-node ${node.active ? "active" : ""} ${node.status === "exception" ? "exception" : ""}" transform="translate(${node.x - 66}, ${node.y - 22})">
              <rect rx="14" ry="14" width="132" height="44"></rect>
              <text x="12" y="20">${escapeXml(trimLabel(node.label, 18))}</text>
              <text x="12" y="35">${escapeXml(node.status)}</text>
            </g>
          `,
        )
        .join("")}
    </svg>
  `;
  callTree.innerHTML = svg;
}

function buildTreeLayout(tree) {
  const nodes = [];
  const edges = [];
  const xGap = 180;
  const yGap = 88;
  const tracker = { nextY: 70, maxDepth: 0 };

  function assign(node, depth) {
    tracker.maxDepth = Math.max(tracker.maxDepth, depth);
    const children = node.children || [];

    if (!children.length) {
      node.x = 90 + depth * xGap;
      node.y = tracker.nextY;
      tracker.nextY += yGap;
    } else {
      children.forEach((child) => assign(child, depth + 1));
      node.x = 90 + depth * xGap;
      node.y = average(children.map((child) => child.y));
    }
  }

  function collect(node, parent = null) {
    nodes.push(node);
    if (parent) {
      edges.push({
        from: { x: parent.x + 66, y: parent.y },
        to: { x: node.x - 66, y: node.y },
      });
    }
    (node.children || []).forEach((child) => collect(child, node));
  }

  assign(tree, 0);
  collect(tree, null);

  return {
    nodes,
    edges,
    width: Math.max(360, 220 + tracker.maxDepth * xGap),
    height: Math.max(260, tracker.nextY),
  };
}

function renderGraph(graph) {
  if (!graph || !graph.nodes || !graph.nodes.length) {
    graphView.className = "visual-surface empty-state";
    graphView.textContent = "`graph`, `tree`, `adj` 같은 인접 구조를 찾으면 노드를 그립니다.";
    return;
  }

  const size = 340;
  const center = size / 2;
  const radius = 112;
  const positionedNodes = graph.nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / graph.nodes.length - Math.PI / 2;
    return {
      ...node,
      x: center + radius * Math.cos(angle),
      y: center + radius * Math.sin(angle),
    };
  });
  const positionMap = Object.fromEntries(positionedNodes.map((node) => [node.id, node]));

  graphView.className = "visual-surface";
  graphView.innerHTML = `
    <svg class="graph-svg" viewBox="0 0 420 380" preserveAspectRatio="xMidYMid meet">
      <text class="graph-meta" x="18" y="28">${escapeXml(graph.name)}${graph.tree_mode ? " (tree-like)" : ""}</text>
      ${graph.edges
        .map((edge) => {
          const source = positionMap[edge.source];
          const target = positionMap[edge.target];
          if (!source || !target) {
            return "";
          }
          return `
            <line class="graph-edge" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" />
          `;
        })
        .join("")}
      ${positionedNodes
        .map(
          (node) => `
            <g class="graph-node ${node.visited ? "visited" : ""} ${node.current ? "current" : ""}">
              <circle cx="${node.x}" cy="${node.y}" r="24"></circle>
              <text class="graph-label" x="${node.x}" y="${node.y + 5}" text-anchor="middle">${escapeXml(node.label)}</text>
            </g>
          `,
        )
        .join("")}
    </svg>
  `;
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
