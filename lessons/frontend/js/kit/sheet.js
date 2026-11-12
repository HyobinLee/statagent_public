(function () {
  function buildTable(rows, columns) {
    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.display_name || column.name;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => {
        const td = document.createElement("td");
        const value = row[column.name];
        td.textContent = value === null || value === undefined ? "" : value;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  async function fetchSheetData(datasetId, limit) {
    const cacheKey = `lesson-sheet:${datasetId}:${limit}`;
    try {
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) return JSON.parse(cached);
    } catch (_error) {   }
    const data = await window.StatApi.request(`/api/datasets/${encodeURIComponent(datasetId)}/sheet?limit=${limit}`);
    try {
      const text = JSON.stringify(data);
      if (text.length < 400000) sessionStorage.setItem(cacheKey, text);
    } catch (_error) {   }
    return data;
  }

  async function renderSheet(container, datasetId, opts = {}) {
    container.innerHTML = "<p class=\"lesson-loading\">자료를 불러오는 중…</p>";
    const limit = opts.limit || 20;
    const previewRows = opts.previewRows || 5;
    const data = await fetchSheetData(datasetId, limit);
    const rows = data.rows || [];
    const allColumns = data.columns || [];
    const picked = opts.columns?.length
      ? opts.columns.map((name) => allColumns.find((column) => column.name === name)).filter(Boolean)
      : [];
    const columns = picked.length ? picked : allColumns;
    container.innerHTML = "";

    const tableHost = document.createElement("div");
    container.appendChild(tableHost);
    let expanded = rows.length <= previewRows;
    tableHost.appendChild(buildTable(expanded ? rows : rows.slice(0, previewRows), columns));

    const scrollHint = document.createElement("p");
    scrollHint.className = "lesson-sheet-note lesson-sheet-scroll-hint";
    scrollHint.textContent = "열이 더 있습니다. 표를 옆으로 밀어 보세요. →";
    scrollHint.hidden = true;
    container.appendChild(scrollHint);
    const updateScrollHint = () => {
      const table = tableHost.querySelector("table");
      scrollHint.hidden = !table || table.scrollWidth <= table.clientWidth + 4;
    };
    requestAnimationFrame(updateScrollHint);
    window.addEventListener("resize", updateScrollHint);

    if (!expanded) {
      const expandButton = document.createElement("button");
      expandButton.type = "button";
      expandButton.className = "lesson-connector-fetch";
      expandButton.textContent = `표 전체 보기 (${rows.length}행)`;
      expandButton.addEventListener("click", () => {
        expanded = true;
        tableHost.innerHTML = "";
        tableHost.appendChild(buildTable(rows, columns));
        expandButton.remove();
        requestAnimationFrame(updateScrollHint);
      });
      container.appendChild(expandButton);
    }

    if (typeof data.total_row_count === "number" && data.total_row_count > rows.length) {
      const note = document.createElement("p");
      note.className = "lesson-sheet-note";
      note.textContent = `전체 ${data.total_row_count}행 중 ${rows.length}행을 표시했습니다.`;
      container.appendChild(note);
    }
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderSheet = renderSheet;
})();
