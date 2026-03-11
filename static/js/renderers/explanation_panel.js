(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function render(dom, state, step, primaryView) {
    const analysis = state.runResult.analysis || { structures: [], summary: "" };
    const structures = analysis.structures || [];
    const language = state.runResult.language || { label: "Unknown", trace_supported: false };
    const runMode = state.runResult.runMode || "trace";
    const traceCapabilities = state.runResult.traceCapabilities;

    if (!step && !structures.length && !state.runResult.error && !state.runResult.stdout) {
      dom.explanationView.className = "support-body empty-state";
      dom.explanationView.textContent = "Start a run to see the explanation panel.";
      return;
    }

    dom.explanationView.className = "support-body explanation-board";
    dom.explanationView.innerHTML = `
      <div class="info-grid">
        ${buildCurrentStepCard(step, state)}
        ${buildLanguageCard(language, runMode)}
        ${buildTracingCard(traceCapabilities)}
        ${buildVariablesCard(step)}
        ${buildLineCard(step)}
        ${buildCurrentStructureCard(step)}
        ${buildStructureCard(structures)}
        ${buildViewCard(primaryView)}
      </div>
    `;
  }

  function buildCurrentStepCard(step, state) {
    const text = step
      ? step.explanation || step.message
      : state.runResult.error
        || (state.runResult.stdout ? "Execution finished." : "The run has not started yet.");
    return buildCard("Current Step", `<p>${utils.escapeHtml(text)}</p>`);
  }

  function buildLanguageCard(language, runMode) {
    const mode = runMode === "execution"
      ? "Executed"
      : language.trace_supported
        ? "Trace available"
        : "Detection only";
    return buildCard(
      "Language",
      `<p><strong>${utils.escapeHtml(language.label || "Unknown")}</strong> · ${utils.escapeHtml(mode)}</p>`,
    );
  }

  function buildTracingCard(traceCapabilities) {
    if (!traceCapabilities) {
      return buildCard("Tracing", "<p>No tracing capability metadata is available yet.</p>");
    }

    return buildCard(
      "Tracing",
      `<p><strong>${utils.escapeHtml(traceCapabilities.status)}</strong> · ${utils.escapeHtml(traceCapabilities.difficulty)}</p><p>${utils.escapeHtml(traceCapabilities.approach)}</p>`,
    );
  }

  function buildLineCard(step) {
    const lineSource = step && step.line_source ? step.line_source : "";
    if (!lineSource) {
      return buildCard("Current Line", "<p>There is no active source line for this state.</p>");
    }

    return buildCard(
      "Current Line",
      `<div class="line-preview">${utils.escapeHtml(lineSource)}</div>`,
    );
  }

  function buildVariablesCard(step) {
    const variables = step && step.globals ? Object.entries(step.globals) : [];
    if (!variables.length) {
      return buildCard("Variables", "<p>No captured variable snapshot for this step.</p>");
    }

    return buildCard(
      "Variables",
      `
        <div class="info-grid">
          ${variables
            .slice(0, 8)
            .map(
              ([name, value]) => `
                <p><strong>${utils.escapeHtml(name)}</strong> = ${utils.escapeHtml(value.repr || "")} <em>(${utils.escapeHtml(value.type || "unknown")})</em></p>
              `,
            )
            .join("")}
        </div>
      `,
    );
  }

  function buildStructureCard(structures) {
    if (!structures.length) {
      return buildCard("Detected Structures", "<p>No supported data structure pattern was found.</p>");
    }

    return buildCard(
      "Detected Structures",
      `
        <div class="tag-row">
          ${structures
            .map(
              (item) => `
                <span class="structure-chip">${utils.escapeHtml(utils.structureKindLabel(item.kind))} · ${utils.escapeHtml(item.name)}</span>
              `,
            )
            .join("")}
        </div>
        <div class="info-grid">
          ${structures
            .map(
              (item) => `
                <p><strong>${utils.escapeHtml(item.name)}</strong> : ${utils.escapeHtml(item.reason)}</p>
              `,
            )
            .join("")}
        </div>
      `,
    );
  }

  function buildCurrentStructureCard(step) {
    const structure = step && step.structure;
    if (!structure) {
      return buildCard("Current Structure", "<p>No active structure visualization was detected for this step.</p>");
    }

    const messages = {
      array: `배열 ${structure.name}의 인덱스별 값을 추적 중입니다.`,
      stack: `스택 ${structure.name}의 top 변화를 추적 중입니다.`,
      queue: `큐 ${structure.name}의 front/back 변화를 추적 중입니다.`,
      tree: `트리 ${structure.name}의 현재 노드 구조를 추적 중입니다.`,
    };

    return buildCard(
      "Current Structure",
      `<p><strong>${utils.escapeHtml(utils.structureKindLabel(structure.kind))}</strong> - ${utils.escapeHtml(messages[structure.kind] || structure.name)}</p>`,
    );
  }

  function buildViewCard(primaryView) {
    return buildCard(
      "Current View",
      `<p>${utils.escapeHtml(utils.describeView(primaryView))}</p>`,
    );
  }

  function buildCard(title, bodyMarkup) {
    return `
      <article class="info-card">
        <h3>${utils.escapeHtml(title)}</h3>
        ${bodyMarkup}
      </article>
    `;
  }

  window.Visualizer.renderers.explanationPanel = {
    render,
  };
})();
