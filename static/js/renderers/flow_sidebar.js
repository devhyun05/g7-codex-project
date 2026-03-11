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
        <section class="flow-column objects-column">
          <div class="flow-column-head">
            <span>Objects</span>
          </div>
          ${buildObjectSummary(globals, step.stack || [])}
        </section>
      </div>
    `;

    syncFocusIntoView(dom.flowSidebar, focusNodeId);
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
      isFocused ? "focused" : "",
      `status-${statusLabel}`,
    ].filter(Boolean).join(" ");
    const localEntries = Object.entries(frame.locals || {});

    return `
      <article
        class="${classes}"
        data-node-id="${utils.escapeHtml(frame.id)}"
        style="--depth:${frame.depth};"
      >
        <div class="flow-row-rail"></div>
        <div class="flow-row-main">
          <div class="flow-row-head">
            <div class="flow-title-block">
              <div class="flow-chip-row">
                <span class="flow-label">f${index + 1}</span>
                <span class="flow-label subtle">depth ${frame.depth}</span>
              </div>
              <strong>${utils.escapeHtml(frame.name)}</strong>
              <p class="flow-signature">${utils.escapeHtml(frame.label || frame.name)}</p>
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

  function buildMiniBindingList(entries) {
    return `
      <dl class="mini-binding-list">
        ${entries
          .map(
            ([name, value]) => `
              <div class="mini-binding-row">
                <dt>${utils.escapeHtml(name)}</dt>
                <dd>${utils.escapeHtml(formatValue(value))}</dd>
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

    return `
      <p class="flow-return">
        <span class="flow-return-label">return</span>
        <span>${utils.escapeHtml(frame.returnValue)}</span>
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

    if (step.event === "return") {
      const returned = [...frames].reverse().find((frame) => frame.status === "returned");
      if (returned) {
        return returned.id;
      }
    }

    if (step.event === "exception") {
      const failed = [...frames].reverse().find((frame) => frame.status === "exception");
      if (failed) {
        return failed.id;
      }
    }

    const active = frames.find((frame) => frame.active);
    return active ? active.id : frames[frames.length - 1].id;
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
      return value;
    }

    if (typeof value === "object") {
      if (Object.prototype.hasOwnProperty.call(value, "repr")) {
        return value.repr || "";
      }
      return JSON.stringify(value);
    }

    return String(value);
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
        block: "nearest",
        inline: "nearest",
      });
    });
  }

  window.Visualizer.renderers.flowSidebar = {
    render,
    renderIdle,
  };
})();
