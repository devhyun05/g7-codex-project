(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function render(dom, state, step) {
    const explanationJson = step && step.explanation_json;

    if (!explanationJson && !state.runResult.error) {
      dom.explanationView.className = "support-body empty-state";
      dom.explanationView.textContent = "실행을 시작하면 설명이 여기에 표시됩니다.";
      return;
    }

    dom.explanationView.className = "support-body explanation-board";
    dom.explanationView.innerHTML = explanationJson
      ? buildExplanationMarkup(explanationJson, step)
      : buildErrorMarkup(state.runResult.error || "설명을 만들지 못했습니다.");
  }

  function buildExplanationMarkup(explanationJson, step) {
    const currentLine = step && step.line ? step.line : null;
    const summary = explanationJson.summary || "코드 설명을 준비 중입니다.";
    const lineExplanations = Array.isArray(explanationJson.line_explanations)
      ? explanationJson.line_explanations
      : [];
    const improvements = Array.isArray(explanationJson.improvements)
      ? explanationJson.improvements
      : [];
    const currentExplanation = lineExplanations.find((item) => item.line === currentLine) || null;

    return `
      <div class="info-grid explanation-json-board">
        ${buildCard("요약", `<p>${utils.escapeHtml(summary)}</p>`)}
        ${buildCurrentLineCard(currentExplanation, currentLine)}
        ${buildImprovementCard(improvements)}
      </div>
    `;
  }

  function buildCurrentLineCard(currentExplanation, currentLine) {
    if (!currentExplanation) {
      return buildCard("현재 줄 해석", "<p>현재 실행 중인 줄의 설명을 아직 만들지 못했습니다.</p>");
    }

    return buildCard(
      "현재 줄 해석",
      `
        <article class="line-explanation-item active">
          <div class="line-explanation-head">
            <span class="line-chip">line ${currentLine}</span>
            <span class="line-chip accent">current</span>
          </div>
          <pre class="line-explanation-code">${utils.escapeHtml(currentExplanation.code || "")}</pre>
          <p class="line-explanation-text">${utils.escapeHtml(currentExplanation.description || "")}</p>
        </article>
      `,
    );
  }

  function buildImprovementCard(improvements) {
    if (!improvements.length) {
      return buildCard("개선 포인트", "<p>코드에서 바로 보이는 개선 포인트는 없습니다.</p>");
    }

    return buildCard(
      "개선 포인트",
      `
        <div class="improvement-list">
          ${improvements
            .map((item) => `<p class="improvement-item">${utils.escapeHtml(item)}</p>`)
            .join("")}
        </div>
      `,
    );
  }

  function buildErrorMarkup(errorMessage) {
    return buildCard("오류", `<p>${utils.escapeHtml(errorMessage)}</p>`);
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
