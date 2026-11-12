(function () {
  function setupSettingsMenu(root) {
    const button = root.querySelector(".present-settings-btn");
    const panel = root.querySelector(".present-settings-panel");
    if (!button || !panel) return;

    function setOpen(open) {
      panel.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    }

    button.addEventListener("click", () => setOpen(panel.hidden));
    document.addEventListener("click", (event) => {
      if (panel.hidden || root.contains(event.target)) return;
      setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !panel.hidden) setOpen(false);
    });
  }

  document.querySelectorAll(".present-settings").forEach(setupSettingsMenu);
})();
