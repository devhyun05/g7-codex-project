(function () {
  window.Visualizer = window.Visualizer || {};

  async function visualizeCode(code, stdin, signal) {
    const response = await fetch("/api/visualize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code, stdin }),
      signal,
    });

    let payload;
    try {
      payload = await response.json();
    } catch (error) {
      payload = {
        ok: false,
        error: "서버 응답을 해석하지 못했습니다.",
        display_error: "서버 응답 형식을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.",
        steps: [],
        stdout: "",
        stdin,
        analysis: {
          structures: [],
          intent_map: {},
          summary: "",
          intents: {
            sorting: false,
            sorting_order: "unknown",
          },
        },
      };
    }

    return { response, payload };
  }

  window.Visualizer.api = {
    visualizeCode,
  };
})();
