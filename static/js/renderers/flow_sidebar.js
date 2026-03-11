(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function renderIdle(dom, message) {
    dom.flowSidebar.className = "flow-sidebar empty-state";
    dom.flowSidebar.textContent = message || "실행 기록이 생성되면 프레임 흐름이 여기에 표시됩니다.";
  }

  function render(dom, step) {
    if (!step) {
      renderIdle(dom);
      return;
    }

    const globals = step.globals || {};
    const frames = flattenCallTree(step.call_tree, step.stack || []);
    const focusNodeId = findFocusNodeId(step, frames);

    dom.flowSidebar.className = "flow-sidebar";
    dom.flowSidebar.innerHTML = `
      <div class="flow-sidebar-head compact">
        <div>
          <h3>코드 흐름</h3>
          <p>${utils.escapeHtml(describeFrameEvent(step, frames))}</p>
        </div>
        <span class="flow-badge">${frames.length} calls</span>
      </div>
      <div class="flow-sidebar-body compact">
        <section class="flow-column">
          <div class="flow-column-head">
            <span>Frames</span>
          </div>
          ${buildGlobalFrame(globals)}
          ${frames.length
            ? frames.map((frame, index) => buildFrameRow(frame, index, focusNodeId)).join("")
            : '<article class="flow-row muted"><p>호출된 함수가 없습니다.</p></article>'}
        </section>
      </div>
    `;

    syncFocusIntoView(dom.flowSidebar, focusNodeId);
  }

  function isTreeTraversalFrame(frame) {
    const name = String((frame && frame.name) || "").trim().toLowerCase();
    return [
      "inorder",
      "preorder",
      "postorder",
      "levelorder",
      "level_order",
    ].includes(name);
  }

  function buildGlobalFrame(globals) {
    const entries = Object.entries(globals)
      .filter(([name]) => name !== "__builtins__")
      .slice(0, 4);

    return `
      <article class="flow-row global">
        <div class="flow-row-head">
          <strong>Global frame</strong>
          <span class="flow-status idle">global</span>
        </div>
        ${entries.length ? buildMiniBindingList(entries) : '<p class="flow-empty">전역 변수 없음</p>'}
      </article>
    `;
  }

  function buildFrameRow(frame, index, focusNodeId) {
    const isFocused = frame.id === focusNodeId;
    const isInit = isInitFrame(frame);
    const isTraversal = isTreeTraversalFrame(frame);
    const status = frame.active ? "active" : frame.status || "running";
    const statusLabel = status === "returned"
      ? "return"
      : status === "exception"
        ? "error"
        : status === "active"
          ? "active"
          : "running";
    const classes = [
      "flow-row",
      "frame-row",
      "frame-card",
      isInit ? "init-compact" : "",
      isTraversal ? "traversal-compact" : "",
      isFocused ? "focused" : "",
      `status-${statusLabel}`,
    ].filter(Boolean).join(" ");
    const localEntries = Object.entries(frame.locals || {})
      .filter(([name, value]) => !name.startsWith("__") && !isFunctionLikeValue(value))
      .slice(0, 8);
    const compactInitEntries = buildCompactInitEntries(localEntries);

    if (isInit) {
      return `
        <article
          class="${classes}"
          data-node-id="${utils.escapeHtml(frame.id)}"
          style="--depth:${frame.depth};"
        >
          <div class="flow-row-main">
            <strong class="flow-init-title">${utils.escapeHtml(frame.name)}</strong>
            ${compactInitEntries.length
              ? buildMiniBindingList(compactInitEntries, formatInitValue)
              : '<p class="flow-empty">지역 변수 없음</p>'}
          </div>
        </article>
      `;
    }

    if (isTraversal) {
      const traversalEntry = getTraversalNodeEntry(frame);
      return `
        <article
          class="${classes}"
          data-node-id="${utils.escapeHtml(frame.id)}"
          style="--depth:${frame.depth};"
        >
          <div class="flow-row-main">
            <strong class="flow-init-title">${utils.escapeHtml(frame.name)}</strong>
            ${traversalEntry
              ? buildMiniBindingList([traversalEntry], formatTraversalValue)
              : '<p class="flow-empty">지역 변수 없음</p>'}
          </div>
        </article>
      `;
    }

    return `
      <article
        class="${classes}"
        data-node-id="${utils.escapeHtml(frame.id)}"
        style="--depth:${frame.depth};"
      >
        <div class="flow-row-main">
          <div class="flow-row-head">
            <div class="flow-title-block">
              <div class="flow-chip-row">
                <span class="flow-label">f${index + 1}</span>
                <span class="flow-label subtle">depth ${frame.depth}</span>
              </div>
              <strong>${utils.escapeHtml(frame.name)}</strong>
            </div>
            <div class="flow-meta-block">
              <span class="flow-status ${statusLabel}">${utils.escapeHtml(statusLabel)}</span>
              <span class="flow-line">line ${frame.line ?? "-"}</span>
            </div>
          </div>
          ${localEntries.length ? buildMiniBindingList(localEntries) : '<p class="flow-empty">지역 변수 없음</p>'}
          ${buildReturnLine(frame)}
        </div>
      </article>
    `;
  }

  function buildMiniBindingList(
    entries,
    valueFormatter = (_name, value) => formatValue(value),
  ) {
    return `
      <dl class="mini-binding-list">
        ${entries
          .map(
            ([name, value]) => `
              <div class="mini-binding-row">
                <dt>${utils.escapeHtml(name)}</dt>
                <dd>${utils.escapeHtml(valueFormatter(name, value))}</dd>
              </div>
            `,
          )
          .join("")}
      </dl>
    `;
  }

  function buildReturnLine(frame) {
    if (frame.returnValue == null) {
      return "";
    }

    const rendered = String(frame.returnValue).trim();
    if (rendered === "True" || rendered === "False") {
      return "";
    }

    return `
      <p class="flow-return">
        <span class="flow-return-label">return</span>
        <span>${utils.escapeHtml(rendered)}</span>
      </p>
    `;
  }

  function buildObjectSummary(globals, stack) {
    const objectEntries = [];

    Object.entries(globals).forEach(([name, value]) => {
      if (value && value.type === "function") {
        objectEntries.push({
          name,
          kind: "function",
          detail: value.repr || "<function>",
        });
      }
    });

    stack.forEach((frame) => {
      Object.entries(frame.locals || {}).forEach(([name, value]) => {
        if (isStructuredValue(value)) {
          objectEntries.push({
            name,
            kind: value.type || "object",
            detail: value.repr || formatValue(value),
          });
        }
      });
    });

    if (!objectEntries.length) {
      return '<article class="flow-row muted"><p>객체 요약 없음</p></article>';
    }

    return objectEntries
      .slice(0, 8)
      .map(
        (entry) => `
          <article class="flow-row object-row">
            <div class="flow-row-head">
              <strong>${utils.escapeHtml(entry.name)}</strong>
              <span class="flow-status idle">${utils.escapeHtml(entry.kind)}</span>
            </div>
            <p class="flow-signature">${utils.escapeHtml(entry.detail)}</p>
          </article>
        `,
      )
      .join("");
  }

  function flattenCallTree(root, stack) {
    if (!root || !Array.isArray(root.children)) {
      return [];
    }

    const frames = [];
    const stackLocalsByNodeId = new Map(
      (stack || [])
        .filter((frame) => frame && frame.node_id)
        .map((frame) => [frame.node_id, frame.locals || {}]),
    );

    root.children.forEach((child) => visitNode(child, 1, frames, stackLocalsByNodeId));
    return frames;
  }

  function visitNode(node, depth, frames, stackLocalsByNodeId) {
    frames.push({
      id: node.id,
      name: extractFunctionName(node.label),
      label: node.label || "",
      line: node.line,
      depth,
      active: Boolean(node.active),
      status: node.status || "running",
      returnValue: node.return_value || null,
      locals: stackLocalsByNodeId.get(node.id) || node.locals || {},
    });

    (node.children || []).forEach((child) => visitNode(child, depth + 1, frames, stackLocalsByNodeId));
  }

  function findFocusNodeId(step, frames) {
    if (!frames.length) {
      return null;
    }

    const stackFrames = step && Array.isArray(step.stack) ? step.stack : [];
    const stackTop = stackFrames.length ? stackFrames[stackFrames.length - 1] : null;
    if (stackTop && stackTop.node_id) {
      return stackTop.node_id;
    }

    const active = [...frames].reverse().find((frame) => frame.active);
    if (active) {
      return active.id;
    }

    const running = [...frames].reverse().find(
      (frame) => frame.status === "active" || frame.status === "running",
    );
    return running ? running.id : frames[frames.length - 1].id;
  }

  function describeFrameEvent(step, frames) {
    const focused = frames.find((frame) => frame.id === findFocusNodeId(step, frames));
    if (!focused) {
      return "실행 중인 호출 흐름을 표시합니다.";
    }

    if (step.event === "return") {
      return `${focused.name} 가 반환되었고, 직전 호출 위치로 돌아갑니다.`;
    }

    if (step.event === "exception") {
      return `${focused.name} 에서 예외가 발생했습니다.`;
    }

    if (step.event === "line") {
      return `${focused.name} 실행 중입니다. 현재 줄과 함께 프레임 흐름을 따라갑니다.`;
    }

    return "실행 중인 호출 흐름을 표시합니다.";
  }

  function extractFunctionName(label) {
    if (!label) {
      return "frame";
    }

    const firstChunk = label.split("(")[0].trim();
    return firstChunk || label;
  }

  function isStructuredValue(value) {
    if (!value || typeof value !== "object") {
      return false;
    }

    return Array.isArray(value.items) || Array.isArray(value.attributes) || value.type === "dict";
  }

  function formatValue(value) {
    if (value == null) {
      return "";
    }

    if (typeof value === "string") {
      return trimText(normalizeFunctionRepr(value), 110);
    }

    if (typeof value === "object") {
      if (Object.prototype.hasOwnProperty.call(value, "repr")) {
        return trimText(normalizeFunctionRepr(value.repr || ""), 110);
      }
      return trimText(normalizeFunctionRepr(JSON.stringify(value)), 110);
    }

    return String(value);
  }

  function getTraversalNodeEntry(frame) {
    if (!frame || !frame.locals || !Object.prototype.hasOwnProperty.call(frame.locals, "node")) {
      return null;
    }
    return ["node", frame.locals.node];
  }

  function formatTraversalValue(name, value) {
    if (name !== "node") {
      return formatValue(value);
    }
    const text = summarizeTreeNodePointer(value);
    return text || "";
  }

  function summarizeTreeNodePointer(value) {
    if (!value || typeof value !== "object") {
      return formatValue(value);
    }

    if (Object.prototype.hasOwnProperty.call(value, "value") && value.value == null) {
      return "None";
    }

    const attrs = Array.isArray(value.attributes) ? value.attributes : [];
    const dataAttr = attrs.find((item) => item && item.name === "data");
    if (dataAttr) {
      return formatValue(dataAttr.value);
    }

    const rendered = formatValue(value);
    if (isObjectPointerRepr(rendered)) {
      return "";
    }
    return rendered;
  }

  function formatInitValue(name, value) {
    const rendered = formatValue(value);
    if (name === "self" && isObjectPointerRepr(rendered)) {
      return "";
    }
    return rendered;
  }

  function buildCompactInitEntries(entries) {
    if (!entries.length) {
      return [];
    }
    const ordered = [];
    const preferred = ["self", "data"];
    const used = new Set();

    preferred.forEach((key) => {
      const found = entries.find(([name]) => name === key);
      if (found) {
        ordered.push(found);
        used.add(key);
      }
    });

    entries.forEach((entry) => {
      if (!used.has(entry[0])) {
        ordered.push(entry);
      }
    });

    return ordered.slice(0, 8);
  }

  function isObjectPointerRepr(text) {
    return /^<[^>]+ object at 0x[0-9a-fA-F]+>$/.test(String(text || "").trim());
  }

  function isInitFrame(frame) {
    return Boolean(frame && frame.name === "__init__");
  }

  function normalizeFunctionRepr(text) {
    return String(text || "").replace(
      /<function\s+([^\s>]+)(?:\s+at\s+0x[0-9a-fA-F]+)?>/g,
      (_match, namePath) => `<function ${shortFunctionName(namePath)}>`,
    );
  }

  function shortFunctionName(namePath) {
    const text = String(namePath || "");
    const chunks = text.split(".");
    return chunks[chunks.length - 1] || text;
  }

  function trimText(text, maxLength) {
    if (text.length <= maxLength) {
      return text;
    }
    return `${text.slice(0, maxLength - 1)}…`;
  }

  function isFunctionLikeValue(value) {
    const rendered = formatValue(value);
    return rendered.startsWith("<function ");
  }

  function syncFocusIntoView(container, focusNodeId) {
    if (!focusNodeId) {
      return;
    }

    const target = container.querySelector(`[data-node-id="${focusNodeId}"]`);
    if (!target) {
      return;
    }

    window.requestAnimationFrame(() => {
      target.scrollIntoView({
        block,
        inline: "nearest",
      });
    });
  }

  window.Visualizer.renderers.flowSidebar = {
    focusFrame,
    render,
    renderIdle,
  };
})();
