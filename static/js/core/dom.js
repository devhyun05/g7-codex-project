(function () {
  window.Visualizer = window.Visualizer || {};

  function getRefs() {
    return {
      codeInput: document.getElementById("code-input"),
      stdinInput: document.getElementById("stdin-input"),
      languageSelect: document.getElementById("language-select"),
      runButton: document.getElementById("run-button"),
      prevStepButton: document.getElementById("prev-step"),
      playStepButton: document.getElementById("play-step"),
      nextStepButton: document.getElementById("next-step"),
      stepSlider: document.getElementById("step-slider"),
      stepCounter: document.getElementById("step-counter"),
      languagePill: document.getElementById("language-pill"),
      functionPill: document.getElementById("function-pill"),
      linePill: document.getElementById("line-pill"),
      editCodeButton: document.getElementById("edit-code-button"),
      editorWrap: document.getElementById("editor-wrap"),
      codeViewer: document.getElementById("code-viewer"),
      outputView: document.getElementById("output-view"),
      outputStatus: document.getElementById("output-status"),
      stageTitle: document.getElementById("stage-title"),
      stageCaption: document.getElementById("stage-caption"),
      primaryStage: document.getElementById("primary-stage"),
      eventLabel: document.getElementById("event-label"),
      primaryViewLabel: document.getElementById("primary-view-label"),
      explanationView: document.getElementById("explanation-view"),
    };
  }

  window.Visualizer.dom = {
    getRefs,
  };
})();
