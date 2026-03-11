(function () {
  window.Visualizer = window.Visualizer || {};

  window.Visualizer.utils = {
    average(values) {
      if (!values.length) {
        return 0;
      }
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    },

    countInputLines(stdin) {
      if (!stdin) {
        return 0;
      }
      return stdin.split("\n").length;
    },

    describeView(view) {
      const labels = {
        graph: "Showing an adjacency-style graph view.",
        "data-tree": "Showing a tree structure view.",
        stack: "Showing a stack-style view with the top highlighted.",
        queue: "Showing a queue-style view with front and back highlighted.",
        "call-tree": "Showing the nested function call flow.",
        summary: "Showing a general execution summary.",
      };
      return labels[view] || labels.summary;
    },

    escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    },

    escapeXml(value) {
      return this.escapeHtml(value);
    },

    formatEvent(event) {
      const labels = {
        line: "line",
        return: "return",
        exception: "exception",
        end: "end",
        error: "error",
      };
      return labels[event] || event || "idle";
    },

    formatViewLabel(view) {
      const labels = {
        graph: "GRAPH",
        "data-tree": "TREE",
        stack: "STACK",
        queue: "QUEUE",
        "call-tree": "CALL",
        summary: "SUMMARY",
      };
      return labels[view] || "SUMMARY";
    },

    shortStatus(status) {
      const labels = {
        running: "run",
        returned: "ret",
        exception: "err",
      };
      return labels[status] || status || "run";
    },

    structureKindLabel(kind) {
      const labels = {
        graph: "Graph",
        tree: "Tree",
        stack: "Stack",
        queue: "Queue",
      };
      return labels[kind] || kind;
    },

    trimLabel(value, maxLength) {
      return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
    },
  };
})();
