(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function renderIdle(dom, message) {
    dom.stageTitle.textContent = "Visualization";
    dom.stageCaption.textContent =
      message || "Python trace output and detected structures will appear here.";
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
      dom.stageCaption.textContent = "Detected graph state from the current Python execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildSimpleGraphMarkup(step.graph);
      return view;
    }

    if (view === "data-tree") {
      dom.stageTitle.textContent = "Tree";
      dom.stageCaption.textContent = "Detected tree structure from the current Python execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildTreeMarkup(step.structure.root, step.structure.current_id);
      return view;
    }

    if (view === "stack") {
      dom.stageTitle.textContent = "Stack";
      dom.stageCaption.textContent = "Detected stack state from the current Python execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildStackMarkup(step.structure);
      return view;
    }

    if (view === "queue") {
      dom.stageTitle.textContent = "Queue";
      dom.stageCaption.textContent = "Detected queue state from the current Python execution.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildQueueMarkup(step.structure);
      return view;
    }

    if (view === "call-tree") {
      dom.stageTitle.textContent = "Call Tree";
      dom.stageCaption.textContent = "Showing the current Python call flow.";
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
    if (step && step.structure && step.structure.kind === "stack") {
      return "stack";
    }
    if (step && step.structure && step.structure.kind === "queue") {
      return "queue";
    }
    if (step && step.call_tree && Array.isArray(step.call_tree.children) && step.call_tree.children.length) {
      return "call-tree";
    }
    return "summary";
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
      depth,
    });
    (node.children || []).forEach((child) => walkCallTree(child, depth + 1, rows));
  }

  window.Visualizer.renderers.visualPanel = {
    render,
    renderIdle,
  };
})();
