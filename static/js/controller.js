(function () {
  window.Visualizer = window.Visualizer || {};

  const api = window.Visualizer.api;
  const browserTracers = window.Visualizer.browserTracers;
  const domApi = window.Visualizer.dom;
  const stateApi = window.Visualizer.state;
  const utils = window.Visualizer.utils;
  const codePanel = window.Visualizer.renderers.codePanel;
  const visualPanel = window.Visualizer.renderers.visualPanel;
  const explanationPanel = window.Visualizer.renderers.explanationPanel;

  let dom;
  let state;

  function initialize() {
    dom = domApi.getRefs();
    state = stateApi.createState();
    bindEvents();
    dom.codeInput.value = state.code;
    dom.stdinInput.value = state.stdin;
    dom.languageSelect.value = state.language;
    resetEditorState();
  }

  function bindEvents() {
    dom.runButton.addEventListener("click", runVisualization);
    dom.prevStepButton.addEventListener("click", () => moveStep(-1));
    dom.nextStepButton.addEventListener("click", () => moveStep(1));
    dom.playStepButton.addEventListener("click", togglePlayback);
    dom.editCodeButton.addEventListener("click", () => {
      state.runResult = stateApi.createRunResult(dom.stdinInput.value);
      resetEditorState();
    });
    dom.stepSlider.addEventListener("input", (event) => {
      state.currentIndex = Number(event.target.value);
      renderTraceState();
    });
    dom.languageSelect.addEventListener("change", (event) => {
      state.language = event.target.value;
      updateHeader(getCurrentStep());
      explanationPanel.render(dom, state, getCurrentStep(), state.primaryView);
    });
  }

  function syncDraft() {
    state.code = dom.codeInput.value;
    state.stdin = dom.stdinInput.value;
    state.language = dom.languageSelect.value;
  }

  function resetEditorState(message) {
    stopPlayback();
    state.steps = [];
    state.currentIndex = 0;
    state.primaryView = "summary";
    codePanel.syncMode(dom, false);
    configureControls();
    updateHeader(null);
    visualPanel.renderIdle(dom, message);
    codePanel.renderIdleOutput(dom, state.runResult.stdout, state.runResult.error);
    explanationPanel.render(dom, state, null, "summary");
  }

  async function runVisualization() {
    stopPlayback();
    syncDraft();

    if (!state.code.trim()) {
      state.runResult = stateApi.createRunResult(state.stdin);
      state.runResult.error = "Please enter code to visualize.";
      resetEditorState(state.runResult.error);
      return;
    }

    dom.runButton.disabled = true;
    dom.playStepButton.disabled = true;
    dom.runButton.textContent = "Running...";
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 8000);

    try {
      const payload = shouldRunJavaScriptInBrowser(state)
        ? browserTracers.runJavaScriptTrace(state.code, state.stdin)
        : (await api.visualizeCode(
          state.code,
          state.stdin,
          state.language,
          controller.signal,
        )).payload;
      window.clearTimeout(timeoutId);

      state.code = payload.code || state.code;
      state.stdin = payload.stdin || state.stdin;
      state.steps = payload.steps || [];
      state.currentIndex = 0;
      state.runResult = {
        ok: Boolean(payload.ok),
        error: payload.error || null,
        stdout: payload.stdout || "",
        stdin: payload.stdin || state.stdin,
        runMode: payload.run_mode || "trace",
        language: payload.language || stateApi.createLanguage(),
        traceCapabilities: payload.trace_capabilities || null,
        supportedLanguages: payload.supported_languages || [],
        analysis: payload.analysis || stateApi.createAnalysis(),
      };
      dom.codeInput.value = state.code;
      dom.stdinInput.value = state.stdin;

      if (state.steps.length) {
        renderTraceState();
      } else {
        resetEditorState(
          payload.error
            || (state.runResult.runMode === "execution"
              ? "Execution finished without trace steps."
              : "No trace steps were created."),
        );
      }
    } catch (error) {
      window.clearTimeout(timeoutId);
      state.runResult = stateApi.createRunResult(state.stdin);
      state.runResult.error = error.name === "AbortError"
        ? "The request timed out. Check whether the Flask server is still running."
        : "Could not reach the server. Start the app before trying again.";
      resetEditorState(state.runResult.error);
    } finally {
      dom.runButton.disabled = false;
      dom.runButton.textContent = "Run";
    }
  }

  function renderTraceState() {
    codePanel.syncMode(dom, true);
    configureControls();

    const step = getCurrentStep();
    const activeFrame = getActiveFrame(step);
    updateHeader(step);
    codePanel.renderCodeView(dom, state.code, step);
    state.primaryView = visualPanel.render(dom, state, step, activeFrame);
    codePanel.renderOutput(
      dom,
      step ? step.stdout || state.runResult.stdout : state.runResult.stdout,
      state.runResult.error,
    );
    explanationPanel.render(dom, state, step, state.primaryView);
  }

  function updateHeader(step) {
    const stepText = state.steps.length
      ? `${state.currentIndex + 1} / ${state.steps.length}`
      : "0 / 0";
    const activeFrame = getActiveFrame(step);

    dom.stepCounter.textContent = stepText;
    dom.languagePill.textContent = formatLanguagePill();
    dom.functionPill.textContent = activeFrame ? activeFrame.name : "module";
    dom.linePill.textContent = step && step.line ? String(step.line) : "-";
    dom.eventLabel.textContent = step
      ? utils.formatEvent(step.event)
      : state.runResult.error
        ? "error"
        : "idle";
  }

  function formatLanguagePill() {
    const language = state.runResult.language;
    if (language && language.key !== "unknown") {
      if (state.runResult.runMode === "execution") {
        return `${language.label} RUN`;
      }
      return language.trace_supported
        ? `${language.label} TRACE`
        : `${language.label} DETECTED`;
    }

    return state.language === "auto" ? "AUTO" : state.language.toUpperCase();
  }

  function shouldRunJavaScriptInBrowser(currentState) {
    if (currentState.language === "javascript") {
      return true;
    }

    if (currentState.language !== "auto") {
      return false;
    }

    return looksLikeJavaScript(currentState.code);
  }

  function looksLikeJavaScript(code) {
    const text = code || "";
    return [
      "console.log(",
      "function ",
      "let ",
      "const ",
      "=>",
    ].some((needle) => text.includes(needle));
  }

  function configureControls() {
    const hasSteps = state.steps.length > 0;
    dom.prevStepButton.disabled = !hasSteps;
    dom.playStepButton.disabled = !hasSteps;
    dom.nextStepButton.disabled = !hasSteps;
    dom.stepSlider.disabled = !hasSteps;
    dom.stepSlider.min = 0;
    dom.stepSlider.max = hasSteps ? String(state.steps.length - 1) : "0";
    dom.stepSlider.value = hasSteps ? String(state.currentIndex) : "0";
  }

  function moveStep(direction) {
    if (!state.steps.length) {
      return;
    }

    const nextIndex = Math.min(
      state.steps.length - 1,
      Math.max(0, state.currentIndex + direction),
    );
    state.currentIndex = nextIndex;
    renderTraceState();
  }

  function togglePlayback() {
    if (state.timer) {
      stopPlayback();
      return;
    }

    if (!state.steps.length) {
      return;
    }

    if (state.currentIndex >= state.steps.length - 1) {
      state.currentIndex = 0;
      renderTraceState();
    }

    dom.playStepButton.textContent = "Pause";
    state.timer = window.setInterval(() => {
      if (state.currentIndex >= state.steps.length - 1) {
        stopPlayback();
        return;
      }
      state.currentIndex += 1;
      renderTraceState();
    }, 900);
  }

  function stopPlayback() {
    if (state.timer) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
    dom.playStepButton.textContent = "Play";
  }

  function getCurrentStep() {
    if (!state.steps.length) {
      return null;
    }
    return state.steps[state.currentIndex];
  }

  function getActiveFrame(step) {
    if (!step || !Array.isArray(step.stack) || !step.stack.length) {
      return null;
    }
    return step.stack[step.stack.length - 1];
  }

  window.Visualizer.controller = {
    initialize,
  };
})();
