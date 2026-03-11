(function () {
  window.Visualizer = window.Visualizer || {};

  function createAnalysis() {
    return {
      structures: [],
      intent_map: {},
      summary: "",
    };
  }

  function createRunResult(stdin = "") {
    return {
      ok: true,
      error: null,
      stdout: "",
      stdin,
      analysis: createAnalysis(),
    };
  }

  function createState() {
    return {
      code: "",
      stdin: "",
      steps: [],
      currentIndex: 0,
      timer: null,
      primaryView: "summary",
      runResult: createRunResult(""),
    };
  }

  window.Visualizer.state = {
    createAnalysis,
    createRunResult,
    createState,
  };
})();
