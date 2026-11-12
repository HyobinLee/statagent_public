(function () {
  async function renderFlexibleAnalysis(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    const savedSection = document.createElement("section");
    savedSection.className = "flex-saved";
    body.appendChild(savedSection);

    const optionsSection = document.createElement("section");
    body.appendChild(optionsSection);

    const editor = document.createElement("div");
    editor.className = "flex-editor";
    body.appendChild(editor);

    const state = {
      analyses: [],
      options: [],
      inquiry: null,
      current: null,
      dirty: false,
    };

    window.addEventListener("beforeunload", (event) => {
      if (!state.dirty) return;
      event.preventDefault();
      event.returnValue = "";
    });

    function confirmLeaveDirty() {
      if (!state.dirty) return true;
      return window.confirm("저장하지 않은 해석이 있습니다. 저장하지 않고 다른 결과로 넘어갈까요?");
    }

    function argsKey(args) {
      const { dataset_id: _datasetId, ...rest } = args || {};
      return JSON.stringify(rest);
    }

    function titleOf(analysis) {
      const key = argsKey(analysis.tool_args);
      const option = state.options.find(
        (item) => item.tool_name === analysis.tool_name && argsKey(item.tool_args) === key,
      );
      return option?.label || window.LessonKit.describeAnalysis(analysis);
    }

    function selectedIds() {
      const selected = state.inquiry?.presentation?.selected;
      return Array.isArray(selected) ? selected : state.analyses.map((analysis) => analysis.analysis_result_id);
    }

    async function setIncluded(analysisId, included) {
      const current = selectedIds().filter((id) => id !== analysisId);
      if (included) current.push(analysisId);
      const presentation = state.inquiry?.presentation || {};
      const saved = await window.StatApi.request(
        `/api/lessons/inquiry/${encodeURIComponent(ctx.projectId)}/presentation`,
        {
          method: "PUT",
          body: JSON.stringify({
            selected: current,
            conclusion: presentation.conclusion || "",
            limitations: presentation.limitations || "",
          }),
        },
      );
      if (state.inquiry) state.inquiry.presentation = saved;
    }

    function renderSavedList() {
      savedSection.innerHTML = "";
      const heading = document.createElement("h4");
      heading.textContent = "내가 저장한 결과";
      savedSection.appendChild(heading);
      if (!state.analyses.length) {
        const empty = document.createElement("p");
        empty.className = "lesson-note";
        empty.textContent = "아직 저장된 결과가 없습니다. 아래 추천 분석을 실행하면 여기에 쌓입니다.";
        savedSection.appendChild(empty);
        return;
      }
      const included = new Set(selectedIds());
      const activeDatasetId = state.inquiry?.dataset?.dataset_id;
      const list = document.createElement("ul");
      list.className = "flex-saved-list";
      state.analyses.forEach((analysis) => {
        const li = document.createElement("li");
        if (state.current?.analysis_result_id === analysis.analysis_result_id) li.classList.add("active");

        const title = document.createElement("span");
        title.className = "flex-saved-title";
        title.textContent = titleOf(analysis);
        li.appendChild(title);

        const status = document.createElement("span");
        const hasText = Boolean((analysis.interpretation || "").trim());
        status.className = `flex-saved-status ${hasText ? "ok" : "todo"}`;
        status.textContent = hasText ? "해석 저장됨" : "해석 없음";
        li.appendChild(status);

        if (activeDatasetId && analysis.dataset_id !== activeDatasetId) {
          const other = document.createElement("span");
          other.className = "flex-saved-status todo";
          other.textContent = "지금과 다른 자료로 만든 결과";
          li.appendChild(other);
        }

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.textContent = hasText ? "이어서 해석하기" : "해석 적기";
        openButton.addEventListener("click", () => {
          if (state.current?.analysis_result_id === analysis.analysis_result_id) return;
          if (!confirmLeaveDirty()) return;
          openAnalysis(analysis);
        });
        li.appendChild(openButton);

        const includeLabel = document.createElement("label");
        includeLabel.className = "flex-saved-include";
        const includeBox = document.createElement("input");
        includeBox.type = "checkbox";
        includeBox.checked = included.has(analysis.analysis_result_id);
        includeBox.addEventListener("change", async () => {
          includeBox.disabled = true;
          try {
            await setIncluded(analysis.analysis_result_id, includeBox.checked);
          } catch (error) {
            includeBox.checked = !includeBox.checked;
            window.LessonKit.showError(error.message || "발표 포함 여부를 저장하지 못했습니다.");
          } finally {
            includeBox.disabled = false;
          }
        });
        includeLabel.append(includeBox, document.createTextNode(" 발표에 포함"));
        li.appendChild(includeLabel);

        list.appendChild(li);
      });
      savedSection.appendChild(list);
    }

    function openAnalysis(analysis) {
      state.current = analysis;
      state.dirty = false;
      editor.innerHTML = "";

      const heading = document.createElement("h4");
      heading.textContent = titleOf(analysis);
      editor.appendChild(heading);

      const resultHost = document.createElement("div");
      editor.appendChild(resultHost);
      window.LessonKit.renderResultCard(resultHost, analysis, {
        title: titleOf(analysis),
        units: window.LessonKit.inquiryUnitMap(state.inquiry?.dataset),
      });

      const guide = document.createElement("p");
      guide.className = "lesson-note";
      guide.textContent = "관찰한 것 → 근거가 되는 수치 → 이 자료만으로 판단하기 어려운 것 순서로 적어 보세요.";
      editor.appendChild(guide);

      const textarea = document.createElement("textarea");
      textarea.className = "lesson-interpretation-input";
      textarea.rows = 4;
      textarea.placeholder = "이 결과를 보고 알 수 있는 것을 적어 보세요.";
      textarea.value = analysis.interpretation || "";
      editor.appendChild(textarea);

      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.className = "primary";
      saveButton.textContent = "해석 저장하기";
      editor.appendChild(saveButton);

      const savedNote = document.createElement("div");
      editor.appendChild(savedNote);

      textarea.addEventListener("input", () => {
        state.dirty = textarea.value.trim() !== (analysis.interpretation || "").trim();
        savedNote.className = state.dirty ? "lesson-source-badge fallback" : "";
        savedNote.textContent = state.dirty ? "저장하지 않은 변경이 있습니다." : "";
      });

      saveButton.addEventListener("click", async () => {
        const text = textarea.value.trim();
        if (!text) {
          window.LessonKit.showError("해석을 입력한 뒤 저장해 주세요.");
          return;
        }
        saveButton.disabled = true;
        try {
          const updated = await window.StatApi.request(
            `/api/projects/${ctx.projectId}/analyses/${analysis.analysis_result_id}/interpretation`,
            { method: "PUT", body: JSON.stringify({ interpretation_text: text }) },
          );
          analysis.interpretation = updated?.interpretation ?? text;
          state.dirty = false;
          savedNote.className = "lesson-source-badge live";
          savedNote.textContent = "해석을 저장했습니다.";
          renderSavedList();
          window.LessonKit.notifyInquiryChanged?.();
        } catch (error) {
          window.LessonKit.showError(error.message || "해석을 저장하지 못했습니다.");
        } finally {
          saveButton.disabled = false;
        }
      });

      renderSavedList();
      editor.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function renderOptions() {
      optionsSection.innerHTML = "";
      const heading = document.createElement("h4");
      heading.textContent = "추천 분석으로 새 결과 만들기";
      optionsSection.appendChild(heading);

      if (!state.inquiry?.dataset) {
        const empty = document.createElement("p");
        empty.className = "lesson-note";
        empty.textContent = "탐구에 연결된 자료가 없습니다. 5차시 '표를 직접 입력해 자료 만들기' 또는 '모둠원의 자료 쓰기'에서 자료를 연결한 뒤 다시 열어 주세요.";
        optionsSection.appendChild(empty);
        return;
      }
      if (!state.options.length) {
        const empty = document.createElement("p");
        empty.className = "lesson-note";
        empty.textContent = "이 자료에서는 추천할 분석을 찾지 못했습니다. 5차시에서 자료를 다시 확인해 주세요.";
        optionsSection.appendChild(empty);
        return;
      }

      const buttonRow = document.createElement("div");
      buttonRow.className = "lesson-analysis-options";
      optionsSection.appendChild(buttonRow);

      state.options.forEach((option) => {
        const optionButton = document.createElement("button");
        optionButton.type = "button";
        optionButton.textContent = option.label;
        optionButton.title = option.description || "";
        buttonRow.appendChild(optionButton);

        optionButton.addEventListener("click", async () => {
          if (!confirmLeaveDirty()) return;
          optionButton.disabled = true;
          state.dirty = false;
          editor.textContent = "에이전트가 분석하는 중…";
          try {
            const result = await window.LessonKit.runFixedAnalysis(ctx.projectId, option.tool_name, option.tool_args);
            state.analyses.push(result);
            window.LessonKit.notifyInquiryChanged?.();
            openAnalysis(result);
          } catch (error) {
            editor.textContent = "";
            window.LessonKit.showError(error.message || "분석을 실행하지 못했습니다.");
          } finally {
            optionButton.disabled = false;
          }
        });
      });
    }

    savedSection.textContent = "저장한 결과를 불러오는 중…";
    try {
      [state.inquiry, state.analyses] = await Promise.all([
        window.LessonKit.fetchInquiry(ctx.projectId),
        window.StatApi.request(`/api/projects/${ctx.projectId}/analyses`),
      ]);
    } catch (error) {
      savedSection.textContent = "";
      window.LessonKit.showError(error.message || "저장한 결과를 불러오지 못했습니다.");
      return;
    }

    if (state.inquiry.dataset) {
      try {
        state.options = await window.StatApi.request(`/api/projects/${ctx.projectId}/analysis-options`);
      } catch (error) {
        window.LessonKit.showError(error.message || "추천 분석을 불러오지 못했습니다.");
      }
    }

    renderSavedList();
    renderOptions();
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderFlexibleAnalysis = renderFlexibleAnalysis;
})();
