(function () {
  window.Visualizer = window.Visualizer || {};

  const MIN_RATIO = 0.28;
  const MAX_RATIO = 0.72;
  const MOBILE_QUERY = window.matchMedia("(max-width: 980px)");

  function initialize(dom) {
    if (!dom.workspaceGrid || !dom.workspaceSplitter) {
      return;
    }

    applyRatio(dom.workspaceGrid, 0.5);
    bindPointerResize(dom.workspaceGrid, dom.workspaceSplitter);
    bindKeyboardResize(dom.workspaceGrid, dom.workspaceSplitter);
    MOBILE_QUERY.addEventListener("change", () => {
      if (MOBILE_QUERY.matches) {
        dom.workspaceGrid.style.removeProperty("--workspace-left-width");
        dom.workspaceGrid.classList.remove("is-resizing");
      } else if (!dom.workspaceGrid.style.getPropertyValue("--workspace-left-width")) {
        applyRatio(dom.workspaceGrid, 0.5);
      }
    });
  }

  function bindPointerResize(grid, splitter) {
    splitter.addEventListener("pointerdown", (event) => {
      if (MOBILE_QUERY.matches) {
        return;
      }

      splitter.setPointerCapture(event.pointerId);
      grid.classList.add("is-resizing");

      const handleMove = (moveEvent) => {
        applyPointerPosition(grid, moveEvent.clientX);
      };

      const handleStop = () => {
        grid.classList.remove("is-resizing");
        splitter.removeEventListener("pointermove", handleMove);
        splitter.removeEventListener("pointerup", handleStop);
        splitter.removeEventListener("pointercancel", handleStop);
      };

      splitter.addEventListener("pointermove", handleMove);
      splitter.addEventListener("pointerup", handleStop);
      splitter.addEventListener("pointercancel", handleStop);
    });
  }

  function bindKeyboardResize(grid, splitter) {
    splitter.addEventListener("keydown", (event) => {
      if (MOBILE_QUERY.matches) {
        return;
      }

      const currentRatio = readRatio(grid);
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        applyRatio(grid, currentRatio - 0.03);
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        applyRatio(grid, currentRatio + 0.03);
      }

      if (event.key === "Home") {
        event.preventDefault();
        applyRatio(grid, 0.38);
      }

      if (event.key === "End") {
        event.preventDefault();
        applyRatio(grid, 0.62);
      }
    });
  }

  function applyPointerPosition(grid, clientX) {
    const rect = grid.getBoundingClientRect();
    const splitterWidth = 14;
    const usableWidth = rect.width - splitterWidth;
    const rawRatio = (clientX - rect.left - splitterWidth / 2) / usableWidth;
    applyRatio(grid, rawRatio);
  }

  function applyRatio(grid, ratio) {
    const clamped = Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio));
    grid.style.setProperty("--workspace-left-width", `${(clamped * 100).toFixed(2)}%`);
  }

  function readRatio(grid) {
    const raw = grid.style.getPropertyValue("--workspace-left-width");
    if (!raw) {
      return 0.5;
    }

    return Number.parseFloat(raw) / 100;
  }

  window.Visualizer.layout = window.Visualizer.layout || {};
  window.Visualizer.layout.splitter = {
    initialize,
  };
})();
