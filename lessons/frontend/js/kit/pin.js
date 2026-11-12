(function () {

  const MASK = "••••";

  function setPinShown(button, shown) {
    button.setAttribute("aria-pressed", String(shown));
    button.textContent = shown ? button.dataset.pin : MASK;
    button.title = shown ? "누르면 다시 가립니다" : "누르면 PIN이 보입니다";
  }

  function createPinToggle(pin, options = {}) {
    if (!pin) {
      const span = document.createElement("span");
      span.className = "pin-missing";
      span.textContent = options.hasPin ? "재발급 필요" : "없음";
      return span;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pin-toggle";
    button.dataset.pin = String(pin);
    button.setAttribute("aria-label", `${options.name ? `${options.name} ` : ""}PIN 보이기`);
    setPinShown(button, Boolean(options.shown));
    button.addEventListener("click", () => {
      setPinShown(button, button.getAttribute("aria-pressed") !== "true");
    });
    return button;
  }

  function createPinShowAllButton(scope) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pin-show-all";
    let shown = false;
    function apply() {
      scope.querySelectorAll(".pin-toggle").forEach((toggle) => setPinShown(toggle, shown));
      button.textContent = shown ? "PIN 모두 가리기" : "PIN 모두 보이기";
      button.setAttribute("aria-pressed", String(shown));
    }
    button.addEventListener("click", () => {
      shown = !shown;
      apply();
    });
    apply();
    return button;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
  }

  function printPinSlips(classId, code, students) {
    const win = window.open("", "_blank");
    if (!win) {
      StatApi.toast("팝업이 차단되어 인쇄 창을 열 수 없습니다.");
      return;
    }
    const slips = students.map((student) => `
      <div class="slip">
        <div class="slip-class">${escapeHtml(classId)} · 학급 코드 <strong>${escapeHtml(code || "")}</strong></div>
        <div class="slip-name">${escapeHtml(student.display_name)}</div>
        <div class="slip-pin">PIN <strong>${escapeHtml(student.pin || "재발급 필요")}</strong></div>
      </div>`).join("");
    win.document.write(`<!doctype html><html lang="ko"><head><meta charset="utf-8" />
      <title>${escapeHtml(classId)} 학생 PIN</title>
      <style>
        body { font-family: "Malgun Gothic", sans-serif; margin: 1rem; }
        .slips { display: grid; grid-template-columns: repeat(2, 1fr); }
        .slip { border: 1px dashed #888; padding: 0.6rem 1rem; break-inside: avoid; }
        .slip-class { font-size: 0.8rem; color: #444; }
        .slip-name { font-size: 1.05rem; margin: 0.2rem 0; }
        .slip-pin strong { font-size: 1.3rem; letter-spacing: 0.15em; }
      </style></head><body><div class="slips">${slips}</div></body></html>`);
    win.document.close();
    win.focus();
    win.print();
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.createPinToggle = createPinToggle;
  window.LessonKit.createPinShowAllButton = createPinShowAllButton;
  window.LessonKit.printPinSlips = printPinSlips;
})();
