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

  function createLanguage() {
    return {
      key: "unknown",
      label: "Unknown",
      source: "auto",
      trace_supported: false,
    };
  }

  function createRunResult(stdin = "") {
    return {
      ok: true,
      error: null,
      displayError: null,
      stdout: "",
      stdin,
      runMode: "trace",
      language: createLanguage(),
      traceCapabilities: null,
      supportedLanguages: [],
      analysis: createAnalysis(),
    };
  }

  function createState() {
    return {
      code: "",
      stdin: "",
      language: "auto",
      steps: [],
      currentIndex: 0,
      timer: null,
      primaryView: "summary",
      runResult: createRunResult(""),
    };
  }

  window.Visualizer.state = {
    createAnalysis,
    createLanguage,
    createRunResult,
    createState,
  };
})();
