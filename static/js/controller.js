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

  function initialize() {
    dom = domApi.getRefs();
    state = stateApi.createState();
    splitterLayout.initialize(dom);
    bindEvents();
    dom.codeInput.value = state.code;
    dom.stdinInput.value = state.stdin;
    resetEditorState();
  }

  function bindEvents() {
    dom.runButton.addEventListener("click", runVisualization);
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
    state.code = dom.codeInput.value;
    state.stdin = dom.stdinInput.value;
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

  function resetEditorState(message) {
    stopPlayback();
    state.steps = [];
    state.currentIndex = 0;
    state.primaryView = "summary";
    codePanel.syncMode(dom, false);
    configureControls();
    updateHeader(null);
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
      setClientRunError(
        "시각화할 파이썬 코드를 입력하세요.",
        "실행할 Python 코드를 먼저 입력해 주세요. 코드 입력창에 한 줄 이상 작성한 뒤 다시 실행해 보세요.",
      );
      resetEditorState(state.runResult.error);
      return;
    }

    dom.runButton.disabled = true;
    dom.playStepButton.disabled = true;
    dom.runButton.textContent = "실행 중...";
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 8000);

    try {
      const { payload } = await api.visualizeCode(state.code, state.stdin, controller.signal);
      window.clearTimeout(timeoutId);

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

      if (state.runResult.ok && state.steps.length) {
        renderTraceState();
      } else {
        resetEditorState(payload.error || "실행 기록을 만들지 못했습니다.");
      }
    } catch (error) {
      window.clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        setClientRunError(
          "서버 응답이 지연되고 있습니다. 개발 서버가 실행 중인지 확인하세요.",
          "실행 요청이 제한 시간 안에 끝나지 않았습니다. 무한 루프이거나 서버가 바쁜 상태일 수 있으니 잠시 후 다시 시도해 주세요.",
        );
      } else {
        setClientRunError(
          "서버에 연결하지 못했습니다. `python3 app.py`로 서버가 실행 중인지 확인하세요.",
          "개발 서버에 연결하지 못했습니다. `python3 app.py`로 서버를 실행한 뒤 다시 시도해 주세요.",
        );
      }
      resetEditorState(state.runResult.error);
    } finally {
      dom.runButton.disabled = false;
      dom.runButton.textContent = "실행 시작";
    }
  }

  function renderTraceState() {
    codePanel.syncMode(dom, true);
    configureControls();

    const step = getCurrentStep();
    const activeFrame = getActiveFrame(step);
    updateHeader(step);
    codePanel.renderCodeView(dom, state.code, step);
    flowSidebar.render(dom, step);
    state.primaryView = visualPanel.render(dom, state, step, activeFrame);
    codePanel.renderOutput(
      dom,
      step ? step.stdout || state.runResult.stdout : state.runResult.stdout,
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

    dom.playStepButton.textContent = "일시정지";
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
    dom.playStepButton.textContent = "재생";
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
