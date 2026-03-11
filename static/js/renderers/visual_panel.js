(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;
  let idleSearchQuery = "";
  const TREE_ZOOM_MIN = 0.2;
  const TREE_ZOOM_MAX = 2.4;
  const TREE_ZOOM_STEP = 0.2;
  const treeZoomState = {
    "data-tree": 1,
    "call-tree": 1,
  };
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
    idleSearchQuery = "";
    dom.stageTitle.textContent = "시각화 가능한 자료 구조";
    dom.stageCaption.textContent = "실행하면 감지된 항목에 맞춰 이 영역이 자동으로 전환됩니다.";
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

    if (view === "sorting") {
      dom.stageTitle.textContent = "정렬 시각화";
      dom.stageCaption.textContent = "정렬 대상 배열의 값 변화를 막대 그래프로 보여줍니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildSortingMarkup(sortingState);
      attachSortingInteractions(dom);
      return view;
    }

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
      dom.primaryStage.innerHTML = buildDataTreeMarkup(step.structure, getTreeZoom("data-tree"));
      attachTreeInteractions(dom, "data-tree");
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
      const sortingIntent = Boolean(
        state &&
          state.runResult &&
          state.runResult.analysis &&
          state.runResult.analysis.intents &&
          state.runResult.analysis.intents.sorting,
      );
      dom.stageTitle.textContent = "호출 트리";
      dom.stageCaption.textContent = sortingIntent
        ? "정렬 알고리즘 실행으로 판단되어 Visualgo처럼 호출 트리를 우선 보여줍니다."
        : "특정 자료구조보다 재귀 호출 흐름이 더 뚜렷해 호출 트리를 보여줍니다.";
      dom.primaryStage.className = "visual-stage";
      dom.primaryStage.innerHTML = buildCallTreeMarkup(step.call_tree, getTreeZoom("call-tree"));
      attachTreeInteractions(dom, "call-tree");
      attachCallTreeFrameLinking(dom);
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

  function detectPrimaryView(step, state, sortingState) {
    if (shouldPreferSortingBars(step, state, sortingState)) {
      return "sorting";
    }

    if (shouldPreferSortingCallTree(step, state)) {
      return "call-tree";
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

  function shouldPreferSortingCallTree(step, state) {
    if (!step || !step.call_tree || !Array.isArray(step.call_tree.children)) {
      return false;
    }
    if (!step.call_tree.children.length) {
      return false;
    }
    const intents = state && state.runResult && state.runResult.analysis
      ? state.runResult.analysis.intents
      : null;
    return Boolean(intents && intents.sorting);
  }

  function shouldPreferSortingBars(step, state, sortingState) {
    const intents = state && state.runResult && state.runResult.analysis
      ? state.runResult.analysis.intents
      : null;
    const stackTop = step && Array.isArray(step.stack) && step.stack.length
      ? step.stack[step.stack.length - 1]
      : null;
    const stackLooksSorting = Boolean(
      stackTop &&
        typeof stackTop.name === "string" &&
        stackTop.name.toLowerCase().includes("sort"),
    );
    if (!(intents && intents.sorting) && !stackLooksSorting) {
      return false;
    }
    return Boolean(sortingState || stackLooksSorting || (intents && intents.sorting));
  }

  function extractSortingState(step, state) {
    const fromCurrent = findSortingStateInStep(step, state, true);
    if (fromCurrent) {
      return fromCurrent;
    }

    const nearby = findNearbySortingState(state);
    if (nearby) {
      return nearby;
    }
    return null;
  }

  function findSortingStateInStep(step, state, includeDiff) {
    if (!step) {
      return null;
    }

    const topFrame = step.stack && step.stack.length
      ? step.stack[step.stack.length - 1]
      : null;
    const localCandidate = topFrame ? findNumericListCandidate(topFrame.locals, "locals") : null;
    const globalCandidate = findNumericListCandidate(step.globals, "globals");
    const candidate = pickBetterCandidate(localCandidate, globalCandidate);
    if (!candidate) {
      return null;
    }

    return {
      ...candidate,
      changedIndices: includeDiff
        ? detectChangedIndices(
            state && Array.isArray(state.steps) && state.currentIndex > 0
              ? findCandidateValues(state.steps[state.currentIndex - 1], candidate.scope, candidate.name)
              : null,
            candidate.compareValues,
          )
        : [],
      sortedIndices: detectSortedIndices(
        candidate.compareValues,
        getSortingOrder(state),
        topFrame ? topFrame.locals : null,
      ),
    };
  }

  function findNearbySortingState(state) {
    if (!state || !Array.isArray(state.steps) || !state.steps.length) {
      return null;
    }

    for (let offset = 1; offset < state.steps.length; offset += 1) {
      const leftIndex = state.currentIndex - offset;
      if (leftIndex >= 0) {
        const leftState = findSortingStateInStep(state.steps[leftIndex], state, false);
        if (leftState) {
          return leftState;
        }
      }

      const rightIndex = state.currentIndex + offset;
      if (rightIndex < state.steps.length) {
        const rightState = findSortingStateInStep(state.steps[rightIndex], state, false);
        if (rightState) {
          return rightState;
        }
      }
    }
    return null;
  }

  function pickBetterCandidate(left, right) {
    if (!left) {
      return right;
    }
    if (!right) {
      return left;
    }
    if (right.values.length > left.values.length) {
      return right;
    }
    return left;
  }

  function findCandidateValues(step, scope, name) {
    if (!step) {
      return null;
    }
    let source = null;
    if (scope === "locals") {
      const topFrame = step.stack && step.stack.length
        ? step.stack[step.stack.length - 1]
        : null;
      source = topFrame ? topFrame.locals : null;
    } else {
      source = step.globals;
    }
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
    if (
      !value ||
      !["list", "tuple"].includes(value.type) ||
      !Array.isArray(value.items) ||
      value.items.length < 2
    ) {
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
        if (
          typeof rawValue !== "string" &&
          typeof rawValue !== "number" &&
          typeof rawValue !== "boolean"
        ) {
          return null;
        }
      } else {
        values.push(numericValue);
      }
      labels.push(String(rawValue));
      compareValues.push(rawValue);
    }

    let displayValues = values;
    if (!allNumeric) {
      displayValues = rankValues(labels);
    }

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

  function getSortingOrder(state) {
    const intents = state && state.runResult && state.runResult.analysis
      ? state.runResult.analysis.intents
      : null;
    if (!intents || !intents.sorting_order) {
      return "unknown";
    }
    return intents.sorting_order;
  }

  function detectSortedIndices(values, sortingOrder, frameLocals) {
    if (!Array.isArray(values) || values.length < 2) {
      return [];
    }

    const byPass = detectBubblePassSortedIndices(values.length, sortingOrder, frameLocals);
    if (byPass) {
      return byPass;
    }

    if (sortingOrder === "asc") {
      return detectAscBubbleFixedSuffix(values);
    }
    if (sortingOrder === "desc") {
      return detectDescBubbleFixedPrefix(values);
    }
    return detectDefaultSortedIndices(values);
  }

  function detectBubblePassSortedIndices(length, sortingOrder, frameLocals) {
    if (!frameLocals || typeof frameLocals !== "object") {
      return null;
    }
    const pass = readNonNegativeInt(frameLocals.i);
    if (pass === null) {
      return null;
    }
    const capped = Math.max(0, Math.min(length, pass + 1));
    if (sortingOrder === "asc") {
      return makeRange(length - capped, length - 1);
    }
    if (sortingOrder === "desc") {
      return makeRange(0, capped - 1);
    }
    return null;
  }

  function readNonNegativeInt(serializedValue) {
    if (!serializedValue || typeof serializedValue !== "object") {
      return null;
    }
    const raw = serializedValue.value;
    if (typeof raw !== "number" || !Number.isInteger(raw) || raw < 0) {
      return null;
    }
    return raw;
  }

  function detectAscBubbleFixedSuffix(values) {
    for (let start = values.length - 1; start >= 0; start -= 1) {
      if (!isNonDecreasing(values, start, values.length - 1)) {
        continue;
      }
      if (!prefixLessOrEqualBoundary(values, start)) {
        continue;
      }
      return makeRange(start, values.length - 1);
    }
    return [];
  }

  function detectDescBubbleFixedPrefix(values) {
    for (let end = 0; end < values.length; end += 1) {
      if (!isNonIncreasing(values, 0, end)) {
        continue;
      }
      if (!suffixLessOrEqualBoundary(values, end)) {
        continue;
      }
      return makeRange(0, end);
    }
    return [];
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

  function makeRange(start, end) {
    if (start > end) {
      return [];
    }
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  }

  function isNonDecreasing(values, start, end) {
    for (let i = start + 1; i <= end; i += 1) {
      if (compareValuesAscending(values[i - 1], values[i]) > 0) {
        return false;
      }
    }
    return true;
  }

  function isNonIncreasing(values, start, end) {
    for (let i = start + 1; i <= end; i += 1) {
      if (compareValuesAscending(values[i - 1], values[i]) < 0) {
        return false;
      }
    }
    return true;
  }

  function prefixLessOrEqualBoundary(values, start) {
    if (start <= 0) {
      return true;
    }
    const boundary = values[start];
    for (let i = 0; i < start; i += 1) {
      if (compareValuesAscending(values[i], boundary) > 0) {
        return false;
      }
    }
    return true;
  }

  function suffixLessOrEqualBoundary(values, end) {
    if (end >= values.length - 1) {
      return true;
    }
    const boundary = values[end];
    for (let i = end + 1; i < values.length; i += 1) {
      if (compareValuesAscending(values[i], boundary) > 0) {
        return false;
      }
    }
    return true;
  }

  function compareValuesAscending(left, right) {
    const leftNumber = normalizeNumericValue(left);
    const rightNumber = normalizeNumericValue(right);
    if (leftNumber !== null && rightNumber !== null) {
      if (leftNumber < rightNumber) {
        return -1;
      }
      if (leftNumber > rightNumber) {
        return 1;
      }
      return 0;
    }
    return String(left).localeCompare(String(right), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function buildSortingMarkup(sortingState) {
    if (!sortingState) {
      return `
        <div class="stage-scroll">
          <div class="structure-board">정렬 대상 배열이 아직 보이지 않습니다. step을 이동해 배열이 생성된 지점을 확인하세요.</div>
        </div>
      `;
    }

    const range = sortingState.max - sortingState.min || 1;
    return `
      <div class="stage-scroll">
        <div class="sorting-board">
          <div class="sorting-bars">
            ${sortingState.values
              .map((value, index) => {
                const normalized = ((value - sortingState.min) / range) * 100;
                const height = Math.round(24 + (normalized / 100) * 200);
                const changed = sortingState.changedIndices.includes(index);
                const sorted = sortingState.sortedIndices.includes(index);
                const statusClass = [changed ? "changed" : "", sorted ? "sorted" : ""]
                  .filter(Boolean)
                  .join(" ");
                return `
                  <div class="sorting-bar-wrap">
                    <div class="sorting-bar ${statusClass}" style="height: ${height}px;">
                      <span class="sorting-value">${utils.escapeHtml(sortingState.labels[index] || String(value))}</span>
                    </div>
                    <span class="sorting-index">${index}</span>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      </div>
    `;
  }

  function attachSortingInteractions(dom) {
    const lane = dom.primaryStage.querySelector(".sorting-bars");
    if (!lane) {
      return;
    }

    if (lane.dataset.scrollEnhanced === "true") {
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
      const delta = event.clientX - startX;
      lane.scrollLeft = startLeft - delta;
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

  function getTreeZoom(view) {
    return treeZoomState[view] || 1;
  }

  function clampTreeZoom(value) {
    return Math.max(TREE_ZOOM_MIN, Math.min(TREE_ZOOM_MAX, value));
  }

  function formatTreeZoom(value) {
    return `${Math.round(value * 100)}%`;
  }

  function applyTreeZoom(svg, zoomLabel, zoom) {
    const baseWidth = Number(svg.dataset.baseWidth || 0);
    const baseHeight = Number(svg.dataset.baseHeight || 0);
    if (!baseWidth || !baseHeight) {
      return;
    }
    svg.style.width = `${Math.round(baseWidth * zoom)}px`;
    svg.style.height = `${Math.round(baseHeight * zoom)}px`;
    if (zoomLabel) {
      zoomLabel.textContent = formatTreeZoom(zoom);
    }
  }

  function attachTreeInteractions(dom, view) {
    const viewport = dom.primaryStage.querySelector("[data-tree-viewport]");
    const svg = dom.primaryStage.querySelector("[data-tree-svg]");
    if (!viewport || !svg) {
      return;
    }

    const zoomInButton = dom.primaryStage.querySelector("[data-tree-zoom='in']");
    const zoomOutButton = dom.primaryStage.querySelector("[data-tree-zoom='out']");
    const zoomResetButton = dom.primaryStage.querySelector("[data-tree-zoom='reset']");
    const zoomLabel = dom.primaryStage.querySelector("[data-tree-zoom-label]");
    let zoom = getTreeZoom(view);
    applyTreeZoom(svg, zoomLabel, zoom);

    const setZoom = (nextZoom) => {
      const clamped = clampTreeZoom(nextZoom);
      if (clamped === zoom) {
        return;
      }
      zoom = clamped;
      treeZoomState[view] = zoom;
      applyTreeZoom(svg, zoomLabel, zoom);
    };

    if (zoomInButton) {
      zoomInButton.addEventListener("click", () => setZoom(zoom + TREE_ZOOM_STEP));
    }
    if (zoomOutButton) {
      zoomOutButton.addEventListener("click", () => setZoom(zoom - TREE_ZOOM_STEP));
    }
    if (zoomResetButton) {
      zoomResetButton.addEventListener("click", () => {
        zoom = 1;
        treeZoomState[view] = zoom;
        applyTreeZoom(svg, zoomLabel, zoom);
      });
    }

    viewport.addEventListener("wheel", (event) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }
      const direction = event.deltaY < 0 ? 1 : -1;
      setZoom(zoom + direction * TREE_ZOOM_STEP);
      event.preventDefault();
    }, { passive: false });
  }

  function attachCallTreeFrameLinking(dom) {
    const clickableNodes = dom.primaryStage.querySelectorAll("[data-call-node-id]");
    if (!clickableNodes.length || !dom.flowSidebar) {
      return;
    }

    clickableNodes.forEach((nodeElement) => {
      const focus = () => {
        const nodeId = nodeElement.getAttribute("data-call-node-id");
        if (!nodeId) {
          return;
        }
        focusFrameCard(dom.flowSidebar, nodeId);
      };

      nodeElement.addEventListener("click", focus);
      nodeElement.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") {
          return;
        }
        event.preventDefault();
        focus();
      });
    });
  }

  function focusFrameCard(flowSidebar, nodeId) {
    const selector = `[data-node-id="${escapeCssValue(nodeId)}"]`;
    const target = flowSidebar.querySelector(selector);
    if (!target) {
      return;
    }

    target.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: "smooth",
    });
    target.classList.remove("flash-focus");
    void target.offsetWidth;
    target.classList.add("flash-focus");
    window.setTimeout(() => {
      target.classList.remove("flash-focus");
    }, 1400);
  }

  function escapeCssValue(text) {
    return String(text || "")
      .replace(/\\/g, "\\\\")
      .replace(/"/g, '\\"');
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
    const normalizedQuery = normalizeGuideSearchQuery(idleSearchQuery);
    return `
      <div class="stage-scroll structure-guide">
        <div class="structure-guide-search">
          <input
            type="search"
            class="structure-guide-search-input"
            placeholder="제목이나 내용으로 검색"
            aria-label="시각화 가능한 자료 구조 검색"
            value="${utils.escapeHtml(idleSearchQuery)}"
            data-guide-search-input
          />
        </div>
        <div class="summary-grid structure-guide-grid" data-guide-grid>
          ${structureGuides
            .map(
              (item) => `
                <article
                  class="summary-card guide-card${guideMatchesQuery(item, normalizedQuery) ? "" : " hidden"}"
                  data-guide-card
                  data-search-text="${utils.escapeHtml(buildGuideSearchText(item))}"
                >
                  <span class="summary-label">${utils.escapeHtml(item.label)}</span>
                  <strong>${utils.escapeHtml(item.title)}</strong>
                  <p><span class="guide-pattern">${utils.escapeHtml(item.pattern)}</span> ${utils.escapeHtml(item.description)}</p>
                </article>
              `,
            )
            .join("")}
        </div>
        <div class="structure-guide-empty${hasGuideMatches(normalizedQuery) ? " hidden" : ""}" data-guide-empty>
          검색 결과가 없습니다. 다른 키워드로 다시 찾아보세요.
        </div>
        <div class="structure-guide-note">
          재귀가 핵심인 코드는 호출 트리로, 특정 구조가 없으면 실행 요약으로 표시됩니다.
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

    const grid = stage.querySelector("[data-guide-grid]");
    const empty = stage.querySelector("[data-guide-empty]");
    if (grid) {
      grid.classList.toggle("hidden", visibleCount === 0);
    }
    if (empty) {
      empty.classList.toggle("hidden", visibleCount !== 0);
    }
  }

  function hasGuideMatches(normalizedQuery) {
    if (!normalizedQuery) {
      return true;
    }
    return structureGuides.some((item) => guideMatchesQuery(item, normalizedQuery));
  }

  function guideMatchesQuery(item, normalizedQuery) {
    if (!normalizedQuery) {
      return true;
    }
    return buildGuideSearchText(item).includes(normalizedQuery);
  }

  function buildGuideSearchText(item) {
    return normalizeGuideSearchQuery(
      [item.label, item.title, item.pattern, item.description].join(" "),
    );
  }

  function normalizeGuideSearchQuery(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
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
    const orderedItems = items
      .map((item, index) => ({ item, index }))
      .reverse();
    return `
      <div class="stage-scroll">
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>top</span>
        </div>
        <div class="structure-board">
          <div class="stack-visual">
            ${orderedItems.length
              ? orderedItems
                  .map(
                    ({ item, index }) => `
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

  function buildDataTreeMarkup(structure, zoom) {
    const layout = buildHierarchyLayout(structure.root);
    return `
      <div class="stage-scroll">
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>현재 노드</span>
        </div>
        <div class="tree-tools">
          <div class="tree-zoom-group">
            <button type="button" class="tree-zoom-button" data-tree-zoom="out" aria-label="축소">-</button>
            <span class="tree-zoom-label" data-tree-zoom-label>${formatTreeZoom(zoom)}</span>
            <button type="button" class="tree-zoom-button" data-tree-zoom="in" aria-label="확대">+</button>
            <button type="button" class="tree-zoom-reset" data-tree-zoom="reset">100%</button>
          </div>
        </div>
        <div class="tree-viewport" data-tree-viewport>
          <svg
            class="tree-svg"
            data-tree-svg
            data-base-width="${layout.width}"
            data-base-height="${layout.height}"
            viewBox="0 0 ${layout.width} ${layout.height}"
            preserveAspectRatio="xMidYMid meet"
            style="width:${Math.round(layout.width * zoom)}px;height:${Math.round(layout.height * zoom)}px;"
          >
            ${layout.edges
              .map(
                (edge) => `
                  <path
                    class="tree-edge"
                    d="M ${edge.from.x} ${edge.from.y + 20} C ${edge.from.x} ${edge.from.y + 66}, ${edge.to.x} ${edge.to.y - 66}, ${edge.to.x} ${edge.to.y - 20}"
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
      </div>
    `;
  }

  function buildCallTreeMarkup(tree, zoom) {
    const normalized = normalizeCallTreeRoot(tree);
    const layout = buildHierarchyLayout(normalized);
    return `
      <div class="stage-scroll">
        <div class="visual-caption">
          <span><span class="legend-dot current"></span>활성 호출</span>
          <span><span class="legend-dot"></span>비활성 호출</span>
        </div>
        <div class="tree-tools">
          <div class="tree-zoom-group">
            <button type="button" class="tree-zoom-button" data-tree-zoom="out" aria-label="축소">-</button>
            <span class="tree-zoom-label" data-tree-zoom-label>${formatTreeZoom(zoom)}</span>
            <button type="button" class="tree-zoom-button" data-tree-zoom="in" aria-label="확대">+</button>
            <button type="button" class="tree-zoom-reset" data-tree-zoom="reset">100%</button>
          </div>
        </div>
        <div class="tree-viewport" data-tree-viewport>
          <svg
            class="tree-svg"
            data-tree-svg
            data-base-width="${layout.width}"
            data-base-height="${layout.height}"
            viewBox="0 0 ${layout.width} ${layout.height}"
            preserveAspectRatio="xMidYMid meet"
            style="width:${Math.round(layout.width * zoom)}px;height:${Math.round(layout.height * zoom)}px;"
          >
            ${layout.edges
              .map(
                (edge) => `
                  <path
                    class="tree-edge"
                    d="M ${edge.from.x} ${edge.from.y + 24} C ${edge.from.x} ${edge.from.y + 72}, ${edge.to.x} ${edge.to.y - 72}, ${edge.to.x} ${edge.to.y - 24}"
                    fill="none"
                  />
                `,
              )
              .join("")}
            ${layout.nodes
              .map(
                (node) => `
                  <g
                    class="tree-node clickable ${node.active ? "active" : ""} ${node.status === "exception" ? "exception" : ""}"
                    data-call-node-id="${utils.escapeXml(String(node.id || ""))}"
                    tabindex="0"
                    role="button"
                    aria-label="${utils.escapeXml(utils.trimLabel(node.label, 19))} 프레임으로 이동"
                    transform="translate(${node.x - 70}, ${node.y - 24})"
                  >
                    <rect rx="14" ry="14" width="140" height="48"></rect>
                    <text x="12" y="20">${utils.escapeXml(utils.trimLabel(node.label, 19))}</text>
                    <text x="12" y="36">${utils.escapeXml(utils.shortStatus(node.status))}</text>
                  </g>
                `,
              )
              .join("")}
          </svg>
        </div>
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
    const xGap = 172;
    const yGap = 116;
    const tracker = { nextX: 96, maxDepth: 0, maxX: 0 };

    function assign(node, depth) {
      tracker.maxDepth = Math.max(tracker.maxDepth, depth);
      const children = node.children || [];

      if (!children.length) {
        node.x = tracker.nextX;
        node.y = 72 + depth * yGap;
        tracker.maxX = Math.max(tracker.maxX, node.x);
        tracker.nextX += xGap;
        return;
      }

      children.forEach((child) => assign(child, depth + 1));
      node.x = utils.average(children.map((child) => child.x));
      node.y = 72 + depth * yGap;
      tracker.maxX = Math.max(tracker.maxX, node.x);
    }

    function collect(node, parent) {
      nodes.push(node);
      if (parent) {
        edges.push({
          from: { x: parent.x, y: parent.y },
          to: { x: node.x, y: node.y },
        });
      }
      (node.children || []).forEach((child) => collect(child, node));
    }

    assign(root, 0);
    collect(root, null);

    return {
      nodes,
      edges,
      width: Math.max(420, tracker.maxX + 108),
      height: Math.max(320, 192 + tracker.maxDepth * yGap),
    };
  }

  window.Visualizer.renderers.visualPanel = {
    render,
    renderIdle,
  };
})();
