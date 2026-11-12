(function () {
  const API_BASE_KEY = "stat-agent-api-base";

  function isLocalHost(hostname) {
    return hostname === "localhost" || hostname === "127.0.0.1";
  }

  function cleanBase(value) {
    return String(value || "").replace(/\/+$/, "");
  }

  function defaultApiBase() {
    if (isLocalHost(window.location.hostname)) {
      return "http://127.0.0.1:18080";
    }
    return window.location.origin;
  }

  function storedApiBase() {
    const stored = cleanBase(localStorage.getItem(API_BASE_KEY));
    if (!stored) return "";
    if (!isLocalHost(window.location.hostname) && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(stored)) {
      localStorage.removeItem(API_BASE_KEY);
      return "";
    }
    if (stored === "http://127.0.0.1:8000" || stored === "http://localhost:8000") {
      localStorage.removeItem(API_BASE_KEY);
      return "";
    }
    return stored;
  }

  let activeApiBase = storedApiBase() || defaultApiBase();

  function candidateApiBases() {
    const bases = new Set([defaultApiBase(), activeApiBase].map(cleanBase));
    if (isLocalHost(window.location.hostname)) {
      bases.add("http://localhost:18080");
      bases.add(`http://${window.location.hostname}:18080`);
    } else {
      bases.add(window.location.origin);
    }
    return [...bases].filter(Boolean);
  }

  function isAuthBootstrapPath(path) {
    return path === "/api/auth/client-config" || path === "/api/auth/me";
  }

  function delegationHeaders(path) {
    if (isAuthBootstrapPath(path)) return {};
    const headers = {};
    const actAsUserId = window.StatAuth?.getAdminActAsUserId?.();
    if (actAsUserId) {
      headers["X-Admin-Act-As-User"] = actAsUserId;
    }
    if (window.StatAuth?.isStudentPreview?.()) {
      headers["X-Student-Preview"] = "true";
    }
    return headers;
  }

  async function headers(path) {
    const baseHeaders = {
      "Content-Type": "application/json",
    };
    if (window.StatAuth?.isFirebaseMode?.()) {
      const token = await window.StatAuth.getIdToken({ allowUnverified: isAuthBootstrapPath(path) });
      return {
        ...baseHeaders,
        Authorization: `Bearer ${token}`,
        ...delegationHeaders(path),
      };
    }
    const user = StatState.getUser();
    return {
      ...baseHeaders,
      "X-Dev-User": user.email,
      "X-Dev-Role": user.role,
      ...delegationHeaders(path),
    };
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
    ) {
      const message = window.StatAuth.getAuthError?.() || "허용된 Google 계정이 아닙니다.";
      toast(`${message} 로그아웃 후 허용된 계정으로 다시 로그인해 주세요.`);
      throw new Error(message);
    }
    const requestHeaders = {
      ...(await headers(path)),
      ...(options.headers || {}),
    };
    if (options.body instanceof FormData) {
      delete requestHeaders["Content-Type"];
    }
    let response;
    let lastNetworkError;
    for (const base of candidateApiBases()) {
      try {
        response = await fetch(`${base}${path}`, {
          ...options,
          headers: requestHeaders,
        });
        if (!(response.headers.get("content-type") || "").includes("application/json")) {
          lastNetworkError = new Error(`${base}에서 JSON API 응답을 받지 못했습니다.`);
          if (cleanBase(localStorage.getItem(API_BASE_KEY)) === cleanBase(base)) {
            localStorage.removeItem(API_BASE_KEY);
          }
          response = null;
          continue;
        }
        activeApiBase = base;
        localStorage.setItem(API_BASE_KEY, base);
        if (window.StatApi) {
          window.StatApi.API_BASE = activeApiBase;
        }
        break;
      } catch (error) {
        lastNetworkError = error;
      }
    }
    if (!response) {
      const target = isLocalHost(window.location.hostname)
        ? "http://127.0.0.1:18080 실행 상태"
        : `${window.location.origin}/api rewrite`;
      throw new Error(
        `백엔드 서버에 연결할 수 없습니다. ${target}와 CORS origin 설정을 확인해 주세요. (${
          lastNetworkError?.message || "network error"
        })`,
      );
    }
    const body = await response.json();
    if (!response.ok || body.success === false) {
      const message = body.error_message_ko || "요청 처리 중 오류가 발생했습니다.";
      toast(`${message} ${body.suggested_fix || ""}`.trim());
      throw new Error(message);
    }
    return body.data ?? body;
  }

  async function download(path, filename) {
    const requestHeaders = await headers(path);
    const response = await fetch(`${activeApiBase}${path}`, { headers: requestHeaders });
    if (!response.ok) {
      throw new Error("파일을 내려받을 수 없습니다.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function chartUrl(path) {
    if (!path) return "";
    if (path.startsWith("http")) return path;
    return `${activeApiBase}${path}`;
  }

  window.StatApi = {
    API_BASE: activeApiBase,
    request,
    download,
    chartUrl,
    toast,

    mergeKeySuggestions(datasetId) {
      return request(`/api/merge/key-suggestions/${encodeURIComponent(datasetId)}`);
    },
    mergePreview(datasetIds, keyColumnMappings, timeColumnMappings = {}) {
      return request("/api/merge/preview", {
        method: "POST",
        body: JSON.stringify({
          dataset_ids: datasetIds,
          key_column_mappings: keyColumnMappings,
          time_column_mappings: timeColumnMappings,
        }),
      });
    },
    mergeHarmonize(datasetId, keyColumn, renameMap) {
      return request("/api/merge/harmonize", {
        method: "POST",
        body: JSON.stringify({ dataset_id: datasetId, key_column: keyColumn, rename_map: renameMap }),
      });
    },
    mergeAiHarmonize(datasetIds, keyColumnMappings) {
      return request("/api/merge/ai-harmonize", {
        method: "POST",
        body: JSON.stringify({ dataset_ids: datasetIds, key_column_mappings: keyColumnMappings }),
      });
    },
    mergeTimePoints(datasetIds, timeColumnMappings) {
      return request("/api/merge/time-points", {
        method: "POST",
        body: JSON.stringify({ dataset_ids: datasetIds, time_column_mappings: timeColumnMappings }),
      });
    },
    mergeExecute(payload) {
      return request("/api/merge/execute", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    mapLevels() {
      return request("/api/maps/levels");
    },
    mapColorScales(nClasses = 5) {
      return request(`/api/maps/color-scales?n_classes=${encodeURIComponent(nClasses)}`);
    },
    mapChildRegions(level = "sido", parentRegion = "") {
      const parent = parentRegion ? `&parent_region=${encodeURIComponent(parentRegion)}` : "";
      return request(`/api/maps/regions?level=${encodeURIComponent(level)}${parent}`);
    },
    mapChoropleth(payload) {
      return request("/api/maps/choropleth", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    mapRegionLookup(regionNames, level = "sido") {
      return request("/api/maps/region-lookup", {
        method: "POST",
        body: JSON.stringify({ region_names: regionNames, level }),
      });
    },
  };
})();
