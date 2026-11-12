(function () {
  const STAT_LABELS = {
    mean: "평균",
    median: "중앙값",
    mode: "최빈값",
    range: "범위",
    min: "최솟값",
    max: "최댓값",
    variance: "분산",
    std: "표준편차",
    q1: "제1사분위수",
    q3: "제3사분위수",
    iqr: "사분위범위",
    frequency: "도수 (몇 명인가)",
    relative_frequency: "상대도수 (전체에서 차지하는 비율)",
    cumulative_frequency: "누적도수",
  };

  async function runFixedAnalysis(projectId, toolName, toolArgs, cacheRef) {
    if (cacheRef?.lessonId && cacheRef?.key) {
      try {
        const query = new URLSearchParams({
          track: cacheRef.track || "",
          scenario: cacheRef.scenario || "",
        });
        return await window.StatApi.request(
          `/api/lessons/${encodeURIComponent(cacheRef.lessonId)}/fixed-analysis?${query.toString()}`,
          { method: "POST", body: JSON.stringify({ key: cacheRef.key }) },
        );
      } catch (_error) {
      }
    }
    return window.StatApi.request(`/api/projects/${encodeURIComponent(projectId)}/run-analysis`, {
      method: "POST",
      body: JSON.stringify({ tool_name: toolName, tool_args: toolArgs || {} }),
    });
  }

  const DICT_STAT_KEYS = ["frequency", "relative_frequency", "cumulative_frequency"];

  function renderGroupedCategoricalTable(container, data, statKey) {
    const groups = data.groups;
    const categories = [];
    groups.forEach((group) => {
      Object.keys(group.statistics[data.columns[0]]?.[statKey] || {}).forEach((name) => {
        if (!categories.includes(name)) categories.push(name);
      });
    });
    const isRate = statKey === "relative_frequency";
    const rows = categories.map((name) => [
      name,
      ...groups.map((group) => {
        const value = group.statistics[data.columns[0]]?.[statKey]?.[name];
        if (value === undefined || value === null) return isRate ? "0%" : 0;
        return isRate ? `${(Number(value) * 100).toFixed(1)}%` : value;
      }),
    ]);
    const headers = [
      data.columns[0],
      ...groups.map((group) => `${group.group} (${group.row_count}명)`),
    ];
    container.appendChild(buildTable(headers, rows, STAT_LABELS[statKey] || statKey));
  }

  function renderGroupedStatsTable(container, data, opts = {}) {
    const statKeys = [];
    data.groups.forEach((group) => {
      Object.keys(group.statistics[data.columns[0]] || {}).forEach((key) => {
        if (!statKeys.includes(key)) statKeys.push(key);
      });
    });
    const dictKeys = statKeys.filter((key) => DICT_STAT_KEYS.includes(key));
    const scalarKeys = statKeys.filter((key) => !DICT_STAT_KEYS.includes(key));

    dictKeys.forEach((key) => renderGroupedCategoricalTable(container, data, key));
    if (!scalarKeys.length) return;

    const table = document.createElement("table");
    table.className = "lesson-stats-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    [data.group_by, opts.countLabel || "표본 수", ...scalarKeys.map((key) => STAT_LABELS[key] || key)].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    data.groups.forEach((group) => {
      const tr = document.createElement("tr");
      const stats = group.statistics[data.columns[0]] || {};
      [group.group, group.sample_size, ...scalarKeys.map((key) => formatValue(stats[key] ?? ""))].forEach(
        (value) => {
          const td = document.createElement("td");
          td.textContent = value;
          decorateNumericCell(td, value);
          tr.appendChild(td);
        },
      );
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  function decorateNumericCell(td, value) {
    const isNumeric = typeof value === "number"
      || (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value)));
    if (!isNumeric) return;
    td.classList.add("lesson-stat-value");
    td.title = "누르면 근거 입력란에 이 값이 들어갑니다.";
    td.addEventListener("click", () => {
      const inserted = window.LessonKit.insertEvidenceValue?.(String(value).trim());
      if (inserted) window.StatApi?.toast?.(`근거 입력란에 ${String(value).trim()}을(를) 넣었습니다.`);
    });
  }

  function columnHeading(name, units) {
    const unit = units?.[name];
    return unit ? `${name} (${unit})` : name;
  }

  function formatValue(value) {
    if (value === null || value === undefined) return "";
    if (Array.isArray(value)) return value.map(formatValue).join(", ");
    if (typeof value === "object") {
      return Object.entries(value)
        .map(([key, inner]) => `${key}: ${formatValue(inner)}`)
        .join(", ");
    }
    return String(value);
  }

  function buildTable(headers, rows, caption) {
    const table = document.createElement("table");
    table.className = "lesson-stats-table";
    if (caption) {
      const cap = document.createElement("caption");
      cap.textContent = caption;
      table.appendChild(cap);
    }
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    headers.forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((value) => {
        const td = document.createElement("td");
        td.textContent = formatValue(value);
        decorateNumericCell(td, value);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function renderStatisticsTable(container, statistics, opts) {
    const columns = Object.keys(statistics || {});
    const statKeys = [];
    columns.forEach((column) => {
      Object.keys(statistics[column] || {}).forEach((key) => {
        if (!statKeys.includes(key)) statKeys.push(key);
      });
    });
    const rows = columns.map((column) => [
      columnHeading(column, opts.units),
      ...statKeys.map((key) => statistics[column]?.[key] ?? ""),
    ]);
    container.appendChild(buildTable(["항목", ...statKeys.map((key) => STAT_LABELS[key] || key)], rows));
    if (opts.rowCount) {
      const note = document.createElement("p");
      note.className = "lesson-sheet-note";
      note.textContent = `자료 전체 ${opts.rowCount}행으로 계산했습니다(빈칸은 제외).`;
      container.appendChild(note);
    }
  }

  function renderCorrelationTable(container, data) {
    const rows = [];
    if (data.overall) {
      rows.push(["전체", data.overall.sample_size, data.overall.pearson_correlation, data.overall.interpretation_label || ""]);
      (data.groups || []).forEach((group) => {
        rows.push([group.group, group.sample_size, group.pearson_correlation ?? "-", group.interpretation_label || group.note || ""]);
      });
    } else {
      rows.push([`${data.x_column} · ${data.y_column}`, data.sample_size, data.pearson_correlation, data.interpretation_label || ""]);
    }
    const first = data.group_by ? data.group_by : "비교한 두 항목";
    container.appendChild(buildTable([first, "표본 수", "상관계수", "읽는 법"], rows));
  }

  function renderFrequencyTable(container, rows) {
    const total = rows.reduce((sum, row) => sum + (Number(row.frequency) || 0), 0);
    const tableRows = rows.map((row) => {
      const share = total ? `${((Number(row.frequency) / total) * 100).toFixed(1)}%` : "";
      return [row.value ?? row.range ?? "", row.frequency, share];
    });
    tableRows.push(["합계", total, total ? "100%" : ""]);
    container.appendChild(buildTable(["값", "도수", "비율"], tableRows));
  }

  function renderRecordRows(container, rows) {
    const headers = [];
    rows.forEach((row) => Object.keys(row || {}).forEach((key) => {
      if (!headers.includes(key)) headers.push(key);
    }));
    container.appendChild(buildTable(headers, rows.map((row) => headers.map((key) => row?.[key] ?? ""))));
  }

  function renderResultData(container, data, opts = {}) {
    if (!data || typeof data !== "object") return;
    if (data.groups && data.columns && !("pearson_correlation" in (data.groups[0] || {}))) {
      renderGroupedStatsTable(container, data, opts);
      return;
    }
    if (data.statistics && !data.groups) {
      renderStatisticsTable(container, data.statistics, opts);
      return;
    }
    if ("pearson_correlation" in data || data.overall?.pearson_correlation !== undefined) {
      renderCorrelationTable(container, data);
      return;
    }
    if (Array.isArray(data.rows) && data.rows.length && "frequency" in data.rows[0]) {
      renderFrequencyTable(container, data.rows);
      return;
    }
    if (Array.isArray(data.rows)) {
      renderRecordRows(container, data.rows);
      return;
    }
    const entries = Object.entries(data).filter(([, value]) => value !== null && value !== undefined);
    if (entries.length) container.appendChild(buildTable(["항목", "값"], entries));
  }

  function renderResultCard(container, result, opts = {}) {
    container.innerHTML = "";
    const chartUrls = (result.chart_urls || []).filter((url) => url.endsWith(".png"));
    chartUrls.forEach((url) => {
      const img = document.createElement("img");
      img.className = "lesson-chart";
      img.src = window.LessonKit.resolveChartUrl(url);
      img.alt = opts.title || result.result?.data?.alt_text || "분석 결과 그래프";
      container.appendChild(img);
    });

    const warnings = result.result?.metadata?.validation_warnings || [];
    warnings.forEach((warning) => {
      const p = document.createElement("p");
      p.className = "lesson-warning";
      p.textContent = warning;
      container.appendChild(p);
    });

    if (!chartUrls.length) {
      renderResultData(container, result.result?.data, opts);
    }
  }

  async function renderAnalysisStep(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);
    const resultContainer = document.createElement("div");
    resultContainer.className = "lesson-result";
    resultContainer.textContent = "에이전트가 분석하는 중…";
    body.appendChild(resultContainer);
    const result = await runFixedAnalysis(ctx.projectId, step.tool_name, step.tool_args, {
      lessonId: ctx.lessonId,
      key: step.id,
      track: ctx.track,
      scenario: ctx.scenario,
    });
    renderResultCard(resultContainer, result, { countLabel: step.count_label });
    if (step.reading?.length) {
      const list = document.createElement("ul");
      list.className = "lesson-reading";
      step.reading.forEach((line) => {
        const li = document.createElement("li");
        li.textContent = line;
        list.appendChild(li);
      });
      body.appendChild(list);
    }
  }

  function renderReveals(container, card, ctx, onRevealed, opts = {}) {
    const doneKeys = new Set();
    const buttonByKey = {};
    const isTeacherViewer = ctx.role === "teacher" || ctx.role === "admin";
    const answerGate = Boolean(opts.answerGate) && !isTeacherViewer;
    let answered = !answerGate || Boolean(opts.answered);
    const deferredKeys = new Set();
    const selfReveal = Boolean(opts.selfReveal);
    const wrap = document.createElement("div");
    wrap.className = "lesson-analysis-options";
    container.appendChild(wrap);

    function isGated(reveal) {
      return answerGate && !reveal?.open_before_answer;
    }

    const lockHint = document.createElement("p");
    lockHint.className = "lesson-reveal-lock-hint";
    lockHint.textContent = opts.lockHintText || "위의 답을 먼저 보내면 열 수 있습니다.";
    lockHint.hidden = true;
    container.appendChild(lockHint);

    let following = false;
    const followHint = document.createElement("p");
    followHint.className = "lesson-reveal-lock-hint";
    followHint.textContent = "선생님이 열면 여기에 나타납니다.";
    followHint.hidden = true;
    container.appendChild(followHint);

    const waitHint = document.createElement("p");
    waitHint.className = "lesson-reveal-lock-hint lesson-reveal-wait-hint";
    waitHint.textContent = "선생님이 열었습니다. 위의 답을 보내면 여기에 나타납니다.";
    waitHint.hidden = true;
    container.appendChild(waitHint);

    if (selfReveal && isTeacherViewer) {
      const selfNote = document.createElement("p");
      selfNote.className = "lesson-note lesson-self-reveal-note";
      selfNote.textContent = "이 카드의 결과는 학생이 예측을 보낸 뒤 각자 엽니다. 여기서 열어도 학생 화면에는 열리지 않습니다.";
      container.appendChild(selfNote);
    }

    function findReveal(key) {
      return (card.reveals || []).find((item) => item.key === key);
    }

    function pendingButtons() {
      return Object.entries(buttonByKey).filter(
        ([, element]) => element.isConnected && element.tagName === "BUTTON",
      );
    }

    function updateHints() {
      const pending = pendingButtons();
      const hideForFollow = following && !selfReveal;
      pending.forEach(([key, button]) => {
        button.hidden = hideForFollow;
        button.disabled = !answered && isGated(findReveal(key));
      });
      const waiting = !answered && deferredKeys.size > 0;
      waitHint.hidden = !waiting;
      followHint.hidden = waiting || !hideForFollow || !pending.length;
      lockHint.hidden = waiting
        || hideForFollow
        || answered
        || !pending.some(([key]) => isGated(findReveal(key)));
    }

    async function runReveal(reveal) {
      if (doneKeys.has(reveal.key)) return;
      doneKeys.add(reveal.key);
      deferredKeys.delete(reveal.key);
      buttonByKey[reveal.key]?.remove();
      updateHints();

      const resultContainer = document.createElement("div");
      resultContainer.className = "lesson-result";
      container.appendChild(resultContainer);

      if (reveal.text?.length || reveal.text_rows?.length || reveal.figure) {
        resultContainer.innerHTML = "";
        (reveal.text || []).forEach((line) => {
          const p = document.createElement("p");
          window.LessonKit.fillInline(p, line);
          resultContainer.appendChild(p);
        });
        if (reveal.text_rows?.length) {
          const table = document.createElement("table");
          table.className = "lesson-stats-table lesson-reveal-table";
          const tbody = document.createElement("tbody");
          reveal.text_rows.forEach((row) => {
            const tr = document.createElement("tr");
            (row || []).forEach((cell) => {
              const td = document.createElement("td");
              td.textContent = cell;
              tr.appendChild(td);
            });
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          resultContainer.appendChild(table);
        }
        if (reveal.figure) {
          window.LessonKit.appendFigure(resultContainer, reveal.figure, reveal.figure_alt || reveal.label);
        }
      } else if (reveal.column_meaning) {
        resultContainer.textContent = "에이전트가 답하는 중…";
        const meanings = await window.StatApi.request(
          `/api/projects/${encodeURIComponent(ctx.projectId)}/column-meaning-suggestions`,
        );
        resultContainer.innerHTML = "";
        window.LessonKit.renderColumnMeanings(resultContainer, meanings);
      } else {
        resultContainer.textContent = "에이전트가 정리하는 중…";
        const result = await runFixedAnalysis(ctx.projectId, reveal.tool_name, reveal.tool_args, {
          lessonId: ctx.lessonId,
          key: reveal.key,
          track: ctx.track,
          scenario: ctx.scenario,
        });
        renderResultCard(resultContainer, result, { countLabel: reveal.count_label });
      }

      if (reveal.note) {
        const note = document.createElement("p");
        note.className = "lesson-reading-note";
        note.textContent = reveal.note;
        container.appendChild(note);
      }
      onRevealed?.(reveal.key);
    }

    (card.reveals || []).forEach((reveal) => {
      if (reveal.teacher_only && !isTeacherViewer) {
        const wait = document.createElement("p");
        wait.className = "lesson-reveal-lock-hint";
        wait.textContent = reveal.student_hint || "선생님이 열면 여기에 나타납니다.";
        buttonByKey[reveal.key] = wait;
        wrap.appendChild(wait);
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lesson-reveal";
      button.textContent = reveal.label;
      button.addEventListener("click", async () => {
        if (!answered && isGated(reveal)) return;
        if (selfReveal && !isTeacherViewer) opts.onSelfOpen?.(reveal.key);
        await runReveal(reveal);
        if (isTeacherViewer && ctx.classId && !selfReveal) {
          window.StatApi
            .request(`/api/lessons/sessions/${encodeURIComponent(ctx.classId)}/reveal`, {
              method: "PUT",
              body: JSON.stringify({ key: reveal.key, value: true }),
            })
            .catch((error) => window.LessonKit.showError(error.message || "표시 상태를 알리지 못했습니다."));
        }
      });
      buttonByKey[reveal.key] = button;
      wrap.appendChild(button);
    });
    updateHints();

    return {
      trigger(key) {
        if (selfReveal) return;
        const reveal = findReveal(key);
        if (!reveal || doneKeys.has(key)) return;
        if (!answered && isGated(reveal)) {
          if (deferredKeys.has(key)) return;
          deferredKeys.add(key);
          const placeholder = buttonByKey[key];
          if (placeholder && placeholder.tagName !== "BUTTON") {
            placeholder.textContent = "선생님이 열었습니다. 위의 답을 보내면 여기에 나타납니다.";
          }
          updateHints();
          return;
        }
        runReveal(reveal);
      },
      open(key) {
        const reveal = findReveal(key);
        if (reveal) runReveal(reveal);
      },
      setEnabled(value) {
        answered = !answerGate || Boolean(value);
        updateHints();
        if (!answered) return;
        [...deferredKeys].forEach((key) => {
          const reveal = findReveal(key);
          if (reveal) runReveal(reveal);
        });
      },
      setFollowing(value) {
        if (isTeacherViewer) return;
        following = Boolean(value);
        updateHints();
      },
    };
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.runFixedAnalysis = runFixedAnalysis;
  window.LessonKit.renderResultCard = renderResultCard;
  window.LessonKit.renderResultData = renderResultData;
  window.LessonKit.renderAnalysisStep = renderAnalysisStep;
  window.LessonKit.renderReveals = renderReveals;
})();
