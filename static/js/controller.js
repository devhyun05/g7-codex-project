(function () {
  window.Visualizer = window.Visualizer || {};

  const api = window.Visualizer.api;
  const domApi = window.Visualizer.dom;
  const stateApi = window.Visualizer.state;
  const utils = window.Visualizer.utils;
  const codePanel = window.Visualizer.renderers.codePanel;
  const visualPanel = window.Visualizer.renderers.visualPanel;
  const explanationPanel = window.Visualizer.renderers.explanationPanel;
  const flowSidebar = window.Visualizer.renderers.flowSidebar;
  const splitterLayout = window.Visualizer.layout.splitter;

  let dom;
  let state;

  const languageMeta = {
    python: {
      code: "Python code",
      stdin: "Input data",
      hint: "Python keeps the original runtime tracer.",
      placeholder: "Enter Python code here",
      emptyDisplay: "Enter code before running.",
    },
    java: {
      code: "Java code",
      stdin: "System.in",
      hint: "Java compiles and runs with local javac/java, then maps results into the shared UI.",
      placeholder: "class Main { public static void main(String[] args) { } }",
      emptyDisplay: "Enter Java code before running.",
    },
    cpp: {
      code: "C++ code",
      stdin: "stdin",
      hint: "C++ compiles and runs with a local compiler, then uses static step simulation.",
      placeholder: "#include <iostream>\nint main() {\n    return 0;\n}",
      emptyDisplay: "Enter C++ code before running.",
    },
  };

  function initialize() {
    dom = domApi.getRefs();
    state = stateApi.createState();
    splitterLayout.initialize(dom);
    bindEvents();
    dom.languageSelect.value = state.language;
    dom.codeInput.value = state.code;
    dom.stdinInput.value = state.stdin;
    syncLanguageUi();
    resetEditorState();
  }

  function bindEvents() {
    dom.runButton.addEventListener("click", runVisualization);
    dom.languageSelect.addEventListener("change", () => {
      state.language = dom.languageSelect.value || "python";
      syncLanguageUi();
    });
    dom.prevStepButton.addEventListener("click", () => moveStep(-1));
    dom.nextStepButton.addEventListener("click", () => moveStep(1));
    dom.playStepButton.addEventListener("click", togglePlayback);
    dom.editCodeButton.addEventListener("click", returnToEditor);
    dom.homeButton.addEventListener("click", returnToEditor);
    dom.homeButton.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      returnToEditor();
    });
    dom.stepSlider.addEventListener("input", (event) => {
      state.currentIndex = Number(event.target.value);
      renderTraceState();
    });
  }

  function syncDraft() {
    state.language = dom.languageSelect.value || "python";
    state.code = dom.codeInput.value;
    state.stdin = dom.stdinInput.value;
  }

  function syncLanguageUi() {
    const current = languageMeta[state.language] || languageMeta.python;
    dom.codeLabel.textContent = current.code;
    dom.stdinLabel.textContent = current.stdin;
    dom.languageHint.textContent = current.hint;
    dom.codeInput.placeholder = current.placeholder;
  }

  function setClientRunError(error, displayError) {
    state.runResult = stateApi.createRunResult(state.stdin);
    state.runResult.ok = false;
    state.runResult.error = error;
    state.runResult.displayError = displayError;
  }

  function returnToEditor() {
    state.runResult = stateApi.createRunResult(dom.stdinInput.value);
    resetEditorState();
  }

  function syncIdlePanels() {
    const showOutputPanel = Boolean(state.runResult.error || state.runResult.stdout);
    dom.outputPanel.classList.toggle("hidden", !showOutputPanel);
    dom.explanationPanel.classList.add("hidden");
    dom.workspaceLeft.classList.toggle("single-panel", !showOutputPanel);
    dom.workspaceRight.classList.add("single-panel");
  }

  function syncTracePanels() {
    dom.outputPanel.classList.remove("hidden");
    dom.explanationPanel.classList.remove("hidden");
    dom.workspaceLeft.classList.remove("single-panel");
    dom.workspaceRight.classList.remove("single-panel");
  }

  function resetEditorState(message) {
    stopPlayback();
    state.steps = [];
    state.currentIndex = 0;
    state.primaryView = "summary";
    codePanel.syncMode(dom, false);
    configureControls();
    updateHeader(null);
    syncIdlePanels();
    visualPanel.renderIdle(dom);
    flowSidebar.renderIdle(dom, message);
    codePanel.renderIdleOutput(
      dom,
      state.runResult.stdout,
      state.runResult.error,
      state.runResult.displayError ?? state.runResult.error,
    );
    explanationPanel.render(dom, state, null, "summary");
  }

  async function runVisualization() {
    stopPlayback();
    syncDraft();

    if (!state.code.trim()) {
      const current = languageMeta[state.language] || languageMeta.python;
      setClientRunError(current.emptyDisplay, current.emptyDisplay);
      resetEditorState(state.runResult.error);
      return;
    }

    dom.runButton.disabled = true;
    dom.playStepButton.disabled = true;
    dom.runButton.textContent = "Running...";
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 8000);

    try {
      const { payload } = await api.visualizeCode(
        state.code,
        state.stdin,
        state.language,
        controller.signal,
      );
      window.clearTimeout(timeoutId);

      state.language = payload.language || state.language;
      dom.languageSelect.value = state.language;
      state.code = payload.code || state.code;
      state.stdin = payload.stdin || state.stdin;
      state.steps = payload.steps || [];
      state.currentIndex = 0;
      const rawError = payload.error || null;
      state.runResult = {
        ok: Boolean(payload.ok),
        error: rawError,
        displayError: payload.display_error ?? payload.displayError ?? rawError,
        stdout: payload.stdout || "",
        stdin: payload.stdin || state.stdin,
        analysis: payload.analysis || stateApi.createAnalysis(),
      };
      dom.codeInput.value = state.code;
      dom.stdinInput.value = state.stdin;
      syncLanguageUi();

      if (state.runResult.ok && state.steps.length) {
        renderTraceState();
      } else {
        resetEditorState(payload.error || "No execution steps were created.");
      }
    } catch (error) {
      window.clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        setClientRunError(
          "The request timed out.",
          "The request timed out. Check for an infinite loop or restart the server.",
        );
      } else {
        setClientRunError(
          "Could not reach the local server.",
          "Could not reach the local server. Start the app and try again.",
        );
      }
      resetEditorState(state.runResult.error);
    } finally {
      dom.runButton.disabled = false;
      dom.runButton.textContent = "Run";
    }
  }

  function renderTraceState() {
    codePanel.syncMode(dom, true);
    configureControls();
    syncTracePanels();

    const step = getCurrentStep();
    const previousStep = getPreviousStep();
    const activeFrame = getActiveFrame(step);
    updateHeader(step);
    codePanel.renderCodeView(dom, state.code, step, previousStep);
    flowSidebar.render(dom, step);
    state.primaryView = visualPanel.render(dom, state, step, activeFrame);
    codePanel.renderOutput(
      dom,
      step ? step.stdout || "" : state.runResult.stdout,
      state.runResult.error,
      state.runResult.displayError ?? state.runResult.error,
    );
    explanationPanel.render(dom, state, step, state.primaryView);
  }

  function updateHeader(step) {
    const stepText = state.steps.length
      ? `${state.currentIndex + 1} / ${state.steps.length}`
      : "0 / 0";
    const activeFrame = getActiveFrame(step);

    dom.stepCounter.textContent = stepText;
    dom.functionPill.textContent = activeFrame ? activeFrame.name : "module";
    dom.linePill.textContent = step && step.line ? String(step.line) : "-";
    dom.eventLabel.textContent = step ? utils.formatEvent(step.event) : "idle";
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

  function getPreviousStep() {
    if (!state.steps.length || state.currentIndex <= 0) {
      return null;
    }
    return state.steps[state.currentIndex - 1];
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
