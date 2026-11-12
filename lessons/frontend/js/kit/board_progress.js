(function () {

  const REFRESH_MS = 10000;

  const STATE_LABELS = {
    none: "아직 안 옴",
    seen: "지나감",
    partial: "일부 제출",
    answered: "제출 완료",
  };

  function hasResubmitted(cell) {
    return cell.resubmits > 0 && cell.resubmitted >= cell.resubmits;
  }

  function cellTitle(student, card, cell) {
    const place = `${card.step + 1}단계 ${card.title}`;
    const base = `${student.display_name} / ${place}: ${STATE_LABELS[cell.state]}`;
    const counts = cell.prompts ? ` (${cell.answered}/${cell.prompts} 발문)` : "";
    const resubmit = cell.resubmits > 0 ? (hasResubmitted(cell) ? ", 재제출함" : ", 재제출 아직") : "";
    return `${base}${counts}${resubmit}${cell.current ? ", 지금 보는 카드" : ""}`;
  }

  const PROMPT_TYPE_LABELS = {
    predict: "예측",
    predict_pair: "예측(숫자)",
    hinge: "판별",
    evidence: "근거",
    exit: "출구",
  };

  function median(sorted) {
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function formatNumber(value) {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }

  function renderPredictPairSummary(container, meta, responses) {
    container.innerHTML = "";
    const fields = meta.fields || [];
    if (!fields.length) return;
    const parse = window.LessonKit.parsePredictPair;
    const parsed = (responses || [])
      .filter((response) => !response.board?.hidden)
      .map((response) => parse(response.text, fields).values);

    fields.forEach((field, index) => {
      const values = parsed
        .map((row) => row[index])
        .filter((value) => value !== null && Number.isFinite(value))
        .sort((a, b) => a - b);
      const row = document.createElement("div");
      row.className = "pair-summary-row";

      const line = document.createElement("p");
      line.className = "pair-summary-line";
      const name = field.short || field.label || field.key;
      const unit = field.unit || "";
      line.textContent = values.length
        ? `${name}: 최소 ${formatNumber(values[0])}${unit}, 중앙값 ${formatNumber(median(values))}${unit}, 최대 ${formatNumber(values[values.length - 1])}${unit} (응답 ${values.length}명)`
        : `${name}: 아직 응답이 없습니다.`;
      row.appendChild(line);

      const low = field.min ?? 0;
      const high = field.max ?? 100;
      const span = high - low || 1;
      const plot = document.createElement("div");
      plot.className = "pair-dotplot";
      const stackCount = {};
      values.forEach((value) => {
        const key = Math.round(value);
        const level = stackCount[key] || 0;
        stackCount[key] = level + 1;
        const dot = document.createElement("span");
        dot.className = "pair-dot";
        const share = Math.min(Math.max((value - low) / span, 0), 1);
        dot.style.left = `${share * 100}%`;
        dot.style.bottom = `${level * 9}px`;
        dot.title = `${formatNumber(value)}${unit}`;
        plot.appendChild(dot);
      });
      const maxStack = Math.max(0, ...Object.values(stackCount));
      plot.style.height = `${Math.max(18, maxStack * 9 + 8)}px`;
      row.appendChild(plot);

      const ticks = document.createElement("div");
      ticks.className = "pair-ticks";
      [low, low + span / 2, high].forEach((tick) => {
        const label = document.createElement("span");
        label.textContent = formatNumber(tick);
        ticks.appendChild(label);
      });
      row.appendChild(ticks);

      container.appendChild(row);
    });
  }

  function appendResponse(container, response, label) {
    const block = document.createElement("div");
    block.className = "progress-answer";
    const head = document.createElement("div");
    head.className = "progress-answer-head";
    head.textContent = label;
    block.appendChild(head);

    if (!response) {
      const empty = document.createElement("p");
      empty.className = "progress-answer-empty";
      empty.textContent = "아직 보내지 않았습니다.";
      block.appendChild(empty);
      container.appendChild(block);
      return;
    }

    if (response.choice) {
      const chip = document.createElement("span");
      chip.className = "discuss-chip";
      chip.textContent = response.choice;
      block.appendChild(chip);
    }
    if (response.after_reveal) {
      const chip = document.createElement("span");
      chip.className = "discuss-chip warn";
      chip.textContent = "결과 본 뒤 보냄";
      block.appendChild(chip);
    }
    if (response.edited_after_peers) {
      const chip = document.createElement("span");
      chip.className = "discuss-chip warn";
      chip.textContent = "친구 의견 본 뒤 고침";
      block.appendChild(chip);
    }
    const text = document.createElement("p");
    text.className = "progress-answer-text";
    text.textContent = response.text || "(내용 없음)";
    block.appendChild(text);

    if (response.feedback) {
      const feedback = document.createElement("p");
      feedback.className = "progress-answer-feedback";
      feedback.textContent = `선생님 피드백: ${response.feedback}`;
      block.appendChild(feedback);
    }
    const clock = (stamp) => {
      const date = stamp ? new Date(stamp) : null;
      if (!date || Number.isNaN(date.getTime())) return "";
      return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
    };
    const parts = [];
    const started = clock(response.input_started_at);
    if (started) parts.push(`쓰기 시작 ${started}`);
    const first = clock(response.created_at);
    const last = clock(response.updated_at);
    if (first) {
      const spent = Math.round((new Date(response.created_at) - new Date(response.input_started_at)) / 1000);
      const took = started && spent >= 0
        ? ` (${spent >= 60 ? `${Math.floor(spent / 60)}분 ` : ""}${spent % 60}초 걸림)`
        : "";
      parts.push(`보냄 ${first}${took}`);
    }
    if (last && response.updated_at !== response.created_at) parts.push(`마지막으로 고쳐 보냄 ${last}`);
    if (parts.length) {
      const time = document.createElement("p");
      time.className = "progress-answer-time";
      time.textContent = parts.join(", ");
      block.appendChild(time);
    }
    container.appendChild(block);
  }

  function openCellDetail(options, student, card) {
    document.querySelector(".progress-detail-overlay")?.remove();
    const layer = document.createElement("div");
    layer.className = "progress-detail-overlay";
    layer.innerHTML = `
      <div class="progress-detail" role="dialog" aria-modal="true">
        <div class="progress-head">
          <div>
            <h3 class="progress-detail-title"></h3>
            <p class="progress-sub"></p>
          </div>
          <div class="progress-head-actions">
            <button type="button" class="progress-goto">이 카드로 이동</button>
            <button type="button" class="progress-detail-close" aria-label="닫기">×</button>
          </div>
        </div>
        <div class="progress-detail-body">불러오는 중…</div>
      </div>`;
    document.body.appendChild(layer);

    const close = () => {
      layer.remove();
      document.removeEventListener("keydown", onKey);
    };
    function onKey(event) {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      close();
    }
    document.addEventListener("keydown", onKey, true);
    layer.querySelector(".progress-detail-close").addEventListener("click", close);
    layer.addEventListener("click", (event) => {
      if (event.target === layer) close();
    });
    layer.querySelector(".progress-goto").addEventListener("click", () => {
      options.onGoToCard?.(card);
      close();
    });

    layer.querySelector(".progress-detail-title").textContent = student.display_name;
    layer.querySelector(".progress-sub").textContent = `${card.index + 1}번 카드, ${card.step + 1}단계 ${card.title}`;

    const body = layer.querySelector(".progress-detail-body");
    const query = new URLSearchParams({
      lesson_id: options.lessonId,
      user_id: student.user_id,
      step: String(card.step),
      card: String(card.card),
      track: options.track || "",
      scenario: options.scenario || "",
    });
    window.StatApi
      .request(`/api/lessons/teacher/card-responses?${query.toString()}`)
      .then((data) => {
        body.innerHTML = "";
        if (!(data.prompts || []).length) {
          const note = document.createElement("p");
          note.className = "lesson-note";
          note.textContent = "이 카드에는 답할 발문이 없습니다.";
          body.appendChild(note);
          return;
        }
        data.prompts.forEach((prompt) => {
          const section = document.createElement("section");
          section.className = "progress-prompt";

          const question = document.createElement("p");
          question.className = "progress-prompt-question";
          if (PROMPT_TYPE_LABELS[prompt.type]) {
            const badge = document.createElement("span");
            badge.className = `prompt-type-badge prompt-type-${prompt.type}`;
            badge.textContent = PROMPT_TYPE_LABELS[prompt.type];
            question.appendChild(badge);
          }
          question.appendChild(document.createTextNode(prompt.question || prompt.prompt_id));
          section.appendChild(question);

          if (prompt.observe || prompt.answer) {
            const guide = document.createElement("p");
            guide.className = "prompt-observe-guide";
            const answer = prompt.answer ? ` [정답 ${prompt.answer}]` : "";
            guide.textContent = `관찰 가이드: ${prompt.observe || "응답에서 표적 오개념의 흔적을 살펴보세요."}${answer}`;
            section.appendChild(guide);
          }

          appendResponse(section, prompt.response, prompt.resubmit ? "1차 응답" : "응답");
          if (prompt.resubmit !== null && prompt.resubmit !== undefined) {
            appendResponse(section, prompt.resubmit, "재제출 (결과를 본 뒤)");
          }
          body.appendChild(section);
        });
      })
      .catch((error) => {
        body.textContent = error.message || "응답을 불러오지 못했습니다.";
      });
  }

  function buildOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "progress-overlay";
    overlay.innerHTML = `
      <div class="progress-panel" role="dialog" aria-modal="true" aria-labelledby="progress-title">
        <div class="progress-head">
          <div>
            <h2 class="progress-title" id="progress-title">학생 진행</h2>
            <p class="progress-sub"></p>
          </div>
          <div class="progress-head-actions">
            <button type="button" class="progress-refresh">새로고침</button>
            <button type="button" class="progress-close" aria-label="닫기">×</button>
          </div>
        </div>
        <div class="progress-legend">
          <span class="progress-legend-item"><i class="progress-chip state-answered"></i>제출 완료</span>
          <span class="progress-legend-item"><i class="progress-chip state-partial"></i>일부 제출</span>
          <span class="progress-legend-item"><i class="progress-chip state-seen"></i>지나감</span>
          <span class="progress-legend-item"><i class="progress-chip state-none"></i>아직 안 옴</span>
          <span class="progress-legend-item"><i class="progress-chip is-current"></i>지금 보는 카드</span>
          <span class="progress-legend-item progress-legend-resubmit" hidden><i class="progress-chip state-answered has-resubmit">재</i>재제출함</span>
        </div>
        <div class="progress-body"></div>
        <p class="progress-foot"></p>
      </div>`;
    document.body.appendChild(overlay);
    return overlay;
  }

  function renderTable(body, data, options) {
    const cards = data.cards || [];
    const students = data.students || [];
    const hasResubmitCards = cards.some((card) => (card.resubmit_ids || []).length);
    body.innerHTML = "";

    if (!students.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "이 학급에 학생이 없습니다. 명단을 먼저 만들어 주세요.";
      body.appendChild(empty);
      return;
    }

    const table = document.createElement("table");
    table.className = "progress-table";

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    const corner = document.createElement("th");
    corner.className = "progress-name-col";
    corner.textContent = `학생 ${students.length}명`;
    headRow.appendChild(corner);
    cards.forEach((card) => {
      const th = document.createElement("th");
      th.className = "progress-card-col";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "progress-card-head";
      const resubmitPart = (card.resubmit_ids || []).length ? `, 재제출 ${card.resubmit_count || 0}명` : "";
      button.title = `${card.step + 1}단계 ${card.title} (열람 ${card.seen_count}명, 제출 ${card.answered_count}명${resubmitPart}) — 누르면 이 카드로 이동`;
      const num = document.createElement("span");
      num.className = "progress-card-num";
      num.textContent = String(card.index + 1);
      const step = document.createElement("span");
      step.className = "progress-card-step";
      step.textContent = `${card.step + 1}단계`;
      button.appendChild(num);
      button.appendChild(step);
      button.addEventListener("click", () => options.onGoToCard?.(card));
      th.appendChild(button);
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    students.forEach((student) => {
      const tr = document.createElement("tr");
      const name = document.createElement("th");
      name.className = "progress-name-col";
      name.scope = "row";
      const nameText = document.createElement("span");
      nameText.textContent = student.display_name;
      name.appendChild(nameText);
      if (!student.started) {
        const badge = document.createElement("span");
        badge.className = "progress-not-started";
        badge.textContent = "미접속";
        name.appendChild(badge);
      }
      tr.appendChild(name);

      (student.cells || []).forEach((cell, index) => {
        const card = cards[index] || { step: 0, card: 0, title: "" };
        const td = document.createElement("td");
        td.className = "progress-cell";
        const clickable = cell.prompts > 0;
        const chip = document.createElement(clickable ? "button" : "span");
        chip.className = `progress-chip state-${cell.state}`;
        if (cell.current) chip.classList.add("is-current");
        if (hasResubmitted(cell)) {
          chip.classList.add("has-resubmit");
          chip.textContent = "재";
        }
        const title = cellTitle(student, card, cell)
          + (clickable ? ", 누르면 쓴 내용이 보입니다" : "");
        chip.title = title;
        chip.setAttribute("aria-label", title);
        if (clickable) {
          chip.type = "button";
          chip.classList.add("is-clickable");
          chip.addEventListener("click", () => openCellDetail(options, student, card));
        }
        td.appendChild(chip);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    const tfoot = document.createElement("tfoot");
    const footRow = document.createElement("tr");
    const footLabel = document.createElement("th");
    footLabel.className = "progress-name-col";
    footLabel.textContent = "열람 / 제출";
    footRow.appendChild(footLabel);
    cards.forEach((card) => {
      const td = document.createElement("td");
      td.className = "progress-cell progress-summary-cell";
      td.textContent = `${card.seen_count}/${card.answered_count}`;
      td.title = `${card.step + 1}단계 ${card.title}: 열람 ${card.seen_count}명, 제출 ${card.answered_count}명`;
      footRow.appendChild(td);
    });
    tfoot.appendChild(footRow);
    if (hasResubmitCards) {
      const resubmitRow = document.createElement("tr");
      const resubmitLabel = document.createElement("th");
      resubmitLabel.className = "progress-name-col";
      resubmitLabel.textContent = "재제출";
      resubmitRow.appendChild(resubmitLabel);
      cards.forEach((card) => {
        const td = document.createElement("td");
        td.className = "progress-cell progress-summary-cell";
        if ((card.resubmit_ids || []).length) {
          td.textContent = String(card.resubmit_count || 0);
          td.title = `${card.step + 1}단계 ${card.title}: 재제출 ${card.resubmit_count || 0}명 (제출 ${card.answered_count}명 중)`;
        }
        resubmitRow.appendChild(td);
      });
      tfoot.appendChild(resubmitRow);
    }
    table.appendChild(tfoot);

    body.appendChild(table);
  }

  function openProgressDashboard(options) {
    document.querySelector(".progress-overlay")?.remove();
    const overlay = buildOverlay();
    const body = overlay.querySelector(".progress-body");
    const sub = overlay.querySelector(".progress-sub");
    const foot = overlay.querySelector(".progress-foot");
    let timer = null;
    let stopped = false;

    function close() {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      overlay.remove();
      document.querySelector(".progress-detail-overlay")?.remove();
      document.removeEventListener("keydown", onKeydown);
      document.removeEventListener("visibilitychange", onVisibility);
    }

    function onVisibility() {
      if (stopped || document.hidden) return;
      if (timer) window.clearTimeout(timer);
      refresh();
    }

    function onKeydown(event) {
      if (event.key !== "Escape") return;
      if (document.querySelector(".progress-detail-overlay")) return;
      close();
    }

    overlay.querySelector(".progress-close").addEventListener("click", close);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close();
    });
    document.addEventListener("keydown", onKeydown);
    document.addEventListener("visibilitychange", onVisibility);

    async function refresh() {
      if (stopped) return;
      if (document.hidden) {
        timer = window.setTimeout(refresh, REFRESH_MS);
        return;
      }
      const query = new URLSearchParams({
        lesson_id: options.lessonId,
        class_id: options.classId || "",
        track: options.track || "",
        scenario: options.scenario || "",
      });
      try {
        const data = await window.StatApi.request(`/api/lessons/teacher/card-progress?${query.toString()}`);
        if (stopped) return;
        sub.textContent = `${options.classId ? `${options.classId} 학급의 ` : ""}${data.title || options.lessonId}`;
        renderTable(body, data, options);
        const answered = (data.students || []).filter((student) =>
          (student.cells || []).some((cell) => cell.state === "answered"),
        ).length;
        const started = (data.students || []).filter((student) => student.started).length;
        const hasResubmitCards = (data.cards || []).some((card) => (card.resubmit_ids || []).length);
        overlay.querySelector(".progress-legend-resubmit").hidden = !hasResubmitCards;
        const resubmitted = (data.students || []).filter((student) =>
          (student.cells || []).some((cell) => cell.resubmitted > 0),
        ).length;
        const resubmitText = hasResubmitCards ? `, 재제출한 학생 ${resubmitted}명` : "";
        foot.textContent = `접속 ${started}명, 한 번이라도 제출한 학생 ${answered}명${resubmitText}. ${Math.round(REFRESH_MS / 1000)}초마다 새로고침합니다.`;
      } catch (error) {
        if (stopped) return;
        body.textContent = "";
        const note = document.createElement("p");
        note.className = "lesson-note";
        note.textContent = error.message || "진행 현황을 불러오지 못했습니다.";
        body.appendChild(note);
      }
      if (!stopped) timer = window.setTimeout(refresh, REFRESH_MS);
    }

    overlay.querySelector(".progress-refresh").addEventListener("click", () => {
      if (timer) window.clearTimeout(timer);
      refresh();
    });

    body.textContent = "불러오는 중…";
    refresh();
    return close;
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.openProgressDashboard = openProgressDashboard;
  window.LessonKit.renderPredictPairSummary = renderPredictPairSummary;
  window.LessonKit.PROMPT_TYPE_LABELS = PROMPT_TYPE_LABELS;
})();
