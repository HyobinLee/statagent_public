(function () {

  const CLASS_CODE_KEY = "lesson-last-class-code";
  const REDIRECT_GUARD_KEY = "lesson-access-redirected";

  const NOT_A_LOGIN_PROBLEM = new Set([
    "CLASS_NOT_ASSIGNED",
    "SESSION_CLASS_FORBIDDEN",
    "FORBIDDEN",
    "FORBIDDEN_STUDENT_PREVIEW",
  ]);

  function currentPageName() {
    return window.location.pathname.split("/").pop() || "index.html";
  }

  function rememberClassCode(code) {
    const value = String(code || "").trim().toUpperCase();
    if (value) localStorage.setItem(CLASS_CODE_KEY, value);
  }

  function getRememberedClassCode() {
    return localStorage.getItem(CLASS_CODE_KEY) || "";
  }

  function forgetClassCode() {
    localStorage.removeItem(CLASS_CODE_KEY);
  }

  function safeNextTarget(raw) {
    const value = String(raw || "").trim();
    if (!value) return "";
    return /^[A-Za-z0-9_-]+\.html(\?[^#]*)?$/.test(value) ? value : "";
  }

  function currentTarget() {
    return `${currentPageName()}${window.location.search || ""}`;
  }

  function loginUrl(reason) {
    const params = new URLSearchParams();
    const next = safeNextTarget(currentTarget());
    if (next) params.set("next", next);
    const code = getRememberedClassCode();
    if (code) params.set("code", code);
    if (reason) params.set("reason", reason);
    const query = params.toString();
    return `./login.html${query ? `?${query}` : ""}`;
  }

  function alreadyRedirected() {
    return sessionStorage.getItem(REDIRECT_GUARD_KEY) === currentPageName();
  }

  function markRedirected() {
    sessionStorage.setItem(REDIRECT_GUARD_KEY, currentPageName());
  }

  function clearRedirectGuard() {
    sessionStorage.removeItem(REDIRECT_GUARD_KEY);
  }

  function renderAccessPanel(container, { title, lines, actions }) {
    if (!container) return;
    container.innerHTML = "";
    const panel = document.createElement("section");
    panel.className = "lesson-access-panel";

    const heading = document.createElement("h2");
    heading.textContent = title;
    panel.appendChild(heading);

    (lines || []).forEach((line) => {
      const p = document.createElement("p");
      p.textContent = line;
      panel.appendChild(p);
    });

    const row = document.createElement("div");
    row.className = "lesson-access-actions";
    (actions || []).forEach((action) => {
      const link = document.createElement("a");
      link.className = `lesson-access-action${action.primary ? " primary" : ""}`;
      link.href = action.href;
      link.textContent = action.label;
      if (action.onClick) {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          action.onClick();
        });
      }
      row.appendChild(link);
    });
    panel.appendChild(row);
    container.appendChild(panel);
  }

  function goToLogin(reason) {
    markRedirected();
    window.location.href = loginUrl(reason);
  }

  function handleLessonAccessError(container, error) {
    const code = error?.code || "";
    const message = error?.message || "차시를 불러오지 못했습니다.";

    if (!code && /연결할 수 없습니다/.test(message)) {
      renderAccessPanel(container, {
        title: "수업 서버에 연결하지 못했습니다",
        lines: [message, "인터넷 연결을 확인한 뒤 다시 시도해 주세요. 계속 안 되면 선생님께 알려 주세요."],
        actions: [
          { label: "다시 시도", href: "#", primary: true, onClick: () => window.location.reload() },
          { label: "차시 목록", href: "./index.html" },
        ],
      });
      return;
    }

    if (NOT_A_LOGIN_PROBLEM.has(code)) {
      const isClassProblem = code === "CLASS_NOT_ASSIGNED" || code === "SESSION_CLASS_FORBIDDEN";
      renderAccessPanel(container, {
        title: isClassProblem ? "아직 학급이 정해지지 않았습니다" : "이 차시를 열 수 없습니다",
        lines: [
          message,
          isClassProblem
            ? "선생님께 학급 배정을 요청해 주세요. 배정되면 이 주소로 다시 들어오면 됩니다."
            : "선생님께 알려 주세요.",
        ],
        actions: [
          { label: "차시 목록", href: "./index.html", primary: true },
          { label: "다른 학급 코드로 들어가기", href: loginUrl("switch"), onClick: () => {
            forgetClassCode();
            window.location.href = loginUrl("switch");
          } },
        ],
      });
      return;
    }

    if (!alreadyRedirected()) {
      goToLogin("expired");
      return;
    }

    renderAccessPanel(container, {
      title: "로그인이 필요합니다",
      lines: [
        message,
        "참여 코드와 PIN으로 다시 들어가 보세요. 그래도 안 되면 선생님께 알려 주세요.",
      ],
      actions: [
        { label: "참여 코드 입력하기", href: loginUrl("retry"), primary: true },
        { label: "차시 목록", href: "./index.html" },
      ],
    });
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.rememberClassCode = rememberClassCode;
  window.LessonKit.getRememberedClassCode = getRememberedClassCode;
  window.LessonKit.forgetClassCode = forgetClassCode;
  window.LessonKit.safeNextTarget = safeNextTarget;
  window.LessonKit.studentLoginUrl = loginUrl;
  window.LessonKit.clearAccessRedirectGuard = clearRedirectGuard;
  window.LessonKit.renderAccessPanel = renderAccessPanel;
  window.LessonKit.handleLessonAccessError = handleLessonAccessError;
})();
