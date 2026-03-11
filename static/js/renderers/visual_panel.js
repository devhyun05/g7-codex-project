(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function renderIdle(dom, message) {
    dom.stageTitle.textContent = "Visualization";
    dom.stageCaption.textContent =
      message || "Trace output, arrays, and detected structures will appear here.";
    dom.primaryViewLabel.textContent = "SUMMARY";
    dom.primaryStage.className = "visual-stage empty-state";
    dom.primaryStage.textContent = "Run the visualizer to see results here.";
    return "summary";
  }

  function render(dom, state, step, activeFrame) {
    const view = detectPrimaryView(step);
    dom.primaryViewLabel.textContent = utils.formatViewLabel(view);

    if (view === "graph") {
      dom.stageTitle.textContent = "Graph";
      dom.stageCaption.textContent = "Detected graph state from the current execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildSimpleGraphMarkup(step.graph);
      return view;
    }

    if (view === "data-tree") {
      dom.stageTitle.textContent = "Tree";
      dom.stageCaption.textContent = "Detected tree structure from the current execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildTreeMarkup(step.structure.root, step.structure.current_id);
      return view;
    }

    if (view === "array") {
      const arrayState = findArrayState(step);
      dom.stageTitle.textContent = "Array Snapshot";
      dom.stageCaption.textContent = "Showing the most relevant array-like variable captured at this step.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildArrayMarkup(arrayState);
      return view;
    }

    if (view === "stack") {
      dom.stageTitle.textContent = "Stack";
      dom.stageCaption.textContent = "Detected stack state from the current execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildStackMarkup(step.structure);
      return view;
    }

    if (view === "queue") {
      dom.stageTitle.textContent = "Queue";
      dom.stageCaption.textContent = "Detected queue state from the current execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildQueueMarkup(step.structure);
      return view;
    }

    if (view === "call-tree") {
      dom.stageTitle.textContent = "Call Tree";
      dom.stageCaption.textContent = "Showing the current function call flow.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildCallTreeMarkup(step.call_tree);
      return view;
    }

    dom.stageTitle.textContent = state.runResult.ok ? "Summary" : "Run Result";
    dom.stageCaption.textContent = state.runResult.ok
      ? "General execution summary for the current run."
      : "The run finished without trace steps or with an error.";
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
    if (hasRecursiveCallTree(step)) {
      return "call-tree";
    }
    if (step && step.structure && step.structure.kind === "array") {
      return "array";
    }
    if (step && step.structure && step.structure.kind === "stack") {
      return "stack";
    }
    if (step && step.structure && step.structure.kind === "queue") {
      return "queue";
    }
    if (findArrayState(step)) {
      return "array";
    }
    if (hasRecursiveCallTree(step)) {
      return "call-tree";
    }
    if (step && step.call_tree && Array.isArray(step.call_tree.children) && step.call_tree.children.length) {
      return "call-tree";
    }
    return "summary";
  }

  function hasRecursiveCallTree(step) {
    if (!step || !step.call_tree || !Array.isArray(step.call_tree.children) || !step.call_tree.children.length) {
      return false;
    }
    return getMaxCallDepth(step.call_tree) > 1;
  }

  function getMaxCallDepth(node) {
    if (!node || !Array.isArray(node.children) || !node.children.length) {
      return 0;
    }
    return 1 + Math.max(...node.children.map((child) => getMaxCallDepth(child)));
  }

  function findArrayState(step) {
    if (step && step.structure && step.structure.kind === "array") {
      return {
        name: step.structure.name,
        items: step.structure.items || [],
        value: {
          type: "array",
          repr: `[${(step.structure.items || []).join(", ")}]`,
        },
      };
    }

    if (!step || !step.globals) {
      return null;
    }

    return Object.entries(step.globals)
      .map(([name, value]) => ({ name, value }))
      .find(({ value }) => looksArrayLike(value));
  }

  function looksArrayLike(value) {
    if (!value || typeof value !== "object") {
      return false;
    }
    const type = String(value.type || "");
    const repr = String(value.repr || "");
    return type.endsWith("[]") || (repr.startsWith("[") && repr.endsWith("]"));
  }

  function parseArrayItems(repr) {
    return String(repr || "")
      .replace(/^\[/, "")
      .replace(/\]$/, "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function buildSummaryMarkup(step, activeFrame, state) {
    const structures = state.runResult.analysis.structures || [];
    const lineSource = step && step.line_source ? step.line_source.trim() : "";

    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          <article class="summary-card ${state.runResult.ok ? "" : "error"}">
            <span class="summary-label">Status</span>
            <strong>${utils.escapeHtml(state.runResult.ok ? utils.formatEvent(step?.event || "end") : "error")}</strong>
            <p>${utils.escapeHtml((step && step.message) || state.runResult.error || "Ready.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Language</span>
            <strong>${utils.escapeHtml(state.runResult.language.label || "Unknown")}</strong>
            <p>${utils.escapeHtml(state.runResult.language.trace_supported ? "Trace available" : "Detection only")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Current Function</span>
            <strong>${utils.escapeHtml(activeFrame ? activeFrame.name : "module")}</strong>
            <p>${utils.escapeHtml(lineSource || "No active line.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Structures</span>
            <strong>${structures.length}</strong>
            <p>${utils.escapeHtml(structures.length ? state.runResult.analysis.summary : "No detected structure pattern.")}</p>
          </article>
        </div>
      </div>
    `;
  }

  function buildSimpleGraphMarkup(graph) {
    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          <article class="summary-card">
            <span class="summary-label">Graph Name</span>
            <strong>${utils.escapeHtml(graph.name || "graph")}</strong>
            <p>${utils.escapeHtml(`${graph.nodes.length} nodes, ${graph.edges.length} edges`)}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Nodes</span>
            <p>${utils.escapeHtml(graph.nodes.map((node) => node.label).join(", "))}</p>
          </article>
        </div>
      </div>
    `;
  }

  function buildArrayMarkup(arrayState) {
    const items = arrayState.items || parseArrayItems(arrayState.value.repr).slice(0, 8);
    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          <article class="summary-card">
            <span class="summary-label">Variable</span>
            <strong>${utils.escapeHtml(arrayState.name)}</strong>
            <p>${utils.escapeHtml(arrayState.value.type || "array")}</p>
          </article>
        </div>
        <div class="structure-board">
          <div class="queue-visual">
            <div class="queue-end">0</div>
            <div class="queue-lane">
              ${items.length
                ? items
                    .map(
                      (item, index) => `
                        <div class="queue-item ${index === 0 ? "front" : ""}">
                          <strong>${index}</strong><br />${utils.escapeHtml(item)}
                        </div>
                      `,
                    )
                    .join("")
                : '<div class="queue-item">empty</div>'}
            </div>
            <div class="queue-end">${Math.max(items.length - 1, 0)}</div>
          </div>
        </div>
      </div>
    `;
  }

  function buildStackMarkup(structure) {
    const items = structure.items || [];
    return `
      <div class="stage-scroll">
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
                      ].filter(Boolean).join(" ");
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

  function buildTreeMarkup(root, currentId) {
    const rows = [];
    walkTree(root, 0, rows);
    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          ${rows
            .map(
              (node) => `
                <article class="summary-card ${node.id === currentId ? "error" : ""}">
                  <span class="summary-label">Depth ${node.depth}</span>
                  <strong>${utils.escapeHtml(node.label)}</strong>
                  <p>${utils.escapeHtml(node.id === currentId ? "Current node" : "Tree node")}</p>
                </article>
              `,
            )
            .join("")}
        </div>
      </div>
    `;
  }

  function walkTree(node, depth, rows) {
    if (!node) {
      return;
    }
    rows.push({ id: node.id, label: node.label, depth });
    (node.children || []).forEach((child) => walkTree(child, depth + 1, rows));
  }

  function buildCallTreeMarkup(tree) {
    const nodes = [];
    walkCallTree(tree, 0, nodes);
    return `
      <div class="stage-scroll">
        <div class="summary-grid">
          ${nodes
            .map(
              (node) => `
                <article class="summary-card ${node.active ? "error" : ""}">
                  <span class="summary-label">Depth ${node.depth}</span>
                  <strong>${utils.escapeHtml(node.label)}</strong>
                  <p>${utils.escapeHtml(node.status || "running")}</p>
                  ${node.locals ? `<p>${utils.escapeHtml(node.locals)}</p>` : ""}
                  ${node.returnValue ? `<p>returns ${utils.escapeHtml(node.returnValue)}</p>` : ""}
                </article>
              `,
            )
            .join("")}
        </div>
      </div>
    `;
  }

  function walkCallTree(node, depth, rows) {
    if (!node) {
      return;
    }
    rows.push({
      label: node.label,
      active: Boolean(node.active),
      status: node.status,
      locals: summarizeLocals(node.locals),
      returnValue: node.return_value,
      depth,
    });
    (node.children || []).forEach((child) => walkCallTree(child, depth + 1, rows));
  }

  function summarizeLocals(locals) {
    if (!locals || typeof locals !== "object") {
      return "";
    }
    const entries = Object.entries(locals).slice(0, 3);
    if (!entries.length) {
      return "";
    }
    return entries
      .map(([name, value]) => `${name}=${value && value.repr ? value.repr : ""}`)
      .join(", ");
  }

  window.Visualizer.renderers.visualPanel = {
    render,
    renderIdle,
  };
})();
