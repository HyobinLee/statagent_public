(function () {
  const ENDPOINTS = {
    gg_library: "/api/lessons/connectors/gg-library",
    neis_meal: "/api/lessons/connectors/neis-meal",
    kosis_private_edu: "/api/lessons/connectors/kosis-private-edu",
  };

  function renderRequestUrl(container, url) {
    if (!url) return;
    const pre = document.createElement("pre");
    pre.className = "lesson-request-url";
    pre.textContent = url;
    container.appendChild(pre);
  }

  function renderSourceBadge(container, result, isTeacherViewer) {
    const isFallback = String(result.source || "").startsWith("탑재된 대체 자료");
    const badge = document.createElement("div");
    badge.className = `lesson-source-badge ${isFallback ? "fallback" : "live"}`;
    badge.textContent = isFallback ? `대체 자료 사용: ${result.source}` : `실시간 호출 성공: ${result.source}`;
    container.appendChild(badge);
    if (result.source_reason && isTeacherViewer) {
      const reason = document.createElement("p");
      reason.className = "lesson-source-reason";
      reason.textContent = `실시간 호출을 쓰지 못한 이유: ${result.source_reason}`;
      container.appendChild(reason);
    }
  }

  async function showResult(resultContainer, result, step, isTeacherViewer) {
    resultContainer.innerHTML = "";
    renderSourceBadge(resultContainer, result, isTeacherViewer);
    renderRequestUrl(resultContainer, result.request_url);
    const sheetContainer = document.createElement("div");
    resultContainer.appendChild(sheetContainer);
    await window.LessonKit.renderSheet(sheetContainer, result.dataset_id, {
      limit: (step && step.sheet_limit) || 10,
      previewRows: step && step.preview_rows,
    });
  }

  async function renderConnector(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);
    const isTeacherViewer = ctx.role === "teacher" || ctx.role === "admin";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "lesson-connector-fetch primary";
    button.textContent = "자료 불러오기";
    body.appendChild(button);

    const resultContainer = document.createElement("div");
    resultContainer.className = "lesson-connector-result";
    body.appendChild(resultContainer);

    if (step.note) {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = step.note;
      body.appendChild(note);
    }

    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "불러오는 중…";
      try {
        const endpoint = `${ENDPOINTS[step.connector_key]}?track=${encodeURIComponent(ctx.track || "")}`;
        const result = await window.StatApi.request(endpoint, { method: "POST", body: JSON.stringify({}) });
        await showResult(resultContainer, result, step, isTeacherViewer);
        button.textContent = "다시 불러오기";
      } catch (error) {
        window.LessonKit.showError(error.message || "자료를 불러오지 못했습니다.");
        button.textContent = "다시 시도";
      } finally {
        button.disabled = false;
      }
    });

    try {
      const state = await window.StatApi.request(
        `/api/lessons/connectors/state/${encodeURIComponent(ctx.lessonId)}?track=${encodeURIComponent(ctx.track || "")}`,
      );
      const existing = state[step.connector_key];
      if (existing && existing.dataset_id) {
        await showResult(resultContainer, existing, step, isTeacherViewer);
        button.textContent = "다시 불러오기";
      }
    } catch (_error) {
    }
  }

  function renderErrorCard(container, error) {
    container.innerHTML = "";
    const card = document.createElement("div");
    card.className = "lesson-error-card";

    const title = document.createElement("p");
    title.className = "lesson-error-title";
    title.textContent = "업로드하지 못했습니다";
    card.appendChild(title);

    const message = document.createElement("p");
    message.className = "lesson-error-message";
    message.textContent = error.message || "알 수 없는 오류입니다.";
    card.appendChild(message);

    if (error.fix) {
      const fix = document.createElement("p");
      fix.className = "lesson-error-fix";
      fix.textContent = `이렇게 해 보세요: ${error.fix}`;
      card.appendChild(fix);
    }
    if (error.code) {
      const code = document.createElement("p");
      code.className = "lesson-error-code";
      code.textContent = `오류 이름: ${error.code}`;
      card.appendChild(code);
    }
    container.appendChild(card);
  }

  async function uploadCsv(file, filename, ctx) {
    const formData = new FormData();
    formData.append("file", file, filename);
    formData.append("topic_id", ctx.topicId);
    return window.StatApi.request("/api/datasets/upload", { method: "POST", body: formData });
  }

  async function showUploadResult(container, payload) {
    container.innerHTML = "";
    const badge = document.createElement("div");
    badge.className = "lesson-source-badge live";
    badge.textContent = `업로드 완료 · ${payload.dataset.name} (${payload.dataset.columns.length}개 항목)`;
    container.appendChild(badge);
    const sheetContainer = document.createElement("div");
    container.appendChild(sheetContainer);
    await window.LessonKit.renderSheet(sheetContainer, payload.dataset.dataset_id, { limit: 10 });
  }

  async function renderCsvUpload(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    (step.downloads || []).forEach((download) => {
      const link = document.createElement("a");
      link.className = "lesson-download-link";
      link.href = `./${download.file}`;
      link.download = "";
      link.textContent = download.label;
      body.appendChild(link);
    });

    const resultContainer = document.createElement("div");

    if (step.upload_file) {
      const fixedButton = document.createElement("button");
      fixedButton.type = "button";
      fixedButton.className = "lesson-connector-fetch primary";
      fixedButton.textContent = step.upload_label || "이 파일 올려 보기";
      body.appendChild(fixedButton);
      fixedButton.addEventListener("click", async () => {
        fixedButton.disabled = true;
        fixedButton.textContent = "올리는 중…";
        try {
          const response = await fetch(`./${step.upload_file}`);
          if (!response.ok) throw new Error("파일을 읽지 못했습니다.");
          const blob = await response.blob();
          const filename = step.upload_file.split("/").pop();
          const payload = await uploadCsv(blob, filename, ctx);
          await showUploadResult(resultContainer, payload);
        } catch (error) {
          renderErrorCard(resultContainer, error);
        } finally {
          fixedButton.disabled = false;
          fixedButton.textContent = "다시 올려 보기";
        }
      });
    }

    const form = document.createElement("div");
    form.className = "lesson-upload-form";
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".csv";
    form.appendChild(fileInput);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary";
    button.textContent = "업로드";
    form.appendChild(button);
    if (step.hide_file_picker) form.hidden = true;
    body.appendChild(form);
    body.appendChild(resultContainer);

    button.addEventListener("click", async () => {
      const file = fileInput.files[0];
      if (!file) {
        window.LessonKit.showError("업로드할 CSV 파일을 먼저 선택해 주세요.");
        return;
      }
      button.disabled = true;
      button.textContent = "업로드하는 중…";
      try {
        const payload = await uploadCsv(file, file.name, ctx);
        await showUploadResult(resultContainer, payload);
        button.textContent = "다시 업로드";
      } catch (error) {
        renderErrorCard(resultContainer, error);
        button.textContent = "업로드";
      } finally {
        button.disabled = false;
      }
    });
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderConnector = renderConnector;
  window.LessonKit.renderCsvUpload = renderCsvUpload;
})();
