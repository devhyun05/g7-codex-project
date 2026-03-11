(function () {
  window.Visualizer = window.Visualizer || {};

  function getRefs() {
    return {
      homeButton: document.getElementById("home-button"),
      codeInput: document.getElementById("code-input"),
      stdinInput: document.getElementById("stdin-input"),
      runButton: document.getElementById("run-button"),
      prevStepButton: document.getElementById("prev-step"),
      playStepButton: document.getElementById("play-step"),
      nextStepButton: document.getElementById("next-step"),
      stepSlider: document.getElementById("step-slider"),
      stepCounter: document.getElementById("step-counter"),
      functionPill: document.getElementById("function-pill"),
      linePill: document.getElementById("line-pill"),
      editorMetaPills: document.getElementById("editor-meta-pills"),
      editCodeButton: document.getElementById("edit-code-button"),
      editorWrap: document.getElementById("editor-wrap"),
      traceWorkspace: document.getElementById("trace-workspace"),
      codeViewer: document.getElementById("code-viewer"),
      flowSidebar: document.getElementById("flow-sidebar"),
      outputPanelTitle: document.getElementById("output-panel-title"),
      outputPanelCaption: document.getElementById("output-panel-caption"),
      outputView: document.getElementById("output-view"),
      outputStatus: document.getElementById("output-status"),
      stageTitle: document.getElementById("stage-title"),
      stageCaption: document.getElementById("stage-caption"),
      primaryStage: document.getElementById("primary-stage"),
      eventLabel: document.getElementById("event-label"),
      primaryViewLabel: document.getElementById("primary-view-label"),
      explanationView: document.getElementById("explanation-view"),
      workspaceGrid: document.querySelector(".workspace-grid"),
      workspaceSplitter: document.getElementById("workspace-splitter"),
    };
  }

  window.Visualizer.dom = {
    getRefs,
  };
})();
