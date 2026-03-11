(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function render(dom, state, step, primaryView) {
    const analysis = state.runResult.analysis || { structures: [], summary: "" };
    const structures = analysis.structures || [];

    if (!step && !structures.length && !state.runResult.error) {
      dom.explanationView.className = "support-body empty-state";
      dom.explanationView.textContent = "실행을 시작하면 설명이 여기에 표시됩니다.";
      return;
    }

    dom.explanationView.className = "support-body explanation-board";
    dom.explanationView.innerHTML = `
      <div class="info-grid">
        ${buildCurrentStepCard(step, state)}
        ${buildLineCard(step)}
        ${buildStructureCard(structures)}
        ${buildViewCard(primaryView)}
      </div>
    `;
  }

  function buildCurrentStepCard(step, state) {
    const text = step
      ? step.explanation || step.message
      : state.runResult.error || "아직 실행되지 않았습니다.";
    return buildCard("현재 단계", `<p>${utils.escapeHtml(text)}</p>`);
  }

  function buildLineCard(step) {
    const lineSource = step && step.line_source ? step.line_source : "";
    if (!lineSource) {
      return buildCard("현재 줄", "<p>현재 강조 중인 줄이 없습니다.</p>");
    }

    return buildCard(
      "현재 줄",
      `<div class="line-preview">${utils.escapeHtml(lineSource)}</div>`,
    );
  }

  function buildStructureCard(structures) {
    if (!structures.length) {
      return buildCard("자동 판단", "<p>코드에서 특정 자료구조를 감지하지 못했습니다.</p>");
    }

    return buildCard(
      "자동 판단",
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

  function buildViewCard(primaryView) {
    return buildCard(
      "현재 시각화",
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
