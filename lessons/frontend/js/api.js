(function () {
  const DEFAULT_BASE = "http://127.0.0.1:18081";

  function isLocalHost(hostname) {
    return hostname === "localhost" || hostname === "127.0.0.1";
  }

  function apiBase() {
    if (isLocalHost(window.location.hostname)) {
      return DEFAULT_BASE;
    }
    return window.location.origin;
  }

  const REUSED_MAIN_BACKEND_PREFIXES = ["/api/auth", "/api/datasets", "/api/projects", "/api/topics", "/api/maps"];

  function resolvePath(path) {
    if (REUSED_MAIN_BACKEND_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) {
      return `/api/lessons${path}`;
    }
    return path;
  }

  function isAuthBootstrapPath(path) {
    return path === "/api/auth/client-config" || path === "/api/auth/me";
  }

  function isPublicPath(path) {
    return path.startsWith("/api/lessons/student-auth/");
  }

  const PREVIEW_DELEGATED_PREFIXES = [
    "/api/lessons/lesson",
    "/api/lessons/projects",
    "/api/lessons/datasets",
    "/api/lessons/connectors",
    "/api/lessons/transform",
    "/api/lessons/careers",
    "/api/lessons/group",
    "/api/lessons/inquiry",
    "/api/projects",
    "/api/datasets",
    "/api/topics",
  ];

  let previewOverride = null;

  function setStudentPreviewOverride(value) {
    previewOverride = value;
  }

  function usesStudentPreview(path) {
    const wanted = previewOverride === null
      ? window.StatAuth?.isStudentPreview?.() === true
      : previewOverride === true;
    if (!wanted) return false;
    return PREVIEW_DELEGATED_PREFIXES.some((prefix) => path.startsWith(prefix));
  }

  function delegationHeaders(path) {
    if (isAuthBootstrapPath(path)) return {};
    const headers = {};
    const actAsUserId = window.StatAuth?.getAdminActAsUserId?.();
    if (actAsUserId) {
      headers["X-Admin-Act-As-User"] = actAsUserId;
    }
    if (usesStudentPreview(path)) {
      headers["X-Student-Preview"] = "true";
    }
    return headers;
  }

  async function headers(path) {
    const baseHeaders = { "Content-Type": "application/json" };
    if (isPublicPath(path) && !window.StatAuth?.isSignedIn?.()) {
      return baseHeaders;
    }
    if (window.StatAuth?.isFirebaseMode?.()) {
      const token = await window.StatAuth.getIdToken({ allowUnverified: isAuthBootstrapPath(path) });
      return { ...baseHeaders, Authorization: `Bearer ${token}`, ...delegationHeaders(path) };
    }
    const user = StatState.getUser();
    return { ...baseHeaders, "X-Dev-User": user.email, "X-Dev-Role": user.role, ...delegationHeaders(path) };
  }

  function toast(message) {
    const target = document.getElementById("toast");
    if (!target) {
      alert(message);
      return;
    }
    target.textContent = message;
    target.hidden = false;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => {
      target.hidden = true;
    }, 4200);
  }

  async function request(path, options = {}) {
    if (
      window.StatAuth?.isFirebaseMode?.()
      && window.StatAuth?.isAuthorized?.() === false
      && !isAuthBootstrapPath(path)
      && !isPublicPath(path)
    ) {
      const message = window.StatAuth.getAuthError?.() || "허용된 Google 계정이 아닙니다.";
      toast(`${message} 로그아웃 후 허용된 계정으로 다시 로그인해 주세요.`);
      throw new Error(message);
    }
    const requestHeaders = { ...(await headers(path)), ...(options.headers || {}) };
    if (options.body instanceof FormData) {
      delete requestHeaders["Content-Type"];
    }
    let response;
    try {
      response = await fetch(`${apiBase()}${resolvePath(path)}`, { ...options, headers: requestHeaders });
    } catch (error) {
      throw new Error(`차시 백엔드(${apiBase()})에 연결할 수 없습니다. (${error.message || "network error"})`);
    }
    const body = await response.json();
    if (!response.ok || body.success === false) {
      const message = body.error_message_ko || "요청 처리 중 오류가 발생했습니다.";
      toast(`${message} ${body.suggested_fix || ""}`.trim());
      const error = new Error(message);
      error.code = body.error_code || "";
      error.fix = body.suggested_fix || "";
      throw error;
    }
    return body.data ?? body;
  }

  function chartUrl(path) {
    if (!path) return "";
    if (path.startsWith("http")) return path;
    return `${apiBase()}${path}`;
  }

  window.StatApi = { API_BASE: apiBase(), request, chartUrl, toast, setStudentPreviewOverride };
})();
