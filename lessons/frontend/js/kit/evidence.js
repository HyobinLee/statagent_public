(function () {
  const DTYPE_LABELS = { numeric: "숫자", categorical: "글자" };

  function evidenceUrl(card, ctx) {
    const base = `/api/lessons/projects/${encodeURIComponent(ctx.projectId)}/column-meaning-evidence`;
    const [source, key] = String(card.dataset_from || "").split(":");
    if (source !== "connector" || !key) return base;
    return `${base}?connector=${encodeURIComponent(key)}&lesson_id=${encodeURIComponent(ctx.lessonId)}&track=${encodeURIComponent(ctx.track || "")}`;
  }

  function renderEvidence(body, card, ctx) {
    window.LessonKit.renderExplain(body, card);

    const container = document.createElement("div");
    container.textContent = "근거를 불러오는 중…";
    body.appendChild(container);

    window.StatApi
      .request(evidenceUrl(card, ctx))
      .then((columns) => {
        container.innerHTML = "";
        const table = document.createElement("table");
        table.className = "lesson-stats-table";
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        ["항목 이름", "자료 유형", "단위", "값 예시"].forEach((label) => {
          const th = document.createElement("th");
          th.textContent = label;
          headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement("tbody");
        (columns || []).forEach((column) => {
          const tr = document.createElement("tr");
          const dtypeLabel = DTYPE_LABELS[column.dtype] || column.dtype || "-";
          const unitLabel = column.unit || "—";
          const examplesLabel = (column.value_examples || []).join(", ") || "—";
          [column.name, dtypeLabel, unitLabel, examplesLabel].forEach((value) => {
            const td = document.createElement("td");
            td.textContent = value;
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);
      })
      .catch((error) => {
        container.textContent = "";
        window.LessonKit.showError(error.message || "근거를 불러오지 못했습니다.");
      });
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderEvidence = renderEvidence;
})();
