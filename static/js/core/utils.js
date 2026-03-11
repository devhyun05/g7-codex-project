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
        sorting: "정렬 알고리즘의 배열 변화를 막대 그래프로 시각화하고 있습니다.",
        graph: "인접 구조를 그래프 흐름으로 시각화하고 있습니다.",
        "linked-list": "연결 리스트 노드 값과 포인터 연결을 시각화하고 있습니다.",
        "data-tree": "노드 구조를 트리로 판단해 현재 노드를 강조하고 있습니다.",
        stack: "push / pop 흐름을 보기 좋게 스택 형태로 시각화하고 있습니다.",
        queue: "front / back 이동이 보이도록 큐 형태로 시각화하고 있습니다.",
        "call-tree": "자료구조보다 재귀 호출 흐름이 중요해 호출 트리를 보여주고 있습니다.",
        summary: "특정 자료구조가 없어서 실행 상태 요약을 보여주고 있습니다.",
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
        sorting: "SORT",
        graph: "GRAPH",
        "linked-list": "LIST",
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
        graph: "그래프",
        "linked-list": "연결리스트",
        tree: "트리",
        stack: "스택",
        queue: "큐",
      };
      return labels[kind] || kind;
    },

    trimLabel(value, maxLength) {
      return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
    },
  };
})();
