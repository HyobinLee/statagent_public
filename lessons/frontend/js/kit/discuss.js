(function () {

  const RESUBMIT_SUFFIX = "__r2";

  const SUBMIT_LABELS = {
    predict: "예측 보내기",
    predict_pair: "예측 보내기",
    hinge: "선택과 이유 보내기",
    evidence: "근거 보내기",
    exit: "오늘의 답 보내기",
  };

  function isPredictType(type) {
    return type === "predict" || type === "predict_pair";
  }

  function pairFieldName(field) {
    return field.short || field.label || field.key;
  }

  function escapeRegExp(text) {
    return String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function formatPredictPair(fields, values, reason) {
    const parts = fields.map((field, index) => `${pairFieldName(field)} ${values[index]}${field.unit || ""}`);
    parts.push(`이유: ${reason}`);
    return parts.join(" / ");
  }

  function parsePredictPair(text, fields) {
    const source = String(text || "");
    const reasonAt = source.indexOf(" / 이유:");
    const head = reasonAt >= 0 ? source.slice(0, reasonAt) : source;
    const reason = reasonAt >= 0 ? source.slice(reasonAt + " / 이유:".length).trim() : "";
    const segments = head.split(" / ");
    const values = (fields || []).map((field, index) => {
      const pattern = new RegExp(`(-?\\d+(?:\\.\\d+)?)\\s*${escapeRegExp(field.unit || "")}\\s*$`);
      const match = pattern.exec(segments[index] || "");
      return match ? Number(match[1]) : null;
    });
    return { values, reason };
  }

  let activeEvidenceInput = null;

  function insertEvidenceValue(value) {
    if (!activeEvidenceInput || !document.body.contains(activeEvidenceInput)) return false;
    const current = activeEvidenceInput.value;
    activeEvidenceInput.value = current ? `${current.replace(/\s+$/, "")} ${value}` : String(value);
    activeEvidenceInput.dispatchEvent(new Event("input"));
    return true;
  }

  function createPromptBlock(prompt, ctx, state, options = {}) {
    const promptId = options.promptId || prompt.prompt_id;
    const item = document.createElement("div");
    item.className = "lesson-discuss-item";
    if (options.resubmit) item.classList.add("lesson-resubmit-item");

    const question = document.createElement("p");
    question.className = "lesson-discuss-question";
    question.textContent = options.question || prompt.question;
    item.appendChild(question);

    let choiceInputs = [];
    if (!options.resubmit && prompt.type === "hinge" && prompt.choices?.length) {
      const list = document.createElement("div");
      list.className = "lesson-hinge-choices";
      choiceInputs = prompt.choices.map((choice) => {
        const label = document.createElement("label");
        label.className = "lesson-hinge-choice";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `hinge-${promptId}`;
        input.value = choice.key;
        label.appendChild(input);
        const text = document.createElement("span");
        text.textContent = `${choice.key}. ${choice.label}`;
        label.appendChild(text);
        list.appendChild(label);
        return input;
      });
      item.appendChild(list);
    }

    const pairFields = !options.resubmit && prompt.type === "predict_pair" ? prompt.fields || [] : [];
    const pairInputs = pairFields.map((field) => {
      const row = document.createElement("label");
      row.className = "lesson-pair-field";
      const name = document.createElement("span");
      name.className = "lesson-pair-label";
      name.textContent = field.label || field.key;
      row.appendChild(name);
      const input = document.createElement("input");
      input.type = "number";
      input.inputMode = "numeric";
      input.className = "lesson-pair-input";
      if (field.min !== undefined) input.min = String(field.min);
      if (field.max !== undefined) input.max = String(field.max);
      input.step = "1";
      row.appendChild(input);
      if (field.unit) {
        const unit = document.createElement("span");
        unit.className = "lesson-pair-unit";
        unit.textContent = field.unit;
        row.appendChild(unit);
      }
      return { field, input, row };
    });
    if (pairInputs.length) {
      const list = document.createElement("div");
      list.className = "lesson-pair-fields";
      pairInputs.forEach(({ row }) => list.appendChild(row));
      item.appendChild(list);
    }

    const textarea = document.createElement("textarea");
    textarea.className = "lesson-discuss-input";
    textarea.rows = 3;
    textarea.placeholder = options.placeholder
      || prompt.placeholder
      || (prompt.type === "hinge" ? "그렇게 고른 이유를 적어 주세요." : "");
    item.appendChild(textarea);

    let canClickNumbers = Boolean(options.canClickNumbers);
    let evidenceHint = null;
    function evidenceHintText() {
      return canClickNumbers
        ? "표나 그래프에서 확인한 수치를 하나 이상 넣어 주세요. 결과 표의 숫자를 누르면 이 칸에 들어갑니다."
        : "표나 그래프에서 확인한 수치를 하나 이상 직접 적어 주세요.";
    }
    if (prompt.type === "evidence" && !options.resubmit) {
      const hint = document.createElement("p");
      hint.className = "lesson-evidence-hint";
      hint.textContent = evidenceHintText();
      evidenceHint = hint;
      item.appendChild(hint);
    }
    if (prompt.type === "evidence" && !options.resubmit && !options.preview) {
      textarea.addEventListener("focus", () => {
        activeEvidenceInput = textarea;
      });
      if (!activeEvidenceInput) activeEvidenceInput = textarea;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "lesson-connector-fetch";
    const submitLabel = options.resubmit ? "다시 보내기" : SUBMIT_LABELS[prompt.type] || "의견 보내기";
    button.textContent = submitLabel;
    item.appendChild(button);

    const note = document.createElement("p");
    note.className = "lesson-note";
    note.hidden = true;
    item.appendChild(note);

    const feedbackEl = document.createElement("p");
    feedbackEl.className = "lesson-teacher-feedback";
    feedbackEl.hidden = true;
    item.appendChild(feedbackEl);

    const peersToggle = document.createElement("button");
    peersToggle.type = "button";
    peersToggle.className = "lesson-peers-toggle";
    peersToggle.textContent = "친구들 의견 보기";
    peersToggle.hidden = true;
    const peersPanel = document.createElement("div");
    peersPanel.className = "lesson-peers";
    peersPanel.hidden = true;
    if (!options.preview) {
      item.appendChild(peersToggle);
      item.appendChild(peersPanel);
    }

    if (options.preview) {
      choiceInputs.forEach((input) => {
        input.disabled = true;
      });
      pairInputs.forEach(({ input }) => {
        input.disabled = true;
      });
      textarea.disabled = true;
      button.disabled = true;
      const noop = () => {};
      return {
        element: item,
        freeze: noop,
        onReveal: noop,
        setClickableNumbers(value) {
          canClickNumbers = Boolean(value);
          if (evidenceHint) evidenceHint.textContent = evidenceHintText();
        },
      };
    }

    let hasSubmitted = false;
    let revealedFirst = false;
    let lastSent = null;
    let sentNote = "";

    const inputStartKey = `lesson-input-start:${ctx.lessonId}:${promptId}:${
      window.StatAuth?.getProfile?.()?.user_id || "anon"}`;
    let inputStartedAt = null;
    try {
      const saved = Number(window.localStorage.getItem(inputStartKey));
      if (saved > 0 && saved <= Date.now()) inputStartedAt = saved;
    } catch {
    }

    function markInputStart() {
      if (hasSubmitted || inputStartedAt !== null) return;
      inputStartedAt = Date.now();
      try {
        window.localStorage.setItem(inputStartKey, String(inputStartedAt));
      } catch {
      }
    }

    function takeInputMs() {
      if (inputStartedAt === null) return undefined;
      const elapsed = Date.now() - inputStartedAt;
      return elapsed >= 0 && elapsed <= 6 * 60 * 60 * 1000 ? elapsed : undefined;
    }

    function clearInputStart() {
      inputStartedAt = null;
      try {
        window.localStorage.removeItem(inputStartKey);
      } catch {
      }
    }

    function showNote(text) {
      note.textContent = text;
      note.hidden = false;
    }

    function snapshot() {
      return JSON.stringify([
        textarea.value.trim(),
        pairInputs.map(({ input }) => input.value.trim()),
        selectedChoice(),
      ]);
    }

    function formatTime(stamp) {
      const date = stamp ? new Date(stamp) : new Date();
      if (Number.isNaN(date.getTime())) return "";
      return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
    }

    function showSent(stamp, again) {
      const time = formatTime(stamp);
      const head = again ? "고친 의견을 다시 보냈습니다" : "보냈습니다";
      sentNote = `${head}${time ? ` (${time})` : ""}. 화면에는 이름 없이 표시됩니다.`;
      item.classList.add("is-sent");
      item.classList.remove("is-dirty");
      button.classList.add("is-sent");
      button.disabled = true;
      button.textContent = again ? "✓ 다시 보냄" : "✓ 보냄";
      showNote(sentNote);
      peersToggle.hidden = false;
      if (again) {
        item.classList.remove("is-flash");
        void item.offsetWidth;
        item.classList.add("is-flash");
      }
    }

    function updateDirty() {
      if (!hasSubmitted || textarea.readOnly) return;
      const dirty = snapshot() !== lastSent;
      item.classList.toggle("is-dirty", dirty);
      item.classList.toggle("is-sent", !dirty);
      button.classList.toggle("is-sent", !dirty);
      button.disabled = !dirty;
      if (dirty) {
        button.textContent = "수정해서 다시 보내기";
        showNote("고친 내용은 아직 보내지 않았습니다. '수정해서 다시 보내기'를 눌러야 바뀝니다.");
      } else {
        button.textContent = "✓ 보냄";
        showNote(sentNote);
      }
    }

    function onEdit() {
      markInputStart();
      updateDirty();
    }

    textarea.addEventListener("input", onEdit);
    pairInputs.forEach(({ input }) => input.addEventListener("input", onEdit));
    choiceInputs.forEach((input) => input.addEventListener("change", onEdit));

    function renderPeers(peers) {
      peersPanel.innerHTML = "";
      const head = document.createElement("div");
      head.className = "lesson-peers-head";
      const title = document.createElement("span");
      title.textContent = peers.length ? `친구들 의견 ${peers.length}개` : "친구들 의견";
      head.appendChild(title);
      const refresh = document.createElement("button");
      refresh.type = "button";
      refresh.className = "lesson-peers-refresh";
      refresh.textContent = "새로 보기";
      refresh.addEventListener("click", loadPeers);
      head.appendChild(refresh);
      peersPanel.appendChild(head);
      if (!peers.length) {
        const empty = document.createElement("p");
        empty.className = "lesson-peers-empty";
        empty.textContent = "아직 다른 친구의 의견이 없습니다.";
        peersPanel.appendChild(empty);
        return;
      }
      const list = document.createElement("ul");
      list.className = "lesson-peers-list";
      peers.forEach((peer) => {
        const li = document.createElement("li");
        li.className = "lesson-peer";
        if (peer.choice) {
          const chip = document.createElement("span");
          chip.className = "lesson-peer-choice";
          chip.textContent = peer.choice;
          li.appendChild(chip);
        }
        const text = document.createElement("span");
        text.textContent = peer.text;
        li.appendChild(text);
        list.appendChild(li);
      });
      peersPanel.appendChild(list);
    }

    async function loadPeers() {
      peersPanel.hidden = false;
      peersPanel.textContent = "친구들 의견을 불러오는 중…";
      try {
        const peers = await window.StatApi.request(
          `/api/lessons/discuss/${encodeURIComponent(ctx.lessonId)}/prompts/${encodeURIComponent(promptId)}/peers`,
        );
        renderPeers(Array.isArray(peers) ? peers : []);
      } catch (error) {
        peersPanel.textContent = error.message || "친구들 의견을 불러오지 못했습니다.";
      }
    }

    peersToggle.addEventListener("click", () => {
      if (peersPanel.hidden) {
        peersToggle.textContent = "친구들 의견 접기";
        loadPeers();
      } else {
        peersPanel.hidden = true;
        peersToggle.textContent = "친구들 의견 보기";
      }
    });

    function showFeedback(text) {
      if (!text) return;
      feedbackEl.textContent = `선생님 피드백: ${text}`;
      feedbackEl.hidden = false;
    }

    function selectedChoice() {
      const checked = choiceInputs.find((input) => input.checked);
      return checked ? checked.value : "";
    }

    function markSubmitted(stamp, again = false) {
      hasSubmitted = true;
      state.submitted.add(promptId);
      lastSent = snapshot();
      showSent(stamp, again);
      state.notify();
    }

    function readPairValues() {
      const values = [];
      for (const { field, input } of pairInputs) {
        const raw = input.value.trim();
        const name = field.label || field.key;
        if (raw === "") return { error: `'${name}' 칸에 숫자를 넣어 주세요.` };
        const value = Number(raw);
        if (!Number.isFinite(value)) return { error: `'${name}' 칸에는 숫자만 넣어 주세요.` };
        const tooSmall = field.min !== undefined && value < field.min;
        const tooLarge = field.max !== undefined && value > field.max;
        if (tooSmall || tooLarge) {
          return { error: `'${name}' 칸에는 ${field.min ?? ""}에서 ${field.max ?? ""} 사이의 숫자를 넣어 주세요.` };
        }
        values.push(value);
      }
      return { values };
    }

    async function submit() {
      let text = textarea.value.trim();
      if (pairInputs.length) {
        const checked = readPairValues();
        if (checked.error) {
          window.LessonKit.showError(checked.error);
          return;
        }
        if (!text) {
          window.LessonKit.showError("그렇게 생각한 이유를 한 문장이라도 적은 뒤에 보내 주세요.");
          return;
        }
        text = formatPredictPair(pairFields, checked.values, text);
      }
      if (!text) {
        window.LessonKit.showError("한 문장이라도 적은 뒤에 보내 주세요.");
        return;
      }
      if (choiceInputs.length && !selectedChoice()) {
        window.LessonKit.showError("먼저 선택지 중 하나를 골라 주세요.");
        return;
      }
      if (prompt.type === "evidence" && !options.resubmit && !/\d/.test(text)) {
        window.LessonKit.showError(
          canClickNumbers
            ? "표나 그래프의 값을 하나 이상 넣어 주세요. 결과 표의 숫자를 누르면 입력란에 들어갑니다."
            : "표나 그래프에서 확인한 값을 하나 이상 직접 적어 주세요.",
        );
        return;
      }
      const again = hasSubmitted;
      button.disabled = true;
      button.textContent = "보내는 중…";
      try {
        const saved = await window.StatApi.request(
          `/api/lessons/discuss/${encodeURIComponent(ctx.lessonId)}/prompts/${encodeURIComponent(promptId)}/responses`,
          {
            method: "POST",
            body: JSON.stringify({
              text,
              choice: selectedChoice(),
              after_reveal: revealedFirst,
              input_ms: again ? undefined : takeInputMs(),
            }),
          },
        );
        if (!again) clearInputStart();
        markSubmitted(saved?.updated_at, again);
        if (revealedFirst) freeze();
      } catch (error) {
        window.LessonKit.showError(error.message || "의견을 보내지 못했습니다.");
        button.disabled = false;
        button.textContent = again ? "수정해서 다시 보내기" : submitLabel;
      }
    }

    button.addEventListener("click", submit);

    window.StatApi
      .request(
        `/api/lessons/discuss/${encodeURIComponent(ctx.lessonId)}/prompts/${encodeURIComponent(promptId)}/responses`,
      )
      .then((responses) => {
        const mine = Array.isArray(responses) ? responses[0] : null;
        if (mine?.text) {
          if (pairInputs.length) {
            const parsed = parsePredictPair(mine.text, pairFields);
            pairInputs.forEach(({ input }, index) => {
              if (parsed.values[index] !== null) input.value = String(parsed.values[index]);
            });
            textarea.value = parsed.reason || mine.text;
          } else {
            textarea.value = mine.text;
          }
          if (mine.choice) {
            const match = choiceInputs.find((input) => input.value === mine.choice);
            if (match) match.checked = true;
          }
          markSubmitted(mine.updated_at || mine.created_at);
          showFeedback(mine.feedback);
          if (revealedFirst) freeze();
          options.onLoaded?.(mine);
        }
      })
      .catch(() => {
      });

    function freeze() {
      if (textarea.readOnly) return;
      textarea.readOnly = true;
      textarea.classList.add("lesson-locked-input");
      choiceInputs.forEach((input) => {
        input.disabled = true;
      });
      pairInputs.forEach(({ input }) => {
        input.readOnly = true;
        input.classList.add("lesson-locked-input");
      });
      button.hidden = true;
      showNote("결과를 연 뒤에는 처음 예측을 고칠 수 없습니다. 바뀐 생각은 아래 '다시 보내기' 칸에 쓰세요.");
    }

    function onReveal() {
      if (hasSubmitted) {
        freeze();
        return;
      }
      if (revealedFirst) return;
      revealedFirst = true;
      showNote("결과가 먼저 열렸습니다. 지금 생각을 적어 보내면 다음 카드로 넘어갈 수 있습니다.");
    }

    function setClickableNumbers(value) {
      canClickNumbers = Boolean(value);
      if (evidenceHint) evidenceHint.textContent = evidenceHintText();
    }

    return { element: item, freeze, onReveal, setClickableNumbers };
  }

  function renderDiscussInputs(container, prompts, ctx, opts = {}) {
    const preview = Boolean(opts.preview);
    const wrap = document.createElement("div");
    wrap.className = "lesson-discuss-inputs";
    if (preview) wrap.classList.add("lesson-discuss-preview");

    const state = {
      submitted: new Set(),
      listeners: [],
      notify() {
        this.listeners.forEach((listener) => listener());
      },
    };

    const resubmitBlocks = [];
    const blocks = [];
    const freezeOnReveal = [];

    (prompts || []).forEach((prompt) => {
      const original = createPromptBlock(prompt, ctx, state, { canClickNumbers: opts.canClickNumbers, preview });
      blocks.push(original);
      wrap.appendChild(original.element);

      if (prompt.requires_resubmit) {
        freezeOnReveal.push(original);
        const resubmit = createPromptBlock(prompt, ctx, state, {
          promptId: `${prompt.prompt_id}${RESUBMIT_SUFFIX}`,
          resubmit: true,
          preview,
          canClickNumbers: opts.canClickNumbers,
          question: "결과를 확인했습니다. 처음 예측을 유지하나요, 수정하나요? 결과에서 본 수치를 근거로 다시 보내 주세요.",
          placeholder: "예) 처음 예측을 유지한다. 왜냐하면 결과에서 ~가 ~였기 때문이다. / 예측을 바꾼다. ~를 보니 ~였다.",
          onLoaded: () => {
            resubmit.element.hidden = false;
            original.freeze();
          },
        });
        resubmit.element.hidden = true;
        resubmitBlocks.push(resubmit.element);
        wrap.appendChild(resubmit.element);
      }
    });

    container.appendChild(wrap);

    const predictIds = (prompts || [])
      .filter((prompt) => isPredictType(prompt.type) && prompt.prompt_id)
      .map((prompt) => prompt.prompt_id);
    const requiredIds = (prompts || []).filter((prompt) => prompt.prompt_id).map((prompt) => prompt.prompt_id);

    return {
      isPredictComplete() {
        return predictIds.every((id) => state.submitted.has(id));
      },
      isAllComplete() {
        return requiredIds.every((id) => state.submitted.has(id));
      },
      onChange(listener) {
        state.listeners.push(listener);
      },
      setClickableNumbers(value) {
        blocks.forEach((block) => block.setClickableNumbers(value));
      },
      showResubmits() {
        resubmitBlocks.forEach((block) => {
          block.hidden = false;
        });
        freezeOnReveal.forEach((block) => block.onReveal());
      },
    };
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderDiscussInputs = renderDiscussInputs;
  window.LessonKit.insertEvidenceValue = insertEvidenceValue;
  window.LessonKit.RESUBMIT_SUFFIX = RESUBMIT_SUFFIX;
  window.LessonKit.isPredictType = isPredictType;
  window.LessonKit.formatPredictPair = formatPredictPair;
  window.LessonKit.parsePredictPair = parsePredictPair;
})();
