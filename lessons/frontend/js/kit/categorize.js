(function () {
  async function renderCategorize(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    const container = document.createElement("div");
    container.textContent = "제안을 불러오는 중…";
    body.appendChild(container);

    const { suggestions, categories } = await window.StatApi.request(
      "/api/lessons/transform/category-suggestions",
      {
        method: "POST",
        body: JSON.stringify({ dataset_id: ctx.datasetId, source_column: step.source_column }),
      },
    );

    container.innerHTML = "";
    const scrollWrap = document.createElement("div");
    scrollWrap.className = "lesson-categorize-scroll";
    const table = document.createElement("table");
    table.className = "lesson-categorize-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    [step.source_column, "범주 (AI 제안 · 고쳐도 됨)"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    const selects = [];
    suggestions.forEach(({ value, suggested_category }) => {
      const tr = document.createElement("tr");
      const valueCell = document.createElement("td");
      valueCell.textContent = value;
      tr.appendChild(valueCell);

      const selectCell = document.createElement("td");
      const select = document.createElement("select");
      select.dataset.value = value;
      categories.forEach((category) => {
        const option = document.createElement("option");
        option.value = category;
        option.textContent = category;
        if (category === suggested_category) option.selected = true;
        select.appendChild(option);
      });
      selects.push(select);
      selectCell.appendChild(select);
      tr.appendChild(selectCell);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scrollWrap.appendChild(table);
    container.appendChild(scrollWrap);

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "primary";
    confirmButton.textContent = "범주 확정하기";
    container.appendChild(confirmButton);

    const resultContainer = document.createElement("div");
    container.appendChild(resultContainer);

    confirmButton.addEventListener("click", async () => {
      const mapping = {};
      selects.forEach((select) => {
        mapping[select.dataset.value] = select.value;
      });
      confirmButton.disabled = true;
      confirmButton.textContent = "저장하는 중…";
      try {
        await window.StatApi.request("/api/lessons/transform/apply-category", {
          method: "POST",
          body: JSON.stringify({
            dataset_id: ctx.datasetId,
            source_column: step.source_column,
            new_column: step.new_column || "주식종류",
            mapping,
          }),
        });
        resultContainer.innerHTML = "";
        const badge = document.createElement("div");
        badge.className = "lesson-source-badge live";
        badge.textContent = `확정했습니다 · '${step.new_column || "주식종류"}' 항목이 만들어졌습니다.`;
        resultContainer.appendChild(badge);
        confirmButton.textContent = "다시 확정하기";
      } catch (error) {
        window.LessonKit.showError(error.message || "범주를 저장하지 못했습니다.");
        confirmButton.textContent = "범주 확정하기";
      } finally {
        confirmButton.disabled = false;
      }
    });
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderCategorize = renderCategorize;
})();
