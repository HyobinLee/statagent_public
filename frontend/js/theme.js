(function () {
  const STORAGE_KEY = "stat-theme";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  function current() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function updateToggleButtons() {
    const isDark = current() === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.textContent = isDark ? "☀️ 라이트 모드" : "🌙 야간 모드";
      btn.setAttribute("aria-pressed", String(isDark));
    });
  }

  function set(theme) {
    root.dataset.theme = theme === "dark" ? "dark" : "light";
    try {
      localStorage.setItem(STORAGE_KEY, root.dataset.theme);
    } catch (error) {
    }
    updateToggleButtons();
  }

  function toggle() {
    set(current() === "dark" ? "light" : "dark");
  }

  media.addEventListener("change", (event) => {
    let stored = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      stored = null;
    }
    if (!stored) {
      root.dataset.theme = event.matches ? "dark" : "light";
      updateToggleButtons();
    }
  });

  function init() {
    updateToggleButtons();
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.addEventListener("click", toggle);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.StatTheme = { toggle, set, current };
})();
