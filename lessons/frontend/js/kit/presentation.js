(function () {

  function chartValueColumns(analysis) {
    const args = analysis.tool_args || {};
    if (args.category_col && args.value_col) return [args.category_col, args.value_col];
    if (args.region_col && args.value_col) return [args.region_col, args.value_col];
    if (args.x_col && args.y_col) return [args.x_col, args.y_col];
    return null;
  }

  function addSection(sheet, heading) {
    const section = document.createElement("section");
    section.className = "presentation-section";
    const h = document.createElement("h4");
    h.textContent = heading;
    section.appendChild(h);
    sheet.appendChild(section);
    return section;
  }

  function addParagraph(section, text, missingText) {
    const p = document.createElement("p");
    if (text) {
      p.textContent = text;
    } else {
      p.className = "inquiry-missing";
      p.textContent = missingText;
    }
    section.appendChild(p);
  }

  async function renderPresentation(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    const container = document.createElement("div");
    container.textContent = "발표 자료를 불러오는 중…";
    body.appendChild(container);

    let inquiry;
    let analyses;
    try {
      [inquiry, analyses] = await Promise.all([
        window.LessonKit.fetchInquiry(ctx.projectId),
        window.StatApi.request(`/api/projects/${ctx.projectId}/analyses`),
      ]);
    } catch (error) {
      container.textContent = "";
      window.LessonKit.showError(error.message || "발표 자료를 불러오지 못했습니다.");
      return;
    }

    const byId = new Map(analyses.map((analysis) => [analysis.analysis_result_id, analysis]));
    const presentation = inquiry.presentation || {};
    let selected = Array.isArray(presentation.selected)
      ? presentation.selected.filter((id) => byId.has(id))
      : analyses.map((analysis) => analysis.analysis_result_id);
    let conclusion = presentation.conclusion || "";
    let limitations = presentation.limitations || "";
    const units = window.LessonKit.inquiryUnitMap(inquiry.dataset);
    const inputs = { conclusion: null, limitations: null };

    async function persist() {
      const saved = await window.StatApi.request(
        `/api/lessons/inquiry/${encodeURIComponent(ctx.projectId)}/presentation`,
        { method: "PUT", body: JSON.stringify({ selected, conclusion, limitations }) },
      );
      selected = (saved.selected || []).filter((id) => byId.has(id));
    }

    container.innerHTML = "";
    const checklistHost = document.createElement("div");
    checklistHost.className = "inquiry-check";
    container.appendChild(checklistHost);

    const composer = document.createElement("details");
    composer.className = "presentation-composer";
    composer.open = true;
    const composerSummary = document.createElement("summary");
    composerSummary.textContent = "발표에 넣을 결과와 순서 고르기";
    composer.appendChild(composerSummary);
    const composerList = document.createElement("ul");
    composerList.className = "flex-saved-list";
    composer.appendChild(composerList);
    container.appendChild(composer);

    const sheet = document.createElement("article");
    sheet.className = "presentation-sheet";
    container.appendChild(sheet);

    function renderChecklist() {
      const chosen = selected.map((id) => byId.get(id)).filter(Boolean);
      const items = [
        { ok: inquiry.question_confirmed, label: "탐구 질문" },
        { ok: Boolean(inquiry.dataset?.source_recorded), label: "자료·출처" },
        { ok: chosen.length > 0, label: "대표 결과 1개 이상" },
        {
          ok: chosen.length > 0 && chosen.every((analysis) => (analysis.interpretation || "").trim()),
          label: "고른 결과마다 해석",
        },
        { ok: Boolean(conclusion.trim()), label: "결론" },
        { ok: Boolean(limitations.trim()), label: "한계·후속 질문" },
      ];
      checklistHost.innerHTML = "";
      const heading = document.createElement("strong");
      const missing = items.filter((item) => !item.ok).length;
      heading.textContent = missing ? `발표 한 장 점검 — 보완할 항목 ${missing}개` : "발표 한 장 점검 — 모두 채웠습니다";
      checklistHost.appendChild(heading);
      const list = document.createElement("ul");
      list.className = "inquiry-check-list compact";
      items.forEach((item) => {
        const li = document.createElement("li");
        li.className = item.ok ? "ok" : "todo";
        li.textContent = `${item.ok ? "확인" : "보완 필요"} · ${item.label}`;
        list.appendChild(li);
      });
      checklistHost.appendChild(list);
    }

    function renderComposer() {
      composerList.innerHTML = "";
      if (!analyses.length) {
        const empty = document.createElement("li");
        empty.textContent = "아직 저장된 분석 결과가 없습니다. 6차시에서 먼저 분석을 실행해 주세요.";
        composerList.appendChild(empty);
        return;
      }
      const ordered = [
        ...selected.map((id) => byId.get(id)).filter(Boolean),
        ...analyses.filter((analysis) => !selected.includes(analysis.analysis_result_id)),
      ];
      ordered.forEach((analysis) => {
        const id = analysis.analysis_result_id;
        const position = selected.indexOf(id);
        const li = document.createElement("li");

        const label = document.createElement("label");
        label.className = "flex-saved-include";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = position >= 0;
        label.append(box, document.createTextNode(` ${window.LessonKit.describeAnalysis(analysis)}`));
        li.appendChild(label);

        const status = document.createElement("span");
        const hasText = Boolean((analysis.interpretation || "").trim());
        status.className = `flex-saved-status ${hasText ? "ok" : "todo"}`;
        status.textContent = hasText ? "해석 있음" : "해석 없음";
        li.appendChild(status);

        const move = async (delta) => {
          const next = position + delta;
          if (position < 0 || next < 0 || next >= selected.length) return;
          const reordered = selected.slice();
          [reordered[position], reordered[next]] = [reordered[next], reordered[position]];
          selected = reordered;
          await saveAndRedraw();
        };
        if (position >= 0) {
          const up = document.createElement("button");
          up.type = "button";
          up.textContent = "위로";
          up.disabled = position === 0;
          up.addEventListener("click", () => move(-1));
          const down = document.createElement("button");
          down.type = "button";
          down.textContent = "아래로";
          down.disabled = position === selected.length - 1;
          down.addEventListener("click", () => move(1));
          li.append(up, down);
        }

        box.addEventListener("change", async () => {
          selected = box.checked ? [...selected, id] : selected.filter((item) => item !== id);
          await saveAndRedraw();
        });
        composerList.appendChild(li);
      });
    }

    function renderResultBlock(section, analysis, index) {
      const card = document.createElement("div");
      card.className = "lesson-presentation-card";
      const title = document.createElement("h5");
      title.textContent = `${index + 1}. ${window.LessonKit.describeAnalysis(analysis)}`;
      card.appendChild(title);

      const resultHost = document.createElement("div");
      card.appendChild(resultHost);
      window.LessonKit.renderResultCard(resultHost, analysis, {
        title: window.LessonKit.describeAnalysis(analysis),
        units,
        rowCount: analysis.dataset_id === inquiry.dataset?.dataset_id ? inquiry.dataset?.row_count : null,
      });

      const hasChart = (analysis.chart_urls || []).some((url) => url.endsWith(".png"));
      const valueColumns = hasChart ? chartValueColumns(analysis) : null;
      if (valueColumns) {
        const values = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "그래프에 쓰인 값 보기";
        values.appendChild(summary);
        const sheetHost = document.createElement("div");
        values.appendChild(sheetHost);
        let loaded = false;
        values.addEventListener("toggle", () => {
          if (!values.open || loaded) return;
          loaded = true;
          window.LessonKit.renderSheet(sheetHost, analysis.dataset_id, { limit: 40, columns: valueColumns }).catch(() => {
            sheetHost.textContent = "값을 불러오지 못했습니다.";
          });
        });
        card.appendChild(values);
      }

      const interpretation = document.createElement("p");
      const text = (analysis.interpretation || "").trim();
      interpretation.className = text ? "presentation-interpretation" : "inquiry-missing";
      interpretation.textContent = text
        ? `해석: ${text}`
        : "보완 필요: 아직 해석을 적지 않았습니다 — 6차시에서 '해석 적기'로 이어서 적을 수 있습니다.";
      card.appendChild(interpretation);
      section.appendChild(card);
    }

    function renderOnePage() {
      sheet.innerHTML = "";
      addParagraph(
        addSection(sheet, "탐구 질문"),
        inquiry.question_confirmed ? inquiry.question : "",
        "보완 필요: 탐구 질문을 정하지 않았습니다 — 5차시에서 질문을 고르세요.",
      );

      const dataSection = addSection(sheet, "자료·출처·기간");
      const dataset = inquiry.dataset;
      if (dataset) {
        const rows = [
          ["자료", dataset.name],
          ["출처", dataset.source_recorded ? [dataset.source, dataset.source_note].filter(Boolean).join(" · ") : ""],
          ["기간", dataset.time_range],
          ["자료 크기", typeof dataset.row_count === "number" ? `${dataset.row_count}행` : ""],
        ];
        const list = document.createElement("dl");
        list.className = "presentation-meta";
        rows.forEach(([label, value]) => {
          const dt = document.createElement("dt");
          dt.textContent = label;
          const dd = document.createElement("dd");
          dd.textContent = value || "(비어 있음 — 직접 적어 설명하세요)";
          if (!value) dd.className = "inquiry-missing";
          list.append(dt, dd);
        });
        dataSection.appendChild(list);
      } else {
        addParagraph(dataSection, "", "보완 필요: 탐구에 연결된 자료가 없습니다.");
      }

      const resultSection = addSection(sheet, "대표 결과와 수치 근거");
      const chosen = selected.map((id) => byId.get(id)).filter(Boolean);
      if (!chosen.length) {
        addParagraph(resultSection, "", "보완 필요: 발표에 넣을 결과를 위에서 하나 이상 고르세요.");
      }
      chosen.forEach((analysis, index) => renderResultBlock(resultSection, analysis, index));

      const writeSection = addSection(sheet, "결론과 한계");
      const conclusionLabel = document.createElement("label");
      conclusionLabel.className = "presentation-field";
      conclusionLabel.textContent = "결론 — 이 자료로 질문에 어떻게 답할 수 있나요?";
      const conclusionInput = document.createElement("textarea");
      conclusionInput.className = "lesson-interpretation-input";
      conclusionInput.rows = 3;
      conclusionInput.value = conclusion;
      conclusionInput.placeholder = "예: 이 자료에서는 ___이 ___보다 ___만큼 높았다. 근거 수치는 ___이다.";
      conclusionLabel.appendChild(conclusionInput);
      inputs.conclusion = conclusionInput;
      writeSection.appendChild(conclusionLabel);

      const limitLabel = document.createElement("label");
      limitLabel.className = "presentation-field";
      limitLabel.textContent = "한계와 후속 질문 — 이 자료만으로 판단하기 어려운 것은 무엇인가요?";
      const limitInput = document.createElement("textarea");
      limitInput.className = "lesson-interpretation-input";
      limitInput.rows = 3;
      limitInput.value = limitations;
      limitInput.placeholder = "예: 지역 평균이라 개인의 지출까지는 말할 수 없다. 차이의 원인은 다른 자료로 확인해야 한다.";
      limitLabel.appendChild(limitInput);
      inputs.limitations = limitInput;
      writeSection.appendChild(limitLabel);

      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.className = "primary";
      saveButton.textContent = "결론·한계 저장하기";
      const savedNote = document.createElement("div");
      saveButton.addEventListener("click", async () => {
        saveButton.disabled = true;
        conclusion = conclusionInput.value;
        limitations = limitInput.value;
        try {
          await persist();
          savedNote.className = "lesson-source-badge live";
          savedNote.textContent = "결론과 한계를 저장했습니다.";
          renderChecklist();
        } catch (error) {
          window.LessonKit.showError(error.message || "저장하지 못했습니다.");
        } finally {
          saveButton.disabled = false;
        }
      });
      writeSection.append(saveButton, savedNote);
    }

    async function saveAndRedraw() {
      if (inputs.conclusion) conclusion = inputs.conclusion.value;
      if (inputs.limitations) limitations = inputs.limitations.value;
      try {
        await persist();
      } catch (error) {
        window.LessonKit.showError(error.message || "발표 구성을 저장하지 못했습니다.");
      }
      renderChecklist();
      renderComposer();
      renderOnePage();
    }

    renderChecklist();
    renderComposer();
    renderOnePage();
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderPresentation = renderPresentation;
})();
