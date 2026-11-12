(function () {
  const CHANGED_EVENT = "lesson-inquiry-changed";

  async function fetchInquiry(projectId) {
    return window.StatApi.request(`/api/lessons/inquiry/${encodeURIComponent(projectId)}`);
  }

  function notifyInquiryChanged() {
    window.dispatchEvent(new CustomEvent(CHANGED_EVENT));
  }

  function onInquiryChanged(handler) {
    window.addEventListener(CHANGED_EVENT, handler);
  }

  const TOOL_KINDS = {
    plot_bar: "막대그래프",
    plot_histogram: "히스토그램",
    plot_boxplot: "상자그림",
    plot_scatter: "산점도",
    plot_grouped_scatter: "집단별 산점도",
    plot_line: "꺾은선그래프",
    plot_frequency_polygon: "도수분포다각형",
    plot_pie: "원그래프",
    plot_choropleth: "지도",
    plot_stem_leaf: "줄기와 잎 그림",
    compute_descriptive_stats: "요약 통계",
    compute_correlation: "상관계수",
    compute_grouped_correlation: "집단별 상관계수",
    create_frequency_table: "도수분포표",
    create_crosstab: "교차표",
  };

  function describeAnalysis(analysis) {
    const args = analysis.tool_args || {};
    const kind = TOOL_KINDS[analysis.tool_name] || "분석 결과";
    if (args.title) return `${args.title} (${kind})`;
    const columns = args.columns || [args.column, args.value_col, args.y_column].filter(Boolean);
    const target = columns.join(", ");
    const groupBy = args.group_by || args.category_col || args.region_col;
    const x = args.x_column || args.x_col;
    const y = args.y_column || args.y_col;
    if (x && y) {
      const pair = `${x}와 ${y}의 ${kind}`;
      return args.group_by ? `${args.group_by}별 ${pair}` : pair;
    }
    if (groupBy && target) return `${groupBy}별 ${target} ${kind}`;
    if (target) return `${target} ${kind}`;
    return kind;
  }

  function unitMap(dataset) {
    const units = {};
    (dataset?.columns || []).forEach((column) => {
      if (column.unit) units[column.name] = column.unit;
    });
    return units;
  }

  function addRow(list, label, value, missingText) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (value) {
      dd.textContent = value;
    } else {
      dd.className = "inquiry-missing";
      dd.textContent = missingText;
    }
    list.append(dt, dd);
  }

  function datasetLine(dataset) {
    if (!dataset) return "";
    const parts = [dataset.name];
    if (typeof dataset.row_count === "number") parts.push(`${dataset.row_count}행`);
    return parts.join(" · ");
  }

  function sourceLine(dataset) {
    if (!dataset?.source_recorded) return "";
    return [dataset.source, dataset.time_range].filter(Boolean).join(" · ");
  }

  const SOURCE_MISSING = "직접 입력한 자료라 출처·기간이 기록되지 않았습니다 — 기록지에 통계표 이름·링크와 기간을 적고 발표에서 밝히세요.";

  async function renderInquirySummary(host, ctx) {
    host.className = "inquiry-summary";

    async function draw() {
      let summary;
      try {
        summary = await fetchInquiry(ctx.projectId);
      } catch (error) {
        host.textContent = "내 탐구 정보를 불러오지 못했습니다.";
        return;
      }
      host.innerHTML = "";
      const heading = document.createElement("div");
      heading.className = "inquiry-summary-heading";
      heading.textContent = "내 탐구";
      host.appendChild(heading);

      const list = document.createElement("dl");
      addRow(
        list,
        "탐구 질문",
        summary.question_confirmed ? summary.question : "",
        "아직 정하지 않았습니다 — 5차시 '진로 분야에서 주제를 고른다'에서 고르세요.",
      );
      addRow(
        list,
        "분석에 쓰는 자료",
        datasetLine(summary.dataset),
        "연결된 자료가 없습니다 — 5차시에서 표를 입력하거나 모둠원 자료를 가져와 연결하세요.",
      );
      if (summary.dataset) {
        addRow(list, "출처·기간", sourceLine(summary.dataset), SOURCE_MISSING);
      }
      addRow(
        list,
        "저장한 결과",
        summary.analysis_count
          ? `${summary.analysis_count}개 (해석을 적은 결과 ${summary.interpreted_count}개)`
          : "",
        "아직 없습니다.",
      );
      host.appendChild(list);
      ctx.inquiry = summary;
    }

    onInquiryChanged(draw);
    await draw();
  }

  async function renderInquiryCheck(body, step, ctx) {
    window.LessonKit.renderExplain(body, step);
    const panel = document.createElement("div");
    panel.className = "inquiry-check";
    body.appendChild(panel);

    const refreshButton = document.createElement("button");
    refreshButton.type = "button";
    refreshButton.textContent = "다시 확인하기";
    body.appendChild(refreshButton);

    async function check() {
      panel.textContent = "확인하는 중…";
      const summary = await fetchInquiry(ctx.projectId);
      let optionCount = null;
      if (summary.dataset) {
        try {
          const options = await window.StatApi.request(`/api/projects/${ctx.projectId}/analysis-options`);
          optionCount = options.length;
        } catch (_error) {
          optionCount = 0;
        }
      }

      panel.innerHTML = "";
      const items = [
        {
          ok: summary.question_confirmed,
          label: "탐구 질문",
          detail: summary.question_confirmed ? summary.question : "아직 고르지 않았습니다. 2단계로 돌아가 질문을 고르세요.",
        },
        {
          ok: Boolean(summary.dataset),
          label: "분석에 쓰일 자료",
          detail: summary.dataset
            ? datasetLine(summary.dataset)
            : "프로젝트에 연결된 자료가 없습니다. 표 입력 또는 모둠원 자료 단계에서 연결을 다시 시도하세요.",
        },
        {
          ok: Boolean(summary.dataset?.source_recorded),
          label: "출처·기간",
          detail: summary.dataset ? sourceLine(summary.dataset) || SOURCE_MISSING : "자료를 먼저 연결하세요.",
        },
        {
          ok: Boolean(optionCount),
          label: "6차시 추천 분석",
          detail:
            optionCount === null
              ? "자료를 연결하면 확인할 수 있습니다."
              : optionCount
                ? `${optionCount}개 준비됨 — 그래도 질문에 맞는 분석인지는 직접 판단해야 합니다.`
                : "이 자료로는 추천 분석이 나오지 않습니다. 첫 줄이 열 이름인지, 숫자 칸에 숫자만 있는지 선생님과 확인하세요.",
        },
      ];
      const list = document.createElement("ul");
      list.className = "inquiry-check-list";
      items.forEach((item) => {
        const li = document.createElement("li");
        li.className = item.ok ? "ok" : "todo";
        const mark = document.createElement("strong");
        mark.textContent = `${item.ok ? "확인" : "보완 필요"} · ${item.label}`;
        const detail = document.createElement("span");
        detail.textContent = item.detail;
        li.append(mark, detail);
        list.appendChild(li);
      });
      panel.appendChild(list);
    }

    refreshButton.addEventListener("click", () => {
      check().catch((error) => window.LessonKit.showError(error.message || "확인하지 못했습니다."));
    });
    onInquiryChanged(() => {
      check().catch(() => {});
    });
    await check();
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.fetchInquiry = fetchInquiry;
  window.LessonKit.notifyInquiryChanged = notifyInquiryChanged;
  window.LessonKit.onInquiryChanged = onInquiryChanged;
  window.LessonKit.describeAnalysis = describeAnalysis;
  window.LessonKit.inquiryUnitMap = unitMap;
  window.LessonKit.renderInquirySummary = renderInquirySummary;
  window.LessonKit.renderInquiryCheck = renderInquiryCheck;
})();
