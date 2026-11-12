(function () {
  async function renderCareerSelect(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);

    const container = document.createElement("div");
    container.textContent = "불러오는 중…";
    body.appendChild(container);

    const [fields, existing] = await Promise.all([
      window.StatApi.request(`/api/lessons/careers/fields?track=${encodeURIComponent(ctx?.track || "")}`),
      window.StatApi.request("/api/lessons/careers/me"),
    ]);

    container.innerHTML = "";
    const fieldSelect = document.createElement("select");
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "진로 분야를 선택하세요";
    fieldSelect.appendChild(placeholder);
    fields.forEach((field) => {
      const option = document.createElement("option");
      option.value = field.field_id;
      option.textContent = field.field_name;
      fieldSelect.appendChild(option);
    });
    container.appendChild(fieldSelect);

    const topicList = document.createElement("div");
    topicList.className = "lesson-topic-options";
    container.appendChild(topicList);

    const resultContainer = document.createElement("div");
    container.appendChild(resultContainer);

    let savedTopicId = existing?.topic_id || null;
    let savedQuestion = existing?.question || "";

    async function confirmQuestionChange(nextQuestion) {
      if (!savedQuestion || savedQuestion === nextQuestion || !ctx?.projectId) return true;
      let summary = null;
      try {
        summary = await window.LessonKit.fetchInquiry(ctx.projectId);
      } catch (_error) {
        return true;
      }
      if (!summary.dataset && !summary.analysis_count) return true;
      const kept = [
        summary.dataset ? `자료 '${summary.dataset.name}'` : "",
        summary.analysis_count ? `저장한 결과 ${summary.analysis_count}개` : "",
      ].filter(Boolean).join(", ");
      return window.confirm(
        `탐구 질문을 바꿀까요?\n\n지금 질문: ${savedQuestion}\n새 질문: ${nextQuestion}\n\n` +
          `${kept}은(는) 지워지지 않고 그대로 남습니다. 바꾼 뒤에는 그 자료가 새 질문에 답할 수 있는지 다시 확인하세요.`,
      );
    }

    function showSaved(question) {
      resultContainer.innerHTML = "";
      const badge = document.createElement("div");
      badge.className = "lesson-source-badge live";
      badge.textContent = `탐구 질문으로 정했습니다 · ${question}`;
      resultContainer.appendChild(badge);
    }

    function renderTopics(fieldId) {
      topicList.innerHTML = "";
      const field = fields.find((item) => item.field_id === fieldId);
      if (!field) return;
      field.topics.forEach((topic) => {
        const label = document.createElement("label");
        label.className = "lesson-topic-option";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "career-topic";
        radio.value = topic.topic_id;
        label.appendChild(radio);
        const text = document.createElement("span");
        text.textContent = `${topic.question} (${topic.related_statistics})`;
        label.appendChild(text);
        topicList.appendChild(label);

        radio.addEventListener("change", async () => {
          const restorePrevious = () => {
            radio.checked = false;
            const previous = savedTopicId && topicList.querySelector(`input[value="${savedTopicId}"]`);
            if (previous) previous.checked = true;
          };
          if (!(await confirmQuestionChange(topic.question))) {
            restorePrevious();
            return;
          }
          try {
            const saved = await window.StatApi.request("/api/lessons/careers/me", {
              method: "POST",
              body: JSON.stringify({ field_id: fieldId, topic_id: topic.topic_id, project_id: ctx?.projectId || null }),
            });
            savedTopicId = saved.topic_id;
            savedQuestion = saved.question;
            showSaved(saved.question);
            window.LessonKit.notifyInquiryChanged?.();
          } catch (error) {
            restorePrevious();
            window.LessonKit.showError(error.message || "주제를 저장하지 못했습니다.");
          }
        });
      });
    }

    fieldSelect.addEventListener("change", () => renderTopics(fieldSelect.value));

    if (existing) {
      fieldSelect.value = existing.field_id;
      renderTopics(existing.field_id);
      const savedRadio = topicList.querySelector(`input[value="${existing.topic_id}"]`);
      if (savedRadio) savedRadio.checked = true;
      showSaved(existing.question);
    }
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderCareerSelect = renderCareerSelect;
})();
