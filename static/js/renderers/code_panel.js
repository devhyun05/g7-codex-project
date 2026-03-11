(function () {
  window.Visualizer = window.Visualizer || {};
  window.Visualizer.renderers = window.Visualizer.renderers || {};

  const utils = window.Visualizer.utils;

  function syncMode(dom, traceMode) {
    dom.editorWrap.classList.toggle("hidden", traceMode);
    dom.codeViewer.classList.toggle("hidden", !traceMode);
    dom.editCodeButton.classList.toggle("hidden", !traceMode);
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
    dom.outputStatus.textContent = error ? "ERROR" : stdout ? "STDOUT" : "IDLE";
    dom.outputView.className = "support-body output-body";
    dom.outputView.innerHTML = `
      <pre class="stdout-pre">${utils.escapeHtml(stdout || "출력이 없습니다.")}</pre>
      ${error ? `<div class="output-error">${utils.escapeHtml(error)}</div>` : ""}
    `;
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
