(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;
  const defaultOutputCaption = "선택한 step 시점까지의 stdout과 오류를 보여줍니다.";
  const errorOutputCaption = "실행에 실패한 이유를 보여줍니다.";

  function syncMode(dom, traceMode) {
    dom.editorWrap.classList.toggle("hidden", traceMode);
    dom.codeViewer.classList.toggle("hidden", !traceMode);
    dom.editCodeButton.classList.toggle("hidden", !traceMode);
    dom.editorMetaPills.classList.toggle("hidden", !traceMode);
    dom.editorWrap.classList.toggle("editor-idle", !traceMode);
  }

  function renderCodeView(dom, code, step) {
    const lines = code.split("\n");
    dom.codeViewer.className = "code-viewer";
    dom.codeViewer.innerHTML = lines
      .map((line, index) => {
        const lineNumber = index + 1;
        const active = step && step.line === lineNumber ? "active" : "";
        return `
          <div class="code-line ${active}">
            <span class="code-line-number">${lineNumber}</span>
            <span class="code-line-text">${utils.escapeHtml(line || " ")}</span>
          </div>
        `;
      })
      .join("");

    const activeLine = dom.codeViewer.querySelector(".code-line.active");
    if (activeLine) {
      activeLine.scrollIntoView({ block: "center", inline: "nearest" });
    }
  }

  function renderOutput(dom, stdout, error) {
    const hasError = Boolean(error);

    dom.outputPanelTitle.textContent = hasError ? "에러 메시지" : "출력";
    dom.outputPanelCaption.textContent = hasError ? errorOutputCaption : defaultOutputCaption;
    dom.outputStatus.textContent = hasError ? "ERROR" : stdout ? "STDOUT" : "IDLE";
    dom.outputStatus.classList.toggle("chip-error", hasError);
    dom.outputView.className = hasError
      ? "support-body output-body output-error-body"
      : "support-body output-body";
    dom.outputView.innerHTML = hasError
      ? `<div class="output-error">${utils.escapeHtml(error)}</div>`
      : `<pre class="stdout-pre">${utils.escapeHtml(stdout || "출력이 없습니다.")}</pre>`;
  }

  function renderIdleOutput(dom, stdout = "", error = null) {
    renderOutput(dom, stdout, error);
  }

  window.Visualizer.renderers.codePanel = {
    renderCodeView,
    renderIdleOutput,
    renderOutput,
    syncMode,
  };
})();
