(function () {

  const CONFIDENCE_LABELS = ["1 전혀 확신 없음", "2", "3", "4 매우 확신"];

  function radioGroup(name, options, className) {
    const wrap = document.createElement("div");
    wrap.className = className;
    const inputs = options.map((option) => {
      const label = document.createElement("label");
      label.className = "lesson-hinge-choice";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = name;
      input.value = option.value;
      label.appendChild(input);
      const text = document.createElement("span");
      text.textContent = option.label;
      label.appendChild(text);
      wrap.appendChild(label);
      return input;
    });
    return { wrap, inputs };
  }

  function selected(inputs) {
    const match = inputs.find((input) => input.checked);
    return match ? match.value : "";
  }

  async function renderDiagItem(body, card, ctx) {
    window.LessonKit.renderExplain(body, card);
    const item = card.item || {};
    const readOnly = ctx.role === "teacher" || ctx.role === "admin";
    const baseUrl = `/api/lessons/diag/${encodeURIComponent(ctx.lessonId)}/items/${encodeURIComponent(item.item_id)}/response`
      + `?track=${encodeURIComponent(ctx.track || "")}&scenario=${encodeURIComponent(ctx.scenario || "")}`;

    const form = document.createElement("div");
    form.className = "lesson-diag";
    body.appendChild(form);

    const question = document.createElement("p");
    question.className = "lesson-discuss-question";
    question.textContent = item.question || "";
    form.appendChild(question);

    const choices = radioGroup(
      `diag-${item.item_id}`,
      (item.choices || []).map((choice) => ({ value: choice.key, label: `${choice.key} ${choice.label}` })),
      "lesson-hinge-choices",
    );
    form.appendChild(choices.wrap);

    const reasonHeading = document.createElement("p");
    reasonHeading.className = "lesson-diag-subheading";
    form.appendChild(reasonHeading);
    let reasonChoices = { wrap: null, inputs: [] };
    if (item.reason_choices?.length) {
      reasonHeading.textContent = "그렇게 생각한 이유를 고르세요. 맞는 것이 없으면 아래에 직접 쓰세요.";
      reasonChoices = radioGroup(
        `diag-reason-${item.item_id}`,
        item.reason_choices.map((choice) => ({ value: choice.key, label: `${choice.key} ${choice.label}` })),
        "lesson-hinge-choices",
      );
      form.appendChild(reasonChoices.wrap);
    } else {
      reasonHeading.textContent = "그렇게 생각한 이유를 직접 쓰세요.";
    }
    const reasonText = document.createElement("textarea");
    reasonText.className = "lesson-discuss-input";
    reasonText.rows = 2;
    reasonText.placeholder = item.reason_choices?.length ? "기타 (직접 쓰기)" : "이유를 적어 주세요.";
    form.appendChild(reasonText);

    const confidenceHeading = document.createElement("p");
    confidenceHeading.className = "lesson-diag-subheading";
    confidenceHeading.textContent = "지금 답에 얼마나 확신이 있나요?";
    form.appendChild(confidenceHeading);
    const confidence = radioGroup(
      `diag-conf-${item.item_id}`,
      CONFIDENCE_LABELS.map((label, index) => ({ value: String(index + 1), label })),
      "lesson-diag-confidence",
    );
    form.appendChild(confidence.wrap);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "lesson-connector-fetch";
    button.textContent = "저장하기";
    form.appendChild(button);
    const note = document.createElement("p");
    note.className = "lesson-note";
    note.hidden = true;
    form.appendChild(note);

    if (readOnly) {
      [...choices.inputs, ...reasonChoices.inputs, ...confidence.inputs].forEach((input) => {
        input.disabled = true;
      });
      reasonText.readOnly = true;
      button.hidden = true;
      note.textContent = "교사 화면입니다. 학생은 각자 기기에서 답하고, 응답은 진단 CSV로 내려받습니다.";
      note.hidden = false;
      return null;
    }

    let saved = false;
    const listeners = [];
    function markSaved() {
      if (saved) return;
      saved = true;
      listeners.forEach((listener) => listener());
    }

    button.addEventListener("click", async () => {
      const choice = selected(choices.inputs);
      if (!choice) {
        window.LessonKit.showError("먼저 보기 중 하나를 골라 주세요.");
        return;
      }
      const reasonChoice = selected(reasonChoices.inputs);
      if (!reasonChoice && !reasonText.value.trim()) {
        window.LessonKit.showError("이유를 고르거나 직접 적어 주세요.");
        return;
      }
      const conf = selected(confidence.inputs);
      if (!conf) {
        window.LessonKit.showError("확신도(1~4)를 표시해 주세요.");
        return;
      }
      button.disabled = true;
      try {
        await window.StatApi.request(baseUrl, {
          method: "POST",
          body: JSON.stringify({
            choice,
            reason_choice: reasonChoice,
            reason_text: reasonText.value.trim(),
            confidence: Number(conf),
          }),
        });
        note.textContent = "저장했습니다. 다음 카드로 넘어가세요. (다시 고르면 수정됩니다)";
        note.hidden = false;
        button.textContent = "수정해서 다시 저장";
        markSaved();
      } catch (error) {
        window.LessonKit.showError(error.message || "저장하지 못했습니다.");
      } finally {
        button.disabled = false;
      }
    });

    try {
      const mine = await window.StatApi.request(baseUrl);
      if (mine?.choice) {
        const match = choices.inputs.find((input) => input.value === mine.choice);
        if (match) match.checked = true;
        const reasonMatch = reasonChoices.inputs.find((input) => input.value === mine.reason_choice);
        if (reasonMatch) reasonMatch.checked = true;
        reasonText.value = mine.reason_text || "";
        const confMatch = confidence.inputs.find((input) => input.value === String(mine.confidence));
        if (confMatch) confMatch.checked = true;
        note.textContent = "저장된 응답입니다. 고치면 다시 저장할 수 있습니다.";
        note.hidden = false;
        button.textContent = "수정해서 다시 저장";
        markSaved();
      }
    } catch (_error) {
    }

    return {
      isAllComplete() {
        return saved;
      },
      onChange(listener) {
        listeners.push(listener);
      },
    };
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderDiagItem = renderDiagItem;
})();
