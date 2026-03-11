(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;
  const structureGuides = [
    {
      label: "STACK",
      title: "스택",
      pattern: "append() + pop()",
      description: "흐름을 top 중심으로 표시합니다.",
    },
    {
      label: "QUEUE",
      title: "큐",
      pattern: "deque / popleft() / pop(0)",
      description: "패턴을 front와 back으로 구분합니다.",
    },
    {
      label: "TREE",
      title: "트리",
      pattern: "left / right / children",
      description: "관계를 노드 구조로 정리합니다.",
    },
    {
      label: "GRAPH",
      title: "그래프",
      pattern: "인접 리스트 / 인접 딕셔너리",
      description: "연결과 방문 상태를 보여줍니다.",
    },
  ];

  function renderIdle(dom) {
    dom.stageTitle.textContent = "시각화 가능한 자료 구조";
    dom.stageCaption.textContent = "실행하면 감지된 항목에 맞춰 이 영역이 자동으로 전환됩니다.";
    dom.primaryViewLabel.textContent = "GUIDE";
    dom.primaryStage.className = "visual-stage";
    dom.primaryStage.innerHTML = buildStructureGuideMarkup();
    return "summary";
  }

  function render(dom, state, step, activeFrame) {
    const view = detectPrimaryView(step);
    dom.primaryViewLabel.textContent = utils.formatViewLabel(view);

    if (view === "graph") {
      dom.stageTitle.textContent = "그래프 흐름";
      dom.stageCaption.textContent = "코드에서 감지한 인접 구조를 그래프로 해석해 현재 노드와 방문 상태를 보여줍니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildGraphMarkup(step.graph);
      return view;
    }

    if (view === "data-tree") {
      dom.stageTitle.textContent = "트리 구조";
      dom.stageCaption.textContent = "left / right 또는 children 관계를 기반으로 트리를 구성했습니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildDataTreeMarkup(step.structure);
      return view;
    }

    if (view === "stack") {
      dom.stageTitle.textContent = "스택 상태";
      dom.stageCaption.textContent = "append + pop 흐름을 스택으로 해석해 top을 강조했습니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildStackMarkup(step.structure);
      return view;
    }

    if (view === "queue") {
      dom.stageTitle.textContent = "큐 상태";
      dom.stageCaption.textContent = "deque / pop(0) 패턴을 큐로 해석해 front와 back을 구분했습니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildQueueMarkup(step.structure);
      return view;
    }

    if (view === "call-tree") {
      dom.stageTitle.textContent = "호출 트리";
      dom.stageCaption.textContent = "특정 자료구조보다 재귀 호출 흐름이 더 뚜렷해 호출 트리를 보여줍니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildCallTreeMarkup(step.call_tree);
      return view;
    }

    dom.stageTitle.textContent = state.runResult.ok ? "실행 요약" : "오류 요약";
    dom.stageCaption.textContent = state.runResult.ok
      ? "특정 자료구조가 감지되지 않아서 현재 실행 상태를 요약합니다."
      : "오류가 있어도 가능한 범위의 실행 흐름을 유지합니다.";
    dom.primaryStage.className = "visual-stage";
    dom.primaryStage.innerHTML = buildSummaryMarkup(step, activeFrame, state);
    return view;
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

  function buildSummaryMarkup(step, activeFrame, state) {
    const structures = state.runResult.analysis.structures || [];
    const lineSource = step && step.line_source ? step.line_source.trim() : "";
    const stackDepth = step && Array.isArray(step.stack) ? step.stack.length : 0;
    const stdinLines = utils.countInputLines(state.runResult.stdin);

    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          <article class="summary-card ${state.runResult.ok ? "" : "error"}">
            <span class="summary-label">상태</span>
            <strong>${utils.escapeHtml(state.runResult.ok ? utils.formatEvent(step?.event || "end") : "error")}</strong>
            <p>${utils.escapeHtml((step && step.message) || state.runResult.error || "실행 전입니다.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">현재 함수</span>
            <strong>${utils.escapeHtml(activeFrame ? activeFrame.name : "module")}</strong>
            <p>${utils.escapeHtml(lineSource || "현재 강조할 줄이 없습니다.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">호출 깊이</span>
            <strong>${stackDepth}</strong>
            <p>현재 활성화된 프레임 수</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">자동 판단</span>
            <strong>${structures.length}</strong>
            <p>${utils.escapeHtml(structures.length ? state.runResult.analysis.summary : "감지된 자료구조가 없습니다.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">입력 줄 수</span>
            <strong>${stdinLines}</strong>
            <p>${utils.escapeHtml(stdinLines ? "입력 데이터를 함께 사용했습니다." : "input() 없이 실행했습니다.")}</p>
          </article>
        </div>
      </div>
    `;
  }

  function buildStructureGuideMarkup() {
    return `
      <div class="stage-scroll structure-guide">
        <div class="summary-grid structure-guide-grid">
          ${structureGuides
            .map(
              (item) => `
                <article class="summary-card guide-card">
                  <span class="summary-label">${utils.escapeHtml(item.label)}</span>
                  <strong>${utils.escapeHtml(item.title)}</strong>
                  <p><span class="guide-pattern">${utils.escapeHtml(item.pattern)}</span> ${utils.escapeHtml(item.description)}</p>
                </article>
              `,
            )
            .join("")}
        </div>
        <div class="structure-guide-note">
          재귀가 핵심인 코드는 호출 트리로, 특정 구조가 없으면 실행 요약으로 표시됩니다.
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
    const positionMap = Object.fromEntries(positionedNodes.map((node) => [node.id, node]));

    return `
      <div class="stage-scroll">
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>현재 노드</span>
          <span><span class="legend-dot visited"></span>방문 완료</span>
          <span><span class="legend-dot"></span>미방문</span>
        </div>
        <svg class="graph-svg" viewBox="0 0 440 420" preserveAspectRatio="xMidYMid meet">
          <text class="graph-meta" x="18" y="26">${utils.escapeXml(graph.name)}${graph.tree_mode ? " (tree-like)" : ""}</text>
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
                  <text class="graph-label" x="${node.x + 40}" y="${node.y + 29}" text-anchor="middle">${utils.escapeXml(node.label)}</text>
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
                        ${utils.escapeHtml(item)}
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
                      return `<div class="${classes}">${utils.escapeHtml(item)}</div>`;
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
                  <text x="12" y="24">${utils.escapeXml(utils.trimLabel(node.label, 17))}</text>
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
                  <text x="12" y="20">${utils.escapeXml(utils.trimLabel(node.label, 19))}</text>
                  <text x="12" y="36">${utils.escapeXml(utils.shortStatus(node.status))}</text>
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
      node.y = utils.average(children.map((child) => child.y));
    }

    function collect(node, parent) {
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
    collect(root, null);

    return {
      nodes,
      edges,
      width: Math.max(420, 240 + tracker.maxDepth * xGap),
      height: Math.max(300, tracker.nextY),
    };
  }

  window.Visualizer.renderers.visualPanel = {
    render,
    renderIdle,
  };
})();
