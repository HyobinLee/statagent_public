(function () {
  async function selectAsActiveDataset(projectId, datasetId) {
    const project = await window.StatApi.request(`/api/lessons/inquiry/${encodeURIComponent(projectId)}/dataset`, {
      method: "PUT",
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    if (project?.dataset_id !== datasetId) {
      throw new Error("프로젝트가 다른 자료를 가리키고 있습니다.");
    }
    return project;
  }

  function badge(container, text, tone) {
    const el = document.createElement("div");
    el.className = `lesson-source-badge ${tone}`;
    el.textContent = text;
    container.appendChild(el);
    return el;
  }

  async function linkWithStatus(container, ctx, dataset) {
    const status = document.createElement("div");
    container.appendChild(status);

    async function attempt() {
      status.innerHTML = "";
      badge(status, "탐구 프로젝트에 연결하는 중…", "fallback");
      try {
        await selectAsActiveDataset(ctx.projectId, dataset.dataset_id);
        status.innerHTML = "";
        badge(status, `② 탐구 프로젝트에 연결했습니다 — 6차시 분석에 '${dataset.name}'을(를) 씁니다`, "live");
        window.LessonKit.notifyInquiryChanged?.();
        return true;
      } catch (error) {
        status.innerHTML = "";
        badge(status, "② 탐구 프로젝트에 연결하지 못했습니다 — 이대로는 6차시에서 이 자료로 분석할 수 없습니다", "fallback");
        const reason = document.createElement("p");
        reason.className = "lesson-source-reason";
        reason.textContent = `이유: ${error.message || "알 수 없는 오류"}`;
        status.appendChild(reason);
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "primary";
        retry.textContent = "연결 다시 시도";
        retry.addEventListener("click", async () => {
          retry.disabled = true;
          await attempt();
        });
        status.appendChild(retry);
        return false;
      }
    }

    return attempt();
  }

  async function renderActiveDatasetNote(container, ctx) {
    const note = document.createElement("p");
    note.className = "lesson-note";
    container.appendChild(note);

    async function update() {
      try {
        const summary = await window.LessonKit.fetchInquiry(ctx.projectId);
        note.textContent = summary.dataset
          ? `지금 탐구에 연결된 자료: ${summary.dataset.name}. 여기서 새 자료를 연결하면 이 자료 대신 새 자료로 분석합니다.`
          : "지금 탐구에 연결된 자료가 없습니다.";
      } catch (_error) {
        note.textContent = "";
      }
    }

    window.LessonKit.onInquiryChanged?.(update);
    await update();
  }

  async function renderWebTableInput(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);
    await renderActiveDatasetNote(body, ctx);

    const hint = document.createElement("p");
    hint.className = "lesson-note";
    hint.textContent = "첫 줄은 항목 이름(예: 항목,값), 그 아래는 실제 값을 쉼표로 구분해 한 줄씩 입력하세요.";
    body.appendChild(hint);

    const textarea = document.createElement("textarea");
    textarea.className = "lesson-table-input";
    textarea.rows = 8;
    textarea.placeholder = "항목,값\n예시1,10\n예시2,20";
    body.appendChild(textarea);

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "자료 이름 (예: 우리 반 설문 결과)";
    nameInput.className = "lesson-dataset-name-input";
    body.appendChild(nameInput);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary";
    button.textContent = "이 표로 자료 만들기";
    body.appendChild(button);

    const resultContainer = document.createElement("div");
    body.appendChild(resultContainer);

    button.addEventListener("click", async () => {
      const csvText = textarea.value.trim();
      if (!csvText) {
        window.LessonKit.showError("표 내용을 입력해 주세요.");
        return;
      }
      button.disabled = true;
      button.textContent = "만드는 중…";
      let payload;
      try {
        const blob = new Blob([csvText], { type: "text/csv" });
        const formData = new FormData();
        formData.append("file", blob, "web-table.csv");
        formData.append("topic_id", ctx.topicId);
        if (nameInput.value.trim()) formData.append("dataset_name", nameInput.value.trim());
        payload = await window.StatApi.request("/api/datasets/upload", { method: "POST", body: formData });
      } catch (error) {
        window.LessonKit.showError(error.message || "자료를 만들지 못했습니다.");
        button.textContent = "이 표로 자료 만들기";
        button.disabled = false;
        return;
      }

      resultContainer.innerHTML = "";
      badge(resultContainer, `① 자료를 만들었습니다 · ${payload.dataset.name}`, "live");
      await linkWithStatus(resultContainer, ctx, payload.dataset);
      const sheetContainer = document.createElement("div");
      resultContainer.appendChild(sheetContainer);
      try {
        await window.LessonKit.renderSheet(sheetContainer, payload.dataset.dataset_id, { limit: 10 });
      } catch (error) {
        sheetContainer.textContent = "표를 불러오지 못했습니다.";
      }
      button.textContent = "다시 만들기";
      button.disabled = false;
    });
  }

  async function renderGroupShare(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    const container = document.createElement("div");
    container.textContent = "모둠원 자료를 확인하는 중…";
    body.appendChild(container);

    let candidates;
    try {
      candidates = await window.StatApi.request("/api/lessons/group/datasets");
    } catch (error) {
      container.textContent = "";
      window.LessonKit.showError(error.message || "모둠 자료를 불러오지 못했습니다.");
      return;
    }

    container.innerHTML = "";
    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "아직 모둠에 배정되지 않았거나, 모둠원이 등록한 자료가 없습니다. 선생님이 나눠 준 표가 있으면 위 '표를 직접 입력해 자료 만들기'에 붙여넣으세요.";
      container.appendChild(empty);
      return;
    }

    await renderActiveDatasetNote(container, ctx);

    candidates.forEach((candidate) => {
      const row = document.createElement("div");
      row.className = "lesson-group-dataset-row";
      const label = document.createElement("span");
      label.textContent = `${candidate.name} (${candidate.owner_display_name})`;
      row.appendChild(label);
      const useButton = document.createElement("button");
      useButton.type = "button";
      useButton.textContent = "이 자료 쓰기";
      row.appendChild(useButton);
      container.appendChild(row);
      const statusHost = document.createElement("div");
      container.appendChild(statusHost);

      useButton.addEventListener("click", async () => {
        useButton.disabled = true;
        useButton.textContent = "가져오는 중…";
        let payload;
        try {
          payload = await window.StatApi.request("/api/lessons/group/copy-dataset", {
            method: "POST",
            body: JSON.stringify({ dataset_id: candidate.dataset_id, topic_id: ctx.topicId }),
          });
        } catch (error) {
          window.LessonKit.showError(error.message || "자료를 가져오지 못했습니다.");
          useButton.disabled = false;
          useButton.textContent = "이 자료 쓰기";
          return;
        }
        useButton.remove();
        statusHost.innerHTML = "";
        badge(statusHost, `① 내 자료로 가져왔습니다 · ${payload.dataset.name}`, "live");
        await linkWithStatus(statusHost, ctx, payload.dataset);
      });
    });
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderWebTableInput = renderWebTableInput;
  window.LessonKit.renderGroupShare = renderGroupShare;
})();
