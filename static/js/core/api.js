(function () {
  window.Visualizer = window.Visualizer || {};

  async function visualizeCode(code, stdin, language, signal) {
    const response = await fetch("/api/visualize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code, stdin, language }),
      signal,
    });

    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      payload = {
        ok: false,
        error: "Could not parse the server response.",
        steps: [],
        stdout: "",
        stdin,
        language: {
          key: "unknown",
          label: "Unknown",
          source: "auto",
          trace_supported: false,
        },
        supported_languages: [],
        analysis: {
          structures: [],
          intent_map: {},
          summary: "",
        },
      };
    }

    return { response, payload };
  }

  window.Visualizer.api = {
    visualizeCode,
  };
})();
