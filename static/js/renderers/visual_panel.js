(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;
  let idleSearchQuery = "";

  const structureGuides = [
    { label: "STACK", title: "Stack", pattern: "append + pop / push + pop", description: "Shows the top-first flow of a LIFO container." },
    { label: "QUEUE", title: "Queue", pattern: "deque / queue / poll", description: "Shows front/back movement in FIFO order." },
    { label: "TREE", title: "Tree", pattern: "left / right / children", description: "Builds a node hierarchy from tree-like data." },
    { label: "GRAPH", title: "Graph", pattern: "adjacency list / matrix", description: "Shows nodes, edges, and traversal state." },
  ];

  function renderIdle(dom) {
    idleSearchQuery = "";
    dom.stageTitle.textContent = "Visual Structures";
    dom.stageCaption.textContent = "Detected data structures and execution views appear here.";
    dom.primaryViewLabel.textContent = "GUIDE";
    dom.primaryStage.className = "visual-stage";
    dom.primaryStage.innerHTML = buildStructureGuideMarkup();
    attachGuideSearch(dom);
    return "summary";
  }

  function render(dom, state, step, activeFrame) {
    const sortingState = extractSortingState(step, state);
    const view = detectPrimaryView(step, state, sortingState);
    dom.primaryViewLabel.textContent = utils.formatViewLabel(view);
    syncHeader(dom, state, step, view);

    if (view === "sorting") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildSortingMarkup(state, sortingState);
      attachSortingInteractions(dom);
      return view;
    }

    if (view === "graph") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildGraphMarkup(state, step.graph);
      return view;
    }

    if (view === "data-tree") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildDataTreeMarkup(state, step.structure);
      return view;
    }

    if (view === "stack") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildStackMarkup(state, step.structure);
      return view;
    }

    if (view === "queue") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildQueueMarkup(state, step.structure);
      return view;
    }

    if (view === "call-tree") {
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildCallTreeMarkup(state, step.call_tree);
      attachCallTreeInteractions(dom);
      return view;
    }

    dom.primaryStage.className = "visual-stage";
    dom.primaryStage.innerHTML = buildSummaryMarkup(step, activeFrame, state);
    return view;
  }

  function syncHeader(dom, state, step, view) {
    const map = {
      sorting: {
        title: "Sorting Replay",
        caption: "Array changes are projected into bars so swaps and fixed regions stand out.",
      },
      graph: {
        title: "Graph View",
        caption: "Detected adjacency structures are arranged as a graph layout.",
      },
      "data-tree": {
        title: "Tree View",
        caption: "Tree-like objects are mapped into a hierarchy.",
      },
      stack: {
        title: "Stack View",
        caption: "Top-of-stack state is highlighted at each step.",
      },
      queue: {
        title: "Queue View",
        caption: "Front and back are highlighted in the current queue state.",
      },
      "call-tree": {
        title: "Call Tree",
        caption: "Function nesting and returns are shown as a tree.",
      },
      summary: {
        title: state.runResult.ok ? "Execution Summary" : "Error Summary",
        caption: "A compact overview of the current step and detected structures.",
      },
    };
    const current = map[view] || map.summary;
    dom.stageTitle.textContent = current.title;
    dom.stageCaption.textContent = current.caption;
    if (step && step.event === "error") {
      dom.stageCaption.textContent = "Execution stopped with an error. Review the final state below.";
    }
  }

  function detectPrimaryView(step, state, sortingState) {
    if (shouldPreferSortingBars(step, state, sortingState)) {
      return "sorting";
    }
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

  function shouldPreferSortingBars(step, state, sortingState) {
    const intents = state && state.runResult && state.runResult.analysis
      ? state.runResult.analysis.intents
      : null;
    return Boolean(sortingState && intents && intents.sorting);
  }

  function extractSortingState(step, state) {
    if (!step) {
      return null;
    }
    const candidate = findNumericListCandidate(step.globals, "globals")
      || findNumericListCandidate(getTopFrame(step)?.locals, "locals");
    if (!candidate) {
      return null;
    }
    const previousValues = state && state.currentIndex > 0
      ? findCandidateValues(state.steps[state.currentIndex - 1], candidate.scope, candidate.name)
      : null;
    return {
      ...candidate,
      changedIndices: detectChangedIndices(previousValues, candidate.compareValues),
      sortedIndices: detectDefaultSortedIndices(candidate.compareValues),
    };
  }

  function getTopFrame(step) {
    return step && Array.isArray(step.stack) && step.stack.length
      ? step.stack[step.stack.length - 1]
      : null;
  }

  function findCandidateValues(step, scope, name) {
    if (!step) {
      return null;
    }
    const source = scope === "locals" ? getTopFrame(step)?.locals : step.globals;
    if (!source || !source[name]) {
      return null;
    }
    const parsed = parseNumericList(name, source[name], scope);
    return parsed ? parsed.compareValues : null;
  }

  function findNumericListCandidate(namespace, scope) {
    if (!namespace) {
      return null;
    }
    let best = null;
    Object.entries(namespace).forEach(([name, value]) => {
      const parsed = parseNumericList(name, value, scope);
      if (!parsed) {
        return;
      }
      if (!best || parsed.values.length > best.values.length) {
        best = parsed;
      }
    });
    return best;
  }

  function parseNumericList(name, value, scope) {
    if (!value || !["list", "tuple"].includes(value.type) || !Array.isArray(value.items) || value.items.length < 2) {
      return null;
    }
    const values = [];
    const labels = [];
    const compareValues = [];
    let allNumeric = true;

    for (const item of value.items) {
      if (!item) {
        return null;
      }
      const rawValue = item.value;
      const numericValue = normalizeNumericValue(rawValue);
      if (numericValue === null) {
        allNumeric = false;
        if (typeof rawValue !== "string" && typeof rawValue !== "number" && typeof rawValue !== "boolean") {
          return null;
        }
      } else {
        values.push(numericValue);
      }
      labels.push(String(rawValue));
      compareValues.push(rawValue);
    }

    const displayValues = allNumeric ? values : rankValues(labels);
    return {
      name,
      scope,
      values: displayValues,
      labels,
      compareValues,
      min: Math.min(...displayValues),
      max: Math.max(...displayValues),
    };
  }

  function normalizeNumericValue(value) {
    if (typeof value === "number" && !Number.isNaN(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
    return null;
  }

  function rankValues(labels) {
    const unique = Array.from(new Set(labels)).sort((left, right) =>
      left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }),
    );
    const rankMap = new Map(unique.map((label, index) => [label, index + 1]));
    return labels.map((label) => rankMap.get(label) || 1);
  }

  function detectChangedIndices(previous, current) {
    if (!Array.isArray(previous) || previous.length !== current.length) {
      return [];
    }
    const changed = [];
    for (let index = 0; index < current.length; index += 1) {
      if (previous[index] !== current[index]) {
        changed.push(index);
      }
    }
    return changed;
  }

  function detectDefaultSortedIndices(values) {
    const sorted = [...values].sort(compareValuesAscending);
    const indices = [];
    for (let index = 0; index < values.length; index += 1) {
      if (compareValuesAscending(values[index], sorted[index]) === 0) {
        indices.push(index);
      }
    }
    return indices;
  }

  function compareValuesAscending(left, right) {
    const leftNumber = normalizeNumericValue(left);
    const rightNumber = normalizeNumericValue(right);
    if (leftNumber !== null && rightNumber !== null) {
      return leftNumber === rightNumber ? 0 : leftNumber < rightNumber ? -1 : 1;
    }
    return String(left).localeCompare(String(right), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function buildSummaryMarkup(step, activeFrame, state) {
    const structures = state.runResult.analysis.structures || [];
    const lineSource = step && step.line_source ? step.line_source.trim() : "";
    const stackDepth = step && Array.isArray(step.stack) ? step.stack.length : 0;
    const stdinLines = utils.countInputLines(state.runResult.stdin);
    const language = (state.language || "python").toUpperCase();
    const modeLabel = state.language === "python" ? "Runtime trace" : "Static replay";
    const primaryStructure = structures.length ? `${structures[0].kind}:${structures[0].name}` : "none";

    return `
      <div class="stage-scroll">
        <div class="summary-ribbon">
          <span class="summary-ribbon-chip accent">${utils.escapeHtml(language)}</span>
          <span class="summary-ribbon-chip">${utils.escapeHtml(modeLabel)}</span>
          <span class="summary-ribbon-chip">${utils.escapeHtml(`Primary ${primaryStructure}`)}</span>
        </div>
        <div class="summary-grid">
          <article class="summary-card ${state.runResult.ok ? "" : "error"}">
            <span class="summary-label">Status</span>
            <strong>${utils.escapeHtml(state.runResult.ok ? utils.formatEvent(step?.event || "end") : "error")}</strong>
            <p>${utils.escapeHtml((step && step.message) || state.runResult.error || "Execution is ready.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Focus</span>
            <strong>${utils.escapeHtml(activeFrame ? activeFrame.name : "module")}</strong>
            <p>${utils.escapeHtml(lineSource || "No active source line at this step.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Call Depth</span>
            <strong>${stackDepth}</strong>
            <p>${utils.escapeHtml(stackDepth ? "Frames are active in the current stack." : "No active function frames.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Structures</span>
            <strong>${structures.length}</strong>
            <p>${utils.escapeHtml(structures.length ? state.runResult.analysis.summary : "No structure hints were detected yet.")}</p>
          </article>
          <article class="summary-card">
            <span class="summary-label">Input Lines</span>
            <strong>${stdinLines}</strong>
            <p>${utils.escapeHtml(stdinLines ? "Standard input was consumed during execution." : "This run did not consume stdin.")}</p>
          </article>
          <article class="summary-card standout">
            <span class="summary-label">Visualizer Mode</span>
            <strong>${utils.escapeHtml(modeLabel)}</strong>
            <p>${utils.escapeHtml(describeExecutionMode(state.language || "python"))}</p>
          </article>
        </div>
      </div>
    `;
  }

  function describeExecutionMode(language) {
    if (language === "python") {
      return "Each step comes from the live Python tracer, so locals and frames are exact.";
    }
    if (language === "java") {
      return "Java is compiled and executed locally, then mapped into the shared visual model.";
    }
    if (language === "cpp") {
      return "C++ is compiled and executed locally, then replayed as structure-aware visual steps.";
    }
    return "The shared visualizer pipeline is active.";
  }

  function buildStructureGuideMarkup() {
    const normalizedQuery = normalizeGuideSearchQuery(idleSearchQuery);
    return `
      <div class="stage-scroll structure-guide">
        <div class="structure-guide-search">
          <input
            type="search"
            class="structure-guide-search-input"
            placeholder="Search structures"
            aria-label="Search visual structures"
            value="${utils.escapeHtml(idleSearchQuery)}"
            data-guide-search-input
          />
        </div>
        <div class="summary-grid structure-guide-grid" data-guide-grid>
          ${structureGuides.map((item) => `
            <article
              class="summary-card guide-card${guideMatchesQuery(item, normalizedQuery) ? "" : " hidden"}"
              data-guide-card
              data-search-text="${utils.escapeHtml(buildGuideSearchText(item))}"
            >
              <span class="summary-label">${utils.escapeHtml(item.label)}</span>
              <strong>${utils.escapeHtml(item.title)}</strong>
              <p><span class="guide-pattern">${utils.escapeHtml(item.pattern)}</span> ${utils.escapeHtml(item.description)}</p>
            </article>
          `).join("")}
        </div>
        <div class="structure-guide-empty${hasGuideMatches(normalizedQuery) ? " hidden" : ""}" data-guide-empty>
          No matching structure cards were found.
        </div>
        <div class="structure-guide-note">
          If no structure is detected, the visualizer falls back to a call tree or execution summary.
        </div>
      </div>
    `;
  }

  function attachGuideSearch(dom) {
    const searchInput = dom.primaryStage.querySelector("[data-guide-search-input]");
    if (!searchInput) {
      return;
    }
    searchInput.addEventListener("input", (event) => {
      idleSearchQuery = event.target.value || "";
      filterStructureGuideCards(dom.primaryStage, idleSearchQuery);
    });
    filterStructureGuideCards(dom.primaryStage, idleSearchQuery);
  }

  function filterStructureGuideCards(stage, query) {
    const normalizedQuery = normalizeGuideSearchQuery(query);
    const cards = stage.querySelectorAll("[data-guide-card]");
    let visibleCount = 0;
    cards.forEach((card) => {
      const matched = !normalizedQuery || card.dataset.searchText.includes(normalizedQuery);
      card.classList.toggle("hidden", !matched);
      if (matched) {
        visibleCount += 1;
      }
    });
    stage.querySelector("[data-guide-grid]")?.classList.toggle("hidden", visibleCount === 0);
    stage.querySelector("[data-guide-empty]")?.classList.toggle("hidden", visibleCount !== 0);
  }

  function hasGuideMatches(normalizedQuery) {
    if (!normalizedQuery) {
      return true;
    }
    return structureGuides.some((item) => guideMatchesQuery(item, normalizedQuery));
  }

  function guideMatchesQuery(item, normalizedQuery) {
    return !normalizedQuery || buildGuideSearchText(item).includes(normalizedQuery);
  }

  function buildGuideSearchText(item) {
    return normalizeGuideSearchQuery([item.label, item.title, item.pattern, item.description].join(" "));
  }

  function normalizeGuideSearchQuery(value) {
    return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function buildGraphMarkup(state, graph) {
    const size = 360;
    const center = size / 2;
    const radius = 118;
    const positionedNodes = graph.nodes.map((node, index) => {
      const angle = (Math.PI * 2 * index) / graph.nodes.length - Math.PI / 2;
      return { ...node, x: center + radius * Math.cos(angle), y: center + radius * Math.sin(angle) };
    });
    const positionMap = Object.fromEntries(positionedNodes.map((node) => [node.id, node]));

    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, "Graph detected")}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Current</span>
          <span><span class="legend-dot visited"></span>Visited</span>
          <span><span class="legend-dot"></span>Unvisited</span>
        </div>
        <svg class="graph-svg" viewBox="0 0 440 420" preserveAspectRatio="xMidYMid meet">
          <text class="graph-meta" x="18" y="26">${utils.escapeXml(graph.name)}${graph.tree_mode ? " (tree-like)" : ""}</text>
          ${graph.edges.map((edge) => {
            const source = positionMap[edge.source];
            const target = positionMap[edge.target];
            if (!source || !target) {
              return "";
            }
            return `<line class="graph-edge" x1="${source.x + 40}" y1="${source.y + 24}" x2="${target.x + 40}" y2="${target.y + 24}" />`;
          }).join("")}
          ${positionedNodes.map((node) => `
            <g class="graph-node ${node.visited ? "visited" : ""} ${node.current ? "current" : ""}">
              <circle cx="${node.x + 40}" cy="${node.y + 24}" r="24"></circle>
              <text class="graph-label" x="${node.x + 40}" y="${node.y + 29}" text-anchor="middle">${utils.escapeXml(node.label)}</text>
            </g>
          `).join("")}
        </svg>
      </div>
    `;
  }

  function buildStackMarkup(state, structure) {
    const items = structure.items || [];
    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, `Stack ${structure.name || ""}`)}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Top</span>
        </div>
        <div class="structure-board">
          <div class="stack-visual">
            ${items.length
              ? items.map((item, index) => `
                <div class="stack-item ${index === structure.top_index ? "top" : ""}">
                  <span class="structure-tag">${index === structure.top_index ? "TOP" : `#${index}`}</span>
                  ${utils.escapeHtml(item)}
                </div>
              `).join("")
              : '<div class="stack-item">empty</div>'}
          </div>
        </div>
      </div>
    `;
  }

  function buildQueueMarkup(state, structure) {
    const items = structure.items || [];
    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, `Queue ${structure.name || ""}`)}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Front</span>
          <span><span class="legend-dot visited"></span>Back</span>
        </div>
        <div class="structure-board">
          <div class="queue-visual">
            <div class="queue-end">FRONT</div>
            <div class="queue-lane">
              ${items.length
                ? items.map((item, index) => {
                  const classes = [
                    "queue-item",
                    index === structure.front_index ? "front" : "",
                    index === structure.back_index ? "back" : "",
                  ].filter(Boolean).join(" ");
                  return `<div class="${classes}">${utils.escapeHtml(item)}</div>`;
                }).join("")
                : '<div class="queue-item">empty</div>'}
            </div>
            <div class="queue-end">BACK</div>
          </div>
        </div>
      </div>
    `;
  }

  function buildDataTreeMarkup(state, structure) {
    const layout = buildHierarchyLayout(structure.root);
    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, `Tree ${structure.name || ""}`)}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Current node</span>
        </div>
        <svg class="tree-svg" viewBox="0 0 ${layout.width} ${layout.height}" preserveAspectRatio="xMidYMid meet">
          ${layout.edges.map((edge) => `
            <path class="tree-edge" d="M ${edge.from.x} ${edge.from.y} C ${edge.from.x + 70} ${edge.from.y}, ${edge.to.x - 70} ${edge.to.y}, ${edge.to.x} ${edge.to.y}" fill="none" />
          `).join("")}
          ${layout.nodes.map((node) => `
            <g class="data-tree-node ${node.id === structure.current_id ? "current" : ""}" transform="translate(${node.x - 64}, ${node.y - 20})">
              <rect rx="14" ry="14" width="128" height="40"></rect>
              <text x="12" y="24">${utils.escapeXml(utils.trimLabel(node.label, 17))}</text>
            </g>
          `).join("")}
        </svg>
      </div>
    `;
  }

  function buildCallTreeMarkup(state, tree) {
    const normalized = normalizeCallTreeRoot(tree);
    const layout = buildHierarchyLayout(normalized);
    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, "Call tree")}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Active frame</span>
          <span><span class="legend-dot"></span>Inactive frame</span>
        </div>
        <svg class="tree-svg" viewBox="0 0 ${layout.width} ${layout.height}" preserveAspectRatio="xMidYMid meet">
          ${layout.edges.map((edge) => `
            <path class="tree-edge" d="M ${edge.from.x} ${edge.from.y} C ${edge.from.x + 70} ${edge.from.y}, ${edge.to.x - 70} ${edge.to.y}, ${edge.to.x} ${edge.to.y}" fill="none" />
          `).join("")}
          ${layout.nodes.map((node) => `
            <g
              class="tree-node ${node.active ? "active" : ""} ${node.status === "exception" ? "exception" : ""}"
              data-node-id="${utils.escapeHtml(node.id || "")}"
              tabindex="0"
              role="button"
              aria-label="${utils.escapeHtml(`${node.label || "frame"} frame`)}"
              transform="translate(${node.x - 70}, ${node.y - 24})"
            >
              <rect rx="14" ry="14" width="140" height="48"></rect>
              <text x="12" y="20">${utils.escapeXml(utils.trimLabel(node.label, 19))}</text>
              <text x="12" y="36">${utils.escapeXml(utils.shortStatus(node.status))}</text>
            </g>
          `).join("")}
        </svg>
      </div>
    `;
  }

  function buildSortingMarkup(state, sortingState) {
    if (!sortingState) {
      return `
        <div class="stage-scroll">
          ${buildMetaRibbon(state, "Sorting view")}
          <div class="structure-board">No sortable array was visible in this step.</div>
        </div>
      `;
    }
    const range = sortingState.max - sortingState.min || 1;
    return `
      <div class="stage-scroll">
        ${buildMetaRibbon(state, `Sorting ${sortingState.name}`)}
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>Changed</span>
          <span><span class="legend-dot sorted"></span>Aligned with sorted order</span>
        </div>
        <div class="sorting-board">
          <div class="sorting-bars">
            ${sortingState.values.map((value, index) => {
              const normalized = ((value - sortingState.min) / range) * 100;
              const height = Math.round(24 + (normalized / 100) * 200);
              const changed = sortingState.changedIndices.includes(index);
              const sorted = sortingState.sortedIndices.includes(index);
              const statusClass = [changed ? "changed" : "", sorted ? "sorted" : ""].filter(Boolean).join(" ");
              return `
                <div class="sorting-bar-wrap">
                  <div class="sorting-bar ${statusClass}" style="height: ${height}px;">
                    <span class="sorting-value">${utils.escapeHtml(sortingState.labels[index] || String(value))}</span>
                  </div>
                  <span class="sorting-index">${index}</span>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      </div>
    `;
  }

  function buildMetaRibbon(state, emphasis) {
    const language = (state.language || "python").toUpperCase();
    const modeLabel = state.language === "python" ? "Exact runtime" : "Compiler + replay";
    return `
      <div class="summary-ribbon">
        <span class="summary-ribbon-chip accent">${utils.escapeHtml(language)}</span>
        <span class="summary-ribbon-chip">${utils.escapeHtml(modeLabel)}</span>
        <span class="summary-ribbon-chip">${utils.escapeHtml(emphasis)}</span>
      </div>
    `;
  }

  function attachSortingInteractions(dom) {
    const lane = dom.primaryStage.querySelector(".sorting-bars");
    if (!lane || lane.dataset.scrollEnhanced === "true") {
      return;
    }
    lane.dataset.scrollEnhanced = "true";
    lane.addEventListener("wheel", (event) => {
      if (event.deltaY === 0) {
        return;
      }
      lane.scrollLeft += event.deltaY;
      event.preventDefault();
    }, { passive: false });

    let dragging = false;
    let startX = 0;
    let startLeft = 0;
    lane.addEventListener("pointerdown", (event) => {
      dragging = true;
      startX = event.clientX;
      startLeft = lane.scrollLeft;
      lane.classList.add("dragging");
      lane.setPointerCapture(event.pointerId);
    });
    lane.addEventListener("pointermove", (event) => {
      if (!dragging) {
        return;
      }
      lane.scrollLeft = startLeft - (event.clientX - startX);
    });
    const endDrag = (event) => {
      if (!dragging) {
        return;
      }
      dragging = false;
      lane.classList.remove("dragging");
      if (lane.hasPointerCapture(event.pointerId)) {
        lane.releasePointerCapture(event.pointerId);
      }
    };
    lane.addEventListener("pointerup", endDrag);
    lane.addEventListener("pointercancel", endDrag);
  }

  function normalizeCallTreeRoot(tree) {
    if (tree && tree.label === "module" && Array.isArray(tree.children) && tree.children.length === 1) {
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

  function attachCallTreeInteractions(dom) {
    const svg = dom.primaryStage.querySelector(".tree-svg");
    if (!svg) {
      return;
    }
    const focusFrameCard = (nodeId) => {
      const flowSidebar = window.Visualizer?.renderers?.flowSidebar;
      if (!nodeId || !flowSidebar || typeof flowSidebar.focusFrame !== "function") {
        return;
      }
      flowSidebar.focusFrame(dom, nodeId);
    };
    svg.querySelectorAll(".tree-node[data-node-id]").forEach((node) => {
      node.addEventListener("click", () => focusFrameCard(node.dataset.nodeId));
      node.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") {
          return;
        }
        event.preventDefault();
        focusFrameCard(node.dataset.nodeId);
      });
    });
  }

  window.Visualizer.renderers.visualPanel = {
    render,
    renderIdle,
  };
})();
