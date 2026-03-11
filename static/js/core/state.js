(function () {
  window.Visualizer = window.Visualizer || {};

  function createAnalysis() {
    return {
      structures: [],
      intent_map: {},
      summary: "",
      intents: {
        sorting: false,
        sorting_order: "unknown",
      },
    };
  }

  function createRunResult(stdin = "") {
    return {
      ok: true,
      error: null,
      displayError: null,
      stdout: "",
      stdin,
      analysis: createAnalysis(),
    };
  }

  function createState() {
    return {
      language: "python",
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
