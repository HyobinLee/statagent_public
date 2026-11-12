(function () {
  const steps = ["주제", "자료", "분석", "보고서", "피드백"];
  const STEP = { TOPIC: 0, DATA: 1, ANALYSIS: 2, REPORT: 3, FEEDBACK: 4 };
  const view = document.getElementById("student-view");
  let reportGrids = [];
  const progress = document.getElementById("progress");
  const stepControls = document.getElementById("step-controls");
  const summary = document.getElementById("state-summary");
  const aiCoachBox = document.getElementById("ai-coach-box");
  const feedbackBox = document.getElementById("feedback-box");
  let mergeWizardState = {
    step: 1,
    selectedDatasetIds: [],
    keyMappings: {},
    previewResult: null,
    harmonizeResult: null,
    timeMappings: {},
    timePoints: null,
    selectedTimePoints: [],
  };
  let state = {
    step: 0,
    project: null,
    projectManagerOpen: false,
    schoolLevel: null,
    startMode: null,
    topic: null,
    questionAdviceMode: "direct_survey",
    dataset: null,
    datasetMode: null,
    sharedArtifacts: null,
    uploadPlan: null,
    kosisPlan: null,
    statApiPlan: null,
    kosisQuestionDraft: "",
    kosisSearchDraft: "",
    statApiQuestionDraft: "",
    customAnalysisTool: "plot_line",
    sheet: null,
    sheetEdits: {},
    sheetFilters: {},
    sheetView: { columnWidth: 150, columnWidths: {}, fontSize: 14 },
    analysisRows: { mode: "all", selected: [] },
    customAnalysisFields: {},
    derivedSuggestions: null,
    options: [],
    analysis: null,
    analysisHistory: [],
    interpretationDrafts: {},
    interpretationFeedback: {},
    analysisRunOpen: false,
    synthesisPanel: { selectedDatasetIds: [], keyMappings: {}, toolName: "compute_cross_correlation" },
    synthesisDatasetSchemas: {},
    synthesisHistory: [],
    synthesisResult: null,
    synthesisObservations: null,
    hints: null,
    report: null,
    reportLayout: null,
    coach: null,
    questionDraft: "",
    questionAdvice: null,
    decidedTopicDraft: "",
    ...StatState.getStudentState(),
  };

  const TUTORIAL_STORE_KEY = "stat-agent-tutorial";
  const TUTORIAL_CSV_HREF = "./tutorial-data/midterm_scores_two_classes.csv?v=20260731-02";
  const TUTORIAL_CSV_NAME = "midterm_scores_two_classes.csv";
  const TUTORIAL_EXAMPLE_QUESTION = "두 학급의 중간고사 성적 분포는 어떻게 다를까?";
  const TUTORIAL_GROUP_COLUMN = "class_name";
  const TUTORIAL_VALUE_COLUMN = "score";

  function defaultTutorialState() {
    return {
      active: false,
      welcomeSeen: false,
      collapsed: false,
      completedShown: false,
      feedbackReached: false,
      reportSaved: false,
      interpretationSaved: false,
      groupBoxplotDone: false,
      groupStatsDone: false,
    };
  }

  function loadTutorialState() {
    try {
      const raw = JSON.parse(localStorage.getItem(TUTORIAL_STORE_KEY) || "{}");
      return { ...defaultTutorialState(), ...raw };
    } catch (_error) {
      return defaultTutorialState();
    }
  }

  let tutorial = loadTutorialState();

  if (new URLSearchParams(window.location.search).get("tutorial") === "midterm") {
    if (!tutorial.active) tutorial = { ...defaultTutorialState(), active: true };
    persistTutorialState();
    window.history.replaceState(null, "", window.location.pathname);
  }

  function persistTutorialState() {
    localStorage.setItem(TUTORIAL_STORE_KEY, JSON.stringify(tutorial));
  }

  function isTutorialActive() {
    return Boolean(tutorial.active);
  }

  function resetTutorialProgress() {
    const keep = { active: tutorial.active, welcomeSeen: tutorial.welcomeSeen, collapsed: tutorial.collapsed };
    tutorial = { ...defaultTutorialState(), ...keep };
    persistTutorialState();
  }

  function startTutorial() {
    if (state.project || state.topic || state.dataset) {
      const ok = window.confirm(
        "튜토리얼은 새 연습 프로젝트에서 시작합니다.\n지금 화면의 탐구는 '프로젝트 관리'에서 다시 열 수 있습니다. 시작할까요?",
      );
      if (!ok) return;
    }
    tutorial = { ...defaultTutorialState(), active: true };
    persistTutorialState();
    updateTutorialButton();
    restart();
  }

  function exitTutorial() {
    tutorial.active = false;
    persistTutorialState();
    removeTutorialFocus();
    document.getElementById("student-tutorial-overlay")?.remove();
    document.getElementById("tutorial-dialog")?.remove();
    updateTutorialButton();
  }

  function updateTutorialButton() {
    const button = document.getElementById("tutorial-btn");
    if (!button) return;
    button.hidden = !StatAuth.isSignedIn?.();
    button.textContent = tutorial.active ? "튜토리얼 종료" : "튜토리얼";
    button.classList.toggle("is-active", tutorial.active);
  }

  function removeTutorialFocus() {
    document.querySelectorAll(".tutorial-focus").forEach((element) => {
      element.classList.remove("tutorial-focus");
    });
  }

  function firstVisibleElement(selectors = []) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (!element) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return element;
    }
    return null;
  }

  function updateTutorialAnalysisProgress(toolName, toolArgs) {
    if (!isTutorialActive()) return;
    const groupBy = String(toolArgs?.group_by || "").trim();
    if (groupBy !== TUTORIAL_GROUP_COLUMN) return;
    let changed = false;
    if (toolName === "plot_boxplot" && !tutorial.groupBoxplotDone) {
      tutorial.groupBoxplotDone = true;
      changed = true;
    }
    if (toolName === "compute_descriptive_stats" && !tutorial.groupStatsDone) {
      tutorial.groupStatsDone = true;
      changed = true;
    }
    if (changed) persistTutorialState();
  }

  function tutorialMilestones() {
    if (state.step === STEP.FEEDBACK && !tutorial.feedbackReached) {
      tutorial.feedbackReached = true;
      persistTutorialState();
    }
    return [
      { label: "주제 확정", done: Boolean(state.project?.project_id) },
      { label: "자료 준비", done: Boolean(state.project?.dataset_id || state.dataset?.dataset_id) },
      { label: "이중 상자그림", done: tutorial.groupBoxplotDone },
      { label: "요약 통계량 비교", done: tutorial.groupStatsDone },
      { label: "해석 저장", done: tutorial.interpretationSaved },
      { label: "보고서·피드백", done: tutorial.reportSaved && tutorial.feedbackReached },
    ];
  }

  function tutorialCompleted() {
    return tutorialMilestones().every((milestone) => milestone.done);
  }

  function tutorialCurrentTask() {
    if (state.projectManagerOpen) {
      return {
        id: "project-manager",
        title: "탐구 화면으로 돌아가기",
        message: "프로젝트 관리 화면입니다. 튜토리얼을 계속하려면 탐구 화면으로 돌아가세요.",
        targets: ["#back-to-inquiry"],
      };
    }
    if (!schoolLevel()) {
      return {
        id: "school-level",
        title: "학교급 고르기",
        message: "먼저 학교급을 고릅니다. 이 연습은 상자그림을 사용하므로 고등학교를 고르세요.",
        items: ["학교급에 따라 예시와 AI 조언 수준이 달라집니다."],
        targets: ["[data-school-level='high']", "[data-school-level]"],
      };
    }
    if (!state.project?.project_id) {
      if (!state.startMode) {
        return {
          id: "start-mode",
          title: "시작 방식 고르기",
          message: "이 연습에서는 '탐구 질문 입력'으로 시작합니다. 왼쪽 카드의 선택 버튼을 누르세요.",
          targets: ["#choose-question-input"],
        };
      }
      if (state.startMode === "example") {
        return {
          id: "switch-question",
          title: "탐구 질문 입력으로 전환",
          message: "튜토리얼은 질문을 직접 적는 흐름으로 진행합니다. '탐구 질문 입력' 버튼을 누르세요.",
          targets: ["#switch-to-question-input", "#choose-question-input"],
        };
      }
      if (!state.questionAdvice) {
        const inputFilled = Boolean(
          (document.getElementById("question-advisor-input")?.value || state.questionDraft || "").trim(),
        );
        return {
          id: "question-advice",
          title: "탐구 질문 적고 조언받기",
          message: inputFilled
            ? "좋습니다. 이제 '직접 자료 조사 탐구 조언받기' 버튼을 눌러 AI 조언을 받아보세요."
            : "입력 칸에 궁금한 점을 적습니다. 아래 예시를 그대로 적어도 됩니다.",
          items: [`입력 예시: ${TUTORIAL_EXAMPLE_QUESTION}`],
          targets: inputFilled
            ? ["#question-advisor-form .advice-mode-actions .primary", "#question-advisor-input"]
            : ["#question-advisor-input"],
          watchInputs: ["#question-advisor-input"],
        };
      }
      const decidedFilled = Boolean(
        (document.getElementById("decided-topic-input")?.value || state.decidedTopicDraft || "").trim(),
      );
      return {
        id: "decide-topic",
        title: "탐구 주제 확정하기",
        message: decidedFilled
          ? "'이 주제로 자료 단계 시작' 버튼을 눌러 프로젝트를 만듭니다."
          : "AI 조언을 읽고, 후보 카드의 '이 질문 선택 →'을 누르거나 결정한 주제를 한 문장으로 적으세요.",
        items: [`예시: ${TUTORIAL_EXAMPLE_QUESTION}`],
        targets: decidedFilled
          ? ["#decision-topic-form button[type='submit']", "#decided-topic-input"]
          : ["#decided-topic-input", ".select-candidate-question"],
        watchInputs: ["#decided-topic-input"],
      };
    }
    const datasetReady = Boolean(state.project?.dataset_id || state.dataset?.dataset_id);
    if (!datasetReady) {
      if (state.uploadPlan?.dataset) {
        return {
          id: "use-upload",
          title: "업로드한 자료로 이어가기",
          message: "AI 처리 제안을 확인했으면 '이 자료로 이어가기' 버튼을 눌러 분석 단계로 갑니다.",
          targets: ["#use-uploaded-dataset"],
        };
      }
      const secondaryDetails = document.querySelector(".secondary-data-methods");
      const detailsOpen = Boolean(secondaryDetails?.open);
      const fileChosen = Boolean(document.getElementById("csv-file")?.files?.length);
      if (secondaryDetails && !detailsOpen) {
        return {
          id: "open-upload",
          title: "CSV 업로드 열기",
          message: "'다른 방법 (CSV 업로드, 자료 결합)'을 눌러 CSV 업로드 칸을 엽니다.",
          items: ["연습용 파일을 아직 안 받았다면 아래 버튼으로 내려받으세요."],
          targets: [".secondary-data-methods summary"],
          csvDownload: true,
          navigateStep: STEP.DATA,
        };
      }
      return {
        id: "upload-csv",
        title: "연습용 CSV 업로드",
        message: fileChosen
          ? "파일을 골랐으면 'AI 처리 제안 받기' 버튼을 누릅니다."
          : `CSV 업로드 칸의 파일 선택에서 ${TUTORIAL_CSV_NAME} 파일을 고르세요.`,
        items: fileChosen ? [] : ["파일이 없다면 아래 버튼으로 먼저 내려받으세요."],
        targets: fileChosen ? ["#csv-upload-form button[type='submit']"] : ["#csv-file"],
        watchInputs: ["#csv-file"],
        csvDownload: !fileChosen,
        navigateStep: STEP.DATA,
      };
    }
    if (!tutorial.groupBoxplotDone || !tutorial.groupStatsDone) {
      if (state.step !== STEP.ANALYSIS) {
        return {
          id: "goto-analysis",
          title: "분석 화면으로 이동",
          message: "자료 표와 분석 카드가 있는 분석 화면으로 이동해 두 학급 비교를 이어가세요.",
          targets: ["#dataset-to-analysis", "#analysis-run-panel summary"],
          navigateStep: STEP.ANALYSIS,
        };
      }
      if (!tutorial.groupBoxplotDone) {
        return {
          id: "group-boxplot",
          title: "두 학급을 한 그림에 놓기 (이중 상자그림)",
          message:
            `'직접 선택'에서 분석 방법을 상자그림으로 고르고, 수치형 항목은 ${TUTORIAL_VALUE_COLUMN}, ` +
            `'범주 추가'는 ${TUTORIAL_GROUP_COLUMN}으로 두고 실행하세요.`,
          items: [
            "추천 분석 카드 맨 위의 '…분포 비교(상자그림)' 카드에서 '실행'을 눌러도 같은 결과가 나옵니다.",
            "학급별로 필터를 걸 필요는 없습니다. 60행을 그대로 두어야 두 학급이 나란히 그려집니다.",
          ],
          targets: ["[data-option]", "#custom-tool-name", "#custom-analysis-form button[type='submit']"],
        };
      }
      return {
        id: "group-stats",
        title: "숫자로도 비교하기 (학급별 요약 통계량)",
        message:
          `'직접 선택'에서 분석 방법을 '요약 통계'로 고르고, 항목은 ${TUTORIAL_VALUE_COLUMN}, ` +
          `'집단 나누기'를 ${TUTORIAL_GROUP_COLUMN}으로 지정해 실행하세요.`,
        items: [
          "평균·중앙값은 어느 학급이 높은지, 표준편차는 어느 학급이 더 퍼져 있는지 확인합니다.",
          "상자그림에서 눈으로 본 차이를 숫자로 확인하는 단계입니다.",
        ],
        targets: ["#custom-tool-name", "[data-option]", "#custom-analysis-form button[type='submit']"],
      };
    }
    const latestForTutorial = latestAnalysisResult();
    if (!tutorial.interpretationSaved) {
      if (state.step !== STEP.ANALYSIS) {
        return {
          id: "goto-analysis-result",
          title: "분석 화면으로 이동",
          message: "두 학급 분석을 마쳤습니다. 분석 화면에서 결과를 읽고 해석을 써 보세요.",
          targets: ["#dataset-to-analysis"],
          navigateStep: STEP.ANALYSIS,
        };
      }
      if (!state.hints) {
        return {
          id: "load-hints",
          title: "관찰점·유도 질문 확인",
          message: "결과 카드의 '관찰점·유도 질문 불러오기' 버튼을 눌러 무엇을 볼지 확인하세요.",
          targets: ["#load-hints"],
        };
      }
      const interpretationFilled = Boolean(
        latestForTutorial && interpretationDraft(latestForTutorial).trim(),
      );
      const feedbackSeen = Boolean(
        latestForTutorial && (state.interpretationFeedback || {})[latestForTutorial.analysis_result_id],
      );
      if (!interpretationFilled) {
        return {
          id: "write-interpretation",
          title: "결과를 읽고 내 해석 쓰기",
          message: "결과 카드 아래 '이 결과에 대한 내 해석' 칸에 2~3문장 적어 보세요. 원인을 단정하지 않습니다.",
          items: [
            "예시: Class_A의 평균과 중앙값이 Class_B보다 높다. 다만 상자의 길이와 표준편차도 Class_A가 더 커서, Class_A는 점수가 넓게 퍼져 있고 Class_B는 좁은 구간에 모여 있다.",
            "대표값 차이와 퍼짐 차이를 각각 한 문장씩 적으면 좋습니다.",
          ],
          targets: ["[data-interpretation-input]"],
          watchInputs: ["[data-interpretation-input]"],
        };
      }
      if (!feedbackSeen) {
        return {
          id: "interpretation-feedback",
          title: "AI 피드백 받아 보기",
          message: "'AI 피드백 받기' 버튼을 누르면 잘한 점과 보완할 점을 알려 줍니다.",
          items: ["피드백을 읽고 해석을 고친 뒤 저장하면 됩니다."],
          targets: ["[data-interpretation-feedback]"],
        };
      }
      return {
        id: "save-interpretation",
        title: "고친 해석 저장하기",
        message: "피드백을 반영해 해석을 다듬었으면 '해석 저장' 버튼을 누르세요.",
        items: ["저장한 해석은 보고서에서 이 결과와 한 카드로 묶여 나옵니다."],
        targets: ["[data-interpretation-save]"],
        watchInputs: ["[data-interpretation-input]"],
      };
    }
    if (!tutorial.reportSaved) {
      if (state.step !== STEP.REPORT) {
        return {
          id: "goto-report",
          title: "보고서 만들기",
          message: "'보고서 만들기 →' 버튼을 눌러 보고서 화면으로 이동하세요.",
          targets: ["#go-report-step"],
          navigateStep: STEP.REPORT,
        };
      }
      return {
        id: "save-report",
        title: "결론 쓰고 보고서 저장하기",
        message: "'탐구 전체 결론' 칸에 두 학급 비교의 답을 정리한 뒤 '구성 저장' 버튼을 누르세요.",
        items: [
          "'저장한 해석 불러오기'를 누르면 앞에서 쓴 해석이 초안으로 들어옵니다.",
          "블록 순서(↑↓)나 결과 카드 너비(절반)도 조정해 볼 수 있습니다.",
          "저장 후 'PDF 내려받기'로 완성본을 확인할 수 있습니다.",
        ],
        targets: ["#report-layout-form button[type='submit']", "#report-add-text-note"],
      };
    }
    if (!tutorial.feedbackReached) {
      return {
        id: "goto-feedback",
        title: "피드백 확인으로 마무리",
        message: "'피드백 확인' 버튼을 눌러 마지막 단계로 이동하세요.",
        items: ["이동 전에 'PDF 내려받기'로 보고서를 확인해 보세요."],
        targets: ["#go-feedback-step"],
        navigateStep: STEP.FEEDBACK,
      };
    }
    return {
      id: "done",
      title: "튜토리얼 완료!",
      message: "탐구 한 사이클을 모두 끝냈습니다. 이제 '새 프로젝트'로 나만의 탐구를 시작해 보세요.",
      items: ["오른쪽 위 '튜토리얼 종료' 버튼으로 안내를 끌 수 있습니다."],
      targets: [],
    };
  }

  let tutorialRenderScheduled = false;
  function scheduleTutorialRender() {
    if (!isTutorialActive() || tutorialRenderScheduled) return;
    tutorialRenderScheduled = true;
    window.requestAnimationFrame(() => {
      tutorialRenderScheduled = false;
      renderTutorialOverlay();
    });
  }

  let tutorialLastTaskId = "";

  function tutorialDialogMarkup(kind) {
    if (kind === "welcome") {
      return `
        <div class="tutorial-dialog-card">
          <p class="eyebrow">연습 탐구 튜토리얼</p>
          <h2>두 학급의 중간고사 성적, 정말 다를까?</h2>
          <p>
            실제 탐구 화면을 그대로 쓰면서 주제 정하기부터 보고서 제출까지 한 바퀴 연습합니다.
            오른쪽 아래 <strong>안내 카드</strong>가 지금 해야 할 일을 알려주고,
            눌러야 할 버튼은 <strong>주황색 테두리</strong>로 표시됩니다.
          </p>
          <ol>
            <li>연습용 자료(CSV)를 내려받아 둡니다.</li>
            <li>안내 카드가 시키는 대로 화면 버튼을 누르며 진행합니다.</li>
            <li>한 작업을 마치면 안내가 자동으로 다음 할 일로 바뀝니다.</li>
          </ol>
          <p class="muted">
            두 학급을 비교할 때는 학급별로 따로 보는 대신, 두 학급을 나란히 놓은
            <strong>이중 상자그림</strong>과 <strong>학급별 요약 통계량</strong>을 사용합니다.
          </p>
          <div class="actions">
            <a class="button-like" href="${TUTORIAL_CSV_HREF}" download="${TUTORIAL_CSV_NAME}">연습용 CSV 내려받기</a>
          </div>
          <div class="actions">
            <button type="button" id="tutorial-dialog-cancel">나중에 하기</button>
            <button type="button" class="primary" id="tutorial-dialog-start">튜토리얼 시작</button>
          </div>
        </div>
      `;
    }
    return `
      <div class="tutorial-dialog-card">
        <p class="eyebrow">축하합니다 🎉</p>
        <h2>탐구 한 사이클을 모두 마쳤어요!</h2>
        <p>
          주제 정하기 → 자료 준비 → 두 학급 분포 비교(상자그림·요약 통계량) → 결론 → 보고서까지
          통계 탐구의 전체 흐름을 직접 해냈습니다.
        </p>
        <p class="muted">이제 '새 프로젝트'에서 내가 궁금한 주제로 진짜 탐구를 시작해 보세요.</p>
        <div class="actions">
          <button type="button" id="tutorial-dialog-continue">화면 더 둘러보기</button>
          <button type="button" class="primary" id="tutorial-dialog-finish">튜토리얼 종료</button>
        </div>
      </div>
    `;
  }

  function showTutorialDialog(kind) {
    let dialog = document.getElementById("tutorial-dialog");
    if (!dialog) {
      dialog = document.createElement("div");
      dialog.id = "tutorial-dialog";
      dialog.className = "tutorial-dialog-backdrop";
      document.body.appendChild(dialog);
    }
    dialog.innerHTML = tutorialDialogMarkup(kind);
    if (kind === "welcome") {
      document.getElementById("tutorial-dialog-start")?.addEventListener("click", () => {
        tutorial.welcomeSeen = true;
        persistTutorialState();
        dialog.remove();
        renderTutorialOverlay();
      });
      document.getElementById("tutorial-dialog-cancel")?.addEventListener("click", () => {
        dialog.remove();
        exitTutorial();
      });
    } else {
      document.getElementById("tutorial-dialog-finish")?.addEventListener("click", () => {
        dialog.remove();
        exitTutorial();
      });
      document.getElementById("tutorial-dialog-continue")?.addEventListener("click", () => {
        dialog.remove();
      });
    }
  }

  function renderTutorialOverlay() {
    updateTutorialButton();
    if (!isTutorialActive()) {
      removeTutorialFocus();
      document.getElementById("student-tutorial-overlay")?.remove();
      document.getElementById("tutorial-dialog")?.remove();
      return;
    }
    if (!tutorial.welcomeSeen) {
      showTutorialDialog("welcome");
      return;
    }
    const milestones = tutorialMilestones();
    const task = tutorialCurrentTask();
    if (task.id === "done" && !tutorial.completedShown) {
      tutorial.completedShown = true;
      persistTutorialState();
      showTutorialDialog("complete");
    }

    let overlay = document.getElementById("student-tutorial-overlay");
    if (!overlay) {
      overlay = document.createElement("aside");
      overlay.id = "student-tutorial-overlay";
      overlay.className = "student-tutorial-overlay";
      document.body.appendChild(overlay);
    }
    const doneCount = milestones.filter((milestone) => milestone.done).length;
    const items = Array.isArray(task.items) ? task.items.filter(Boolean) : [];
    overlay.classList.toggle("is-collapsed", Boolean(tutorial.collapsed));
    overlay.innerHTML = `
      <div class="tutorial-card-head">
        <p class="eyebrow">튜토리얼 · ${doneCount}/${milestones.length} 완료</p>
        <div class="tutorial-card-controls">
          <button type="button" id="tutorial-collapse" aria-label="${tutorial.collapsed ? "안내 펼치기" : "안내 접기"}">
            ${tutorial.collapsed ? "펼치기" : "접기"}
          </button>
          <button type="button" id="tutorial-exit" aria-label="튜토리얼 종료">종료</button>
        </div>
      </div>
      <div class="tutorial-card-body" ${tutorial.collapsed ? "hidden" : ""}>
        <ol class="tutorial-milestones">
          ${milestones
            .map(
              (milestone) => `
                <li class="${milestone.done ? "is-done" : ""}" title="${escapeHtml(milestone.label)}">
                  <span>${escapeHtml(milestone.label)}</span>
                </li>
              `,
            )
            .join("")}
        </ol>
        <h3>${escapeHtml(task.title)}</h3>
        <p>${escapeHtml(task.message)}</p>
        ${items.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
        ${
          task.csvDownload
            ? `<div class="actions"><a class="button-like" href="${TUTORIAL_CSV_HREF}" download="${TUTORIAL_CSV_NAME}">연습용 CSV 내려받기</a></div>`
            : ""
        }
        <div class="actions">
          <button type="button" class="primary" id="tutorial-show-target">할 일 위치 보기</button>
        </div>
      </div>
    `;

    document.getElementById("tutorial-collapse")?.addEventListener("click", () => {
      tutorial.collapsed = !tutorial.collapsed;
      persistTutorialState();
      renderTutorialOverlay();
    });
    document.getElementById("tutorial-exit")?.addEventListener("click", exitTutorial);
    document.getElementById("tutorial-show-target")?.addEventListener("click", () => {
      const target = firstVisibleElement(task.targets || []);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("tutorial-focus");
        return;
      }
      if (typeof task.navigateStep === "number" && isStepAvailable(task.navigateStep)) {
        navigateToStep(task.navigateStep);
        return;
      }
      StatApi.toast("지금 화면에서 안내 위치를 찾지 못했습니다. 화면을 위아래로 살펴보세요.");
    });

    (task.watchInputs || []).forEach((selector) => {
      const input = document.querySelector(selector);
      if (input && !input.dataset.tutorialWatched) {
        input.dataset.tutorialWatched = "true";
        input.addEventListener("input", scheduleTutorialRender);
        input.addEventListener("change", scheduleTutorialRender);
      }
    });
    const secondaryDetails = document.querySelector(".secondary-data-methods");
    if (secondaryDetails && !secondaryDetails.dataset.tutorialWatched) {
      secondaryDetails.dataset.tutorialWatched = "true";
      secondaryDetails.addEventListener("toggle", scheduleTutorialRender);
    }

    removeTutorialFocus();
    const target = firstVisibleElement(task.targets || []);
    target?.classList.add("tutorial-focus");
    if (task.id !== tutorialLastTaskId) {
      tutorialLastTaskId = task.id;
      overlay.classList.remove("tutorial-card-flash");
      void overlay.offsetWidth;
      overlay.classList.add("tutorial-card-flash");
      if (!tutorial.collapsed) target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function dtypeLabel(dtype) {
    const labels = {
      numeric: "수치형",
      categorical: "범주형",
    };
    return labels[dtype] || dtype || "-";
  }

  function metricLabel(key) {
    const labels = {
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
      frequency: "도수",
      relative_frequency: "상대도수",
      cumulative_frequency: "누적도수",
      pearson_correlation: "피어슨 상관계수",
      sample_size: "표본 수",
      interpretation_label: "관계 해석",
      x_column: "가로축 항목",
      y_column: "세로축 항목",
    };
    return labels[key] || key;
  }

  function toolLabel(toolName) {
    const labels = {
      compute_descriptive_stats: "요약 통계",
      compute_correlation: "상관계수",
      compute_grouped_correlation: "집단별 상관계수(층화분석)",
      plot_grouped_scatter: "집단별 산점도",
      plot_map: "지도",
      plot_bar: "막대그래프",
      plot_histogram: "히스토그램",
      plot_boxplot: "상자그림",
      plot_scatter: "산점도",
      plot_line: "선그래프",
      plot_frequency_polygon: "도수분포다각형",
      plot_stem_leaf: "줄기와 잎 그림",
      plot_pie: "원그래프",
      create_frequency_table: "도수분포표",
      create_crosstab: "교차표",
      plot_choropleth: "지도 시각화",
      compute_cross_dataset_comparison: "교차 대표값 비교",
      compute_cross_correlation: "교차 상관계수",
      plot_comparative_line: "비교 선그래프",
      plot_comparative_bar: "비교 막대그래프",
    };
    return labels[toolName] || toolName;
  }

  function statusLabel(status) {
    const labels = {
      created: "프로젝트 생성",
      topic_selected: "주제 선택 완료",
      dataset_chosen: "자료 선택 완료",
      analysis_done: "분석 완료",
      conclusion_submitted: "보고서 제출 완료",
      stopped: "중단됨",
    };
    return labels[status] || status || "-";
  }

  function formatNumber(value, fixed = true) {
    if (typeof value !== "number" || !Number.isFinite(value)) return escapeHtml(value);
    return value.toLocaleString("ko-KR", {
      minimumFractionDigits: fixed ? 2 : 0,
      maximumFractionDigits: fixed ? 2 : 0,
    });
  }

  function formatValue(value) {
    if (typeof value === "number") return formatNumber(value);
    if (Array.isArray(value)) return value.map((item) => escapeHtml(item)).join(", ");
    if (value && typeof value === "object") {
      return Object.entries(value)
        .map(([key, item]) => `${escapeHtml(key)}: ${formatValue(item)}`)
        .join("<br />");
    }
    return escapeHtml(value ?? "-");
  }

  function clampNumber(value, min, max, fallback) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.max(min, Math.min(max, number));
  }

  function sheetViewSettings() {
    const settings = state.sheetView || {};
    const columnWidths = {};
    if (settings.columnWidths && typeof settings.columnWidths === "object") {
      Object.entries(settings.columnWidths).forEach(([columnName, width]) => {
        const nextWidth = clampNumber(width, 80, 520, 0);
        if (columnName && nextWidth) columnWidths[columnName] = nextWidth;
      });
    }
    return {
      columnWidth: clampNumber(settings.columnWidth, 80, 520, 150),
      columnWidths,
      fontSize: clampNumber(settings.fontSize, 12, 18, 14),
    };
  }

  function sheetColumnWidth(columnName) {
    const settings = sheetViewSettings();
    return settings.columnWidths[columnName] || settings.columnWidth;
  }

  function sheetTableWidth(columns) {
    return 108 + columns.reduce((total, column) => total + sheetColumnWidth(column.name), 0);
  }

  function hasCustomSheetColumnWidths(columns) {
    const widths = sheetViewSettings().columnWidths;
    return columns.some((column) => widths[column.name]);
  }

  function analysisRowState() {
    const current = state.analysisRows || {};
    const rowCount = Number(state.sheet?.total_row_count ?? state.datasetSummary?.row_count ?? state.sheet?.row_count ?? 0);
    const selected = Array.isArray(current.selected)
      ? [...new Set(current.selected.map((value) => Number(value)).filter((value) => Number.isInteger(value) && value >= 0))]
      : [];
    return {
      mode: current.mode === "selected" ? "selected" : "all",
      selected: rowCount > 0 ? selected.filter((rowIndex) => rowIndex < rowCount) : selected,
    };
  }

  function selectedAnalysisRowIndices() {
    return analysisRowState().selected.sort((a, b) => a - b);
  }

  function analysisRowPayload() {
    const rows = analysisRowState();
    return rows.mode === "selected" ? selectedAnalysisRowIndices() : [];
  }

  function analysisRowLabel() {
    const rows = analysisRowState();
    if (rows.mode !== "selected") return "전체 자료";
    return `선택한 ${rows.selected.length}행`;
  }

  function normalizeFilterMap(filters) {
    const normalized = {};
    if (!filters || typeof filters !== "object") return normalized;
    Object.entries(filters).forEach(([columnName, criteria]) => {
      if (!columnName || !criteria) return;
      const entry = {};
      const rawValues = Array.isArray(criteria) ? criteria : criteria.values;
      const values = Array.isArray(rawValues)
        ? [...new Set(rawValues.map((value) => String(value ?? "").trim()).filter(Boolean))]
        : [];
      const query = typeof criteria.query === "string" ? criteria.query.trim() : "";
      if (values.length) entry.values = values;
      if (query) entry.query = query;
      if (entry.values || entry.query) normalized[columnName] = entry;
    });
    return normalized;
  }

  function activeSheetFilters() {
    return normalizeFilterMap(state.sheetFilters || {});
  }

  function activeSheetFilterCount() {
    return Object.keys(activeSheetFilters()).length;
  }

  function mergeFilterMaps(...maps) {
    const merged = {};
    maps.forEach((map) => {
      Object.entries(normalizeFilterMap(map)).forEach(([columnName, criteria]) => {
        const current = merged[columnName] || {};
        const bothHaveValues = Boolean(current.values?.length && criteria.values?.length);
        let values = criteria.values || current.values || [];
        if (current.values?.length && criteria.values?.length) {
          const allowed = new Set(current.values);
          values = criteria.values.filter((value) => allowed.has(value));
        } else if (current.values?.length) {
          values = current.values;
        }
        const query = [current.query, criteria.query].filter(Boolean).join(" ");
        const next = {};
        if (values.length) next.values = [...new Set(values)];
        if (bothHaveValues && !values.length) next.values = ["__NO_MATCH__"];
        if (query) next.query = query;
        if (next.values || next.query) merged[columnName] = next;
      });
    });
    return merged;
  }

  function categoricalUniqueValues(columnName) {
    const summary = state.datasetSummary?.columns?.[columnName] || {};
    return Array.isArray(summary.unique_values)
      ? summary.unique_values.map((value) => String(value ?? "")).filter(Boolean)
      : Array.isArray(summary.examples)
        ? summary.examples.map((value) => String(value ?? "")).filter(Boolean)
        : [];
  }

  function renderAdviceList(items) {
    const safeItems = Array.isArray(items) ? items.filter((item) => String(item ?? "").trim()) : [];
    if (!safeItems.length) return "";
    return `<ul class="hint-list">${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function renderPossibleResults(results) {
    const safeResults = Array.isArray(results) ? results.filter((item) => item && typeof item === "object") : [];
    if (!safeResults.length) return "";
    return `
      <div class="possible-results">
        ${safeResults
          .map(
            (result) => `
              <div>
                <strong>${escapeHtml(result.result_pattern || "예상 가능한 결과")}</strong>
                <p>${escapeHtml(result.interpretation || "")}</p>
                <p class="muted">${escapeHtml(result.decision_support || "")}</p>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderDatasetSummary() {
    const summaryColumns = state.datasetSummary?.columns || {};
    const rows = Object.entries(summaryColumns)
      .map(([columnName, info]) => {
        const examples = info.examples?.length ? info.examples.join(", ") : "-";
        const extra = info.dtype === "categorical" ? `고유값 ${info.unique_count ?? 0}개 · 예시 ${examples}` : "-";
        return `
          <tr>
            <td>
              <strong>${escapeHtml(info.display_name || columnName)}</strong>
              <span class="subtle">${escapeHtml(columnName)}</span>
            </td>
            <td>${dtypeLabel(info.dtype)}</td>
            <td>${formatNumber(info.missing_count || 0, false)}</td>
            <td>${info.min === undefined ? "-" : formatNumber(info.min)}</td>
            <td>${info.max === undefined ? "-" : formatNumber(info.max)}</td>
            <td>${info.mean === undefined ? "-" : formatNumber(info.mean)}</td>
            <td>${escapeHtml(extra)}</td>
          </tr>
        `;
      })
      .join("");
    return `
      <p class="muted">전체 ${formatNumber(state.datasetSummary?.row_count || 0, false)}행의 자료입니다.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>항목</th>
              <th>유형</th>
              <th>결측 수</th>
              <th>최솟값</th>
              <th>최댓값</th>
              <th>평균</th>
              <th>범주 요약</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  const COLUMN_ROLE_ORDER = ["measure", "group", "period", "location", "identifier", "reference"];
  const COLUMN_ROLE_HINTS = {
    measure: "크기를 재는 값입니다. 요약 통계량과 분포 그래프의 대상이 됩니다.",
    group: "자료를 몇 개의 집단으로 나눕니다. 집단별 비교의 기준이 됩니다.",
    period: "시간 순서를 나타냅니다. 변화 흐름을 볼 때 씁니다.",
    location: "위치를 나타냅니다. 지도로 표현할 수 있습니다.",
    identifier: "행을 하나씩 구분하는 이름표입니다. 그 자체를 분석하지는 않습니다.",
    reference: "자료의 출처나 형식을 적어 둔 항목입니다. 분석에는 쓰지 않습니다.",
  };

  function datasetSchemaPath(datasetId) {
    const level = schoolLevel();
    return `/api/datasets/${datasetId}/schema${level ? `?school_level=${encodeURIComponent(level)}` : ""}`;
  }

  function isPlaceholderDescription(column) {
    return !column.description || column.description === `자료의 '${column.name}' 항목`;
  }

  function columnValueText(columnName, info) {
    if (!info) return "";
    const parts = [];
    if (info.dtype === "numeric") {
      if (info.min !== undefined && info.max !== undefined) {
        parts.push(`${formatNumber(info.min)} ~ ${formatNumber(info.max)}`);
      }
      if (info.mean !== undefined) parts.push(`평균 ${formatNumber(info.mean)}`);
    } else {
      if (info.unique_count !== undefined) parts.push(`${formatNumber(info.unique_count, false)}가지`);
      if (info.examples?.length) parts.push(info.examples.slice(0, 4).join(", "));
    }
    if (info.missing_count) parts.push(`빈칸 ${formatNumber(info.missing_count, false)}개`);
    return parts.join(" · ");
  }

  function renderColumnCard(column) {
    const info = state.datasetSummary?.columns?.[column.name];
    const valueText = columnValueText(column.name, info);
    const meaning = isPlaceholderDescription(column)
      ? `<p class="muted">설명이 아직 없습니다. 값을 보고 뜻을 짐작해 보세요.</p>`
      : `<p>${escapeHtml(column.description)}</p>`;
    const valueLabels = column.value_labels?.length
      ? `<ul class="column-value-list">${column.value_labels
          .map(
            (item) =>
              `<li><strong>${escapeHtml(item.label || item.value)}</strong>${
                item.unit ? ` <span class="subtle-inline">${escapeHtml(item.unit)}</span>` : ""
              }${item.note ? `<span class="subtle">${escapeHtml(item.note)}</span>` : ""}</li>`,
          )
          .join("")}</ul>`
      : "";
    const warnings = column.warnings?.length
      ? `<ul class="column-warnings">${column.warnings
          .map((text) => `<li>${escapeHtml(text)}</li>`)
          .join("")}</ul>`
      : "";
    const suggestions = column.suggestions?.length
      ? `<div class="column-suggestions">
          <dt>할 수 있는 분석</dt>
          <ul>
            ${column.suggestions
              .map(
                (item, index) => `
                  <li>
                    <div>
                      <strong>${escapeHtml(item.label)}</strong>
                      <span class="subtle">${escapeHtml(item.why || "")}</span>
                    </div>
                    <button type="button" class="secondary" data-column-suggestion="${escapeHtml(column.name)}" data-suggestion-index="${index}">실행</button>
                  </li>
                `,
              )
              .join("")}
          </ul>
        </div>`
      : "";
    return `
      <article class="column-card">
        <div class="column-card-head">
          <strong>${escapeHtml(column.display_name || column.name)}</strong>
          <span class="chip">${escapeHtml(dtypeLabel(column.dtype))}</span>
          ${column.unit ? `<span class="chip">${escapeHtml(column.unit)}</span>` : ""}
          ${column.estimated ? `<span class="chip estimated-chip">AI 추정</span>` : ""}
        </div>
        <span class="subtle">${escapeHtml(column.name)}</span>
        <dl class="column-card-body">
          <dt>뜻</dt><dd>${meaning}</dd>
          <dt>값</dt><dd>${valueText ? escapeHtml(valueText) : '<span class="muted">-</span>'}${valueLabels}</dd>
        </dl>
        ${warnings}
        ${suggestions}
      </article>
    `;
  }

  function attachColumnSuggestionEvents() {
    view.querySelectorAll("[data-column-suggestion]").forEach((button) => {
      button.addEventListener("click", () => {
        const column = (state.dataset?.columns || []).find(
          (item) => item.name === button.dataset.columnSuggestion,
        );
        const suggestion = column?.suggestions?.[Number(button.dataset.suggestionIndex)];
        if (!suggestion) return;
        runAnalysisRequest(suggestion.tool_name, suggestion.tool_args);
      });
    });
  }

  function renderColumnCards() {
    const columns = state.dataset?.columns || [];
    if (!columns.length) return "";
    const grouped = new Map();
    columns.forEach((column) => {
      const role = COLUMN_ROLE_ORDER.includes(column.role) ? column.role : "measure";
      if (!grouped.has(role)) grouped.set(role, []);
      grouped.get(role).push(column);
    });

    const sections = COLUMN_ROLE_ORDER.filter((role) => grouped.has(role)).map((role) => {
      const items = grouped.get(role);
      const label = escapeHtml(items[0].role_label || role);
      const cards = items.map(renderColumnCard).join("");
      const body = `
        <p class="muted">${escapeHtml(COLUMN_ROLE_HINTS[role] || "")}</p>
        <div class="column-card-grid">${cards}</div>
      `;
      if (items.every((column) => column.secondary)) {
        return `
          <details class="column-role-group">
            <summary>${label} <span class="subtle-inline">${items.length}개 · 분석에 쓰지 않음</span></summary>
            ${body}
          </details>
        `;
      }
      return `
        <div class="column-role-group">
          <h3>${label} <span class="subtle-inline">${items.length}개</span></h3>
          ${body}
        </div>
      `;
    });
    return sections.join("");
  }

  function renderColumnMeaningPanel() {
    if (!state.dataset?.uploaded || !(state.dataset?.columns || []).length) return "";
    const proposals = state.columnMeanings;
    if (!proposals?.length) {
      return `
        <section class="column-meaning-panel">
          <div>
            <strong>항목 뜻이 비어 있나요?</strong>
            <span class="subtle">AI가 컬럼명과 값을 보고 한글 표시명과 뜻을 추정해 줍니다.</span>
          </div>
          <button type="button" id="request-column-meanings">항목 뜻 AI로 채우기</button>
        </section>
      `;
    }
    return `
      <section class="column-meaning-panel proposals">
        <div>
          <strong>AI가 추정한 항목 뜻입니다.</strong>
          <span class="subtle">추정이라 틀릴 수 있습니다. 확인하고 적용하거나 다시 받아 보세요.</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>컬럼</th><th>표시명</th><th>뜻</th></tr></thead>
            <tbody>
              ${proposals
                .map(
                  (item) => `
                    <tr>
                      <td><span class="subtle">${escapeHtml(item.name)}</span></td>
                      <td>${escapeHtml(item.display_name || "-")}</td>
                      <td>${escapeHtml(item.description || "-")}${
                        item.confident === false
                          ? ` <span class="subtle-inline">(확실하지 않음)</span>`
                          : ""
                      }</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
        <div class="actions">
          <button type="button" class="primary" id="apply-column-meanings">이대로 적용</button>
          <button type="button" id="request-column-meanings">다시 제안받기</button>
          <button type="button" id="cancel-column-meanings">취소</button>
        </div>
      </section>
    `;
  }

  function attachColumnMeaningEvents() {
    document.getElementById("request-column-meanings")?.addEventListener("click", async () => {
      setLoading("항목의 뜻을 추정하는 중입니다.");
      try {
        state.columnMeanings = await StatApi.request(
          `/api/projects/${state.project.project_id}/column-meaning-suggestions`,
        );
        save();
      } catch (error) {
        StatApi.toast(error.message);
      }
      renderAnalysisWorkspace();
    });
    document.getElementById("apply-column-meanings")?.addEventListener("click", async () => {
      setLoading("항목 뜻을 자료에 저장하는 중입니다.");
      try {
        state.dataset = await StatApi.request(
          `/api/projects/${state.project.project_id}/column-meanings`,
          { method: "POST", body: JSON.stringify({ meanings: state.columnMeanings }) },
        );
        state.columnMeanings = null;
        save();
        StatApi.toast("항목 뜻을 저장했습니다. 이상하면 다시 제안받을 수 있습니다.");
      } catch (error) {
        StatApi.toast(error.message);
      }
      renderAnalysisWorkspace();
    });
    document.getElementById("cancel-column-meanings")?.addEventListener("click", () => {
      state.columnMeanings = null;
      save();
      renderAnalysisWorkspace();
    });
  }

  function renderSourceNotes() {
    const notes = state.dataset?.source_notes || [];
    if (!notes.length) return "";
    return `
      <section class="source-notes">
        <h3>이 자료를 읽을 때</h3>
        <dl>
          ${notes
            .map(
              (note) =>
                `<dt>${escapeHtml(note.label)}</dt><dd>${escapeHtml(note.text)}</dd>`,
            )
            .join("")}
        </dl>
      </section>
    `;
  }

  function renderStatisticsTable(statistics) {
    const rows = Object.entries(statistics || {})
      .flatMap(([columnName, metrics]) =>
        Object.entries(metrics).map(
          ([key, value]) => `
            <tr>
              <td>${escapeHtml(columnName)}</td>
              <td>${metricLabel(key)}</td>
              <td>${formatValue(value)}</td>
            </tr>
          `,
        ),
      )
      .join("");
    return `
      <div class="table-wrap">
        <table>
          <thead><tr><th>항목</th><th>통계량</th><th>값</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderKeyValueTable(data) {
    const rows = Object.entries(data || {})
      .map(
        ([key, value]) => `
          <tr>
            <th>${metricLabel(key)}</th>
            <td>${formatValue(value)}</td>
          </tr>
        `,
      )
      .join("");
    return `
      <div class="table-wrap">
        <table>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderRowsTable(rows) {
    if (!rows.length) return `<p class="muted">자료가 없습니다.</p>`;
    const keys = Object.keys(rows[0]);
    return `
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>${keys.map((k) => {
              const isTime = String(k).includes("시점") || String(k).includes("연도") || String(k).includes("시간");
              return `<th${isTime ? ' style="text-align: left;"' : ''}>${escapeHtml(k)}</th>`;
            }).join("")}</tr>
          </thead>
          <tbody>
            ${safeRows
              .map(
                (row) => `
                  <tr>${columns.map((column) => `<td>${formatValue(row[column])}</td>`).join("")}</tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function displayName(columnName) {
    return state.dataset?.columns?.find((column) => column.name === columnName)?.display_name || columnName;
  }

  function renderAnalysisData(toolResult) {
    const data = toolResult.data || {};
    if (data.png_url) {
      return `<img class="analysis-image" src="${StatApi.chartUrl(data.png_url)}" alt="${escapeHtml(data.alt_text)}" />`;
    }
    if (data.group_by && Array.isArray(data.groups) && data.groups[0]?.statistics) {
      return renderGroupedStatisticsTable(data);
    }
    if (data.statistics) return renderStatisticsTable(data.statistics);
    if (Array.isArray(data.groups) && data.overall) return renderGroupedCorrelationTable(data);
    if (Array.isArray(data.rows)) return renderRowsTable(data.rows);
    return renderKeyValueTable(data);
  }

  function renderGroupedStatisticsTable(data) {
    const groups = data.groups || [];
    const columns = Array.isArray(data.columns) && data.columns.length
      ? data.columns
      : Object.keys(groups[0]?.statistics || {});
    const overall = data.overall;
    const headers = [
      ...groups.map((group) => escapeHtml(String(group.group))),
      ...(overall ? ["전체"] : []),
    ];
    const tables = columns
      .map((columnName) => {
        const metrics = [
          ...new Set(
            groups.flatMap((group) => Object.keys(group.statistics?.[columnName] || {})),
          ),
        ];
        const rows = metrics
          .map((metric) => {
            const cells = [
              ...groups.map((group) => formatValue(group.statistics?.[columnName]?.[metric])),
              ...(overall ? [formatValue(overall.statistics?.[columnName]?.[metric])] : []),
            ];
            return `<tr><th>${metricLabel(metric)}</th>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
          })
          .join("");
        const sizeCells = [
          ...groups.map((group) => escapeHtml(String(group.sample_sizes?.[columnName] ?? group.sample_size ?? ""))),
          ...(overall ? [escapeHtml(String(overall.sample_size ?? ""))] : []),
        ];
        return `
          <div class="table-wrap">
            <table class="result-table">
              <caption>${escapeHtml(displayName(columnName))}</caption>
              <thead><tr><th>통계량</th>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
              <tbody>
                <tr><th>자료 수</th>${sizeCells.map((cell) => `<td>${cell}</td>`).join("")}</tr>
                ${rows}
              </tbody>
            </table>
          </div>
        `;
      })
      .join("");
    return `
      <p><strong>${escapeHtml(displayName(data.group_by))}</strong> 집단별로 대표값과 산포도를 나눠 계산했습니다.
      같은 줄의 값을 좌우로 비교해 보세요.</p>
      ${tables}
    `;
  }

  function renderGroupedCorrelationTable(data) {
    const rows = data.groups
      .map((group) => {
        const value =
          group.pearson_correlation === null
            ? `<span class="muted">${escapeHtml(group.note || "계산하지 않음")}</span>`
            : escapeHtml(String(group.pearson_correlation));
        const label = group.interpretation_label ? escapeHtml(group.interpretation_label) : "";
        return `<tr><td>${escapeHtml(group.group)}</td><td>${group.sample_size}</td><td>${value}</td><td>${label}</td></tr>`;
      })
      .join("");
    const contrast = data.sign_contrast
      ? `<p class="contrast-banner">집단마다 상관계수의 방향이 서로 다릅니다. 전체 값만 보고 결론을 내리기 전에, 왜 집단별로 다른지 살펴보세요.</p>`
      : "";
    return `
      <p><strong>${escapeHtml(displayName(data.x_column))}</strong>와 <strong>${escapeHtml(displayName(data.y_column))}</strong>의 관계를
      <strong>${escapeHtml(displayName(data.group_by))}</strong> 집단별로 나눠 계산했습니다.</p>
      <table class="result-table">
        <thead><tr><th>집단</th><th>표본 수</th><th>상관계수</th><th>관계 해석</th></tr></thead>
        <tbody>
          <tr class="overall-row">
            <td>전체</td>
            <td>${data.overall.sample_size}</td>
            <td>${escapeHtml(String(data.overall.pearson_correlation))}</td>
            <td>${escapeHtml(data.overall.interpretation_label)}</td>
          </tr>
          ${rows}
        </tbody>
      </table>
      ${contrast}
    `;
  }

  function defaultSynthesisPanel() {
    return { selectedDatasetIds: [], keyMappings: {}, toolName: "compute_cross_correlation" };
  }

  function synthesisPanelState() {
    if (!state.synthesisPanel) state.synthesisPanel = defaultSynthesisPanel();
    return state.synthesisPanel;
  }

  function synthesisAvailableDatasetIds() {
    const ids = Array.isArray(state.project?.dataset_ids) ? state.project.dataset_ids : [];
    return [...new Set(ids)];
  }

  function synthesisDatasetLabel(datasetId) {
    return state.synthesisDatasetSchemas?.[datasetId]?.name || datasetId;
  }

  async function toggleSynthesisDataset(datasetId, checked) {
    const panel = synthesisPanelState();
    if (checked) {
      if (!panel.selectedDatasetIds.includes(datasetId)) panel.selectedDatasetIds.push(datasetId);
    } else {
      panel.selectedDatasetIds = panel.selectedDatasetIds.filter((id) => id !== datasetId);
    }
    if (checked && !state.synthesisDatasetSchemas?.[datasetId]) {
      const schema = await StatApi.request(`/api/datasets/${datasetId}/schema`);
      state = {
        ...state,
        synthesisDatasetSchemas: { ...(state.synthesisDatasetSchemas || {}), [datasetId]: schema },
      };
    }
    renderAnalysisWorkspace();
  }

  function renderSynthesisToolFields(toolName, allColumns, numericColumns) {
    const firstNumeric = numericColumns[0]?.name || "";
    const secondNumeric = numericColumns[1]?.name || firstNumeric;
    if (toolName === "compute_cross_correlation") {
      return `
        ${renderAnalysisField(
          "가로축 항목",
          `<select id="synthesis-x-column">${renderColumnOptions(numericColumns, firstNumeric)}</select>`,
        )}
        ${renderAnalysisField(
          "세로축 항목",
          `<select id="synthesis-y-column">${renderColumnOptions(numericColumns, secondNumeric)}</select>`,
        )}
      `;
    }
    if (toolName === "compute_cross_dataset_comparison") {
      return `
        ${renderAnalysisField(
          "비교할 항목(2개 이상)",
          `<select id="synthesis-value-columns" multiple size="4">${renderColumnOptions(numericColumns, [
            firstNumeric,
            secondNumeric,
          ])}</select>`,
        )}
        <div class="analysis-field">
          <span>통계량</span>
          <div class="checkbox-grid">
            ${["mean", "median", "min", "max", "std", "q1", "q3", "iqr"]
              .map(
                (stat, index) => `
                  <label><input type="checkbox" name="synthesis-stat" value="${stat}" ${
                    index < 4 ? "checked" : ""
                  } /> ${metricLabel(stat)}</label>
                `,
              )
              .join("")}
          </div>
        </div>
      `;
    }
    if (toolName === "plot_comparative_line") {
      return `
        ${renderAnalysisField(
          "가로축(x) 항목",
          `<select id="synthesis-x-col">${renderColumnOptions(allColumns, allColumns[0]?.name || "")}</select>`,
        )}
        ${renderAnalysisField(
          "비교할 항목(2개 이상)",
          `<select id="synthesis-y-cols" multiple size="4">${renderColumnOptions(numericColumns, [
            firstNumeric,
            secondNumeric,
          ])}</select>`,
        )}
      `;
    }
    if (toolName === "plot_comparative_bar") {
      return `
        ${renderAnalysisField(
          "범주 항목",
          `<select id="synthesis-category-col">${renderColumnOptions(allColumns, allColumns[0]?.name || "")}</select>`,
        )}
        ${renderAnalysisField(
          "비교할 항목(2개 이상)",
          `<select id="synthesis-value-cols" multiple size="4">${renderColumnOptions(numericColumns, [
            firstNumeric,
            secondNumeric,
          ])}</select>`,
        )}
      `;
    }
    return "";
  }

  function renderSynthesisResultPanel() {
    if (!state.synthesisResult) return "";
    const result = state.synthesisResult;
    const chartUrls = result.chart_urls || [];
    const observations = state.synthesisObservations;
    return `
      <div class="synthesis-result">
        <h3>${escapeHtml(toolLabel(result.tool_name))} 결과</h3>
        ${renderAnalysisData({ data: result.result?.data || {} })}
        ${chartUrls
          .map(
            (url) => `<img class="analysis-image report-chart" src="${StatApi.chartUrl(url)}" alt="종합 비교 그래프" />`,
          )
          .join("")}
        <div class="actions">
          <button type="button" id="synthesis-observations-btn">관찰 도움받기</button>
        </div>
        ${
          observations
            ? `
              <div class="synthesis-observations">
                <p class="muted">${escapeHtml(observations.warning || "")}</p>
                <ul>${(observations.observations || []).map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul>
                <h4>생각해볼 질문</h4>
                <ul>${(observations.questions || []).map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul>
              </div>
            `
            : ""
        }
      </div>
    `;
  }

  function renderSynthesisPanel() {
    const availableIds = synthesisAvailableDatasetIds();
    if (availableIds.length < 2) return "";
    const panel = synthesisPanelState();
    const schemas = state.synthesisDatasetSchemas || {};
    const readySelected = panel.selectedDatasetIds.filter((id) => schemas[id]);
    const seenColumns = new Map();
    readySelected.forEach((id) => {
      (schemas[id]?.columns || []).forEach((column) => {
        if (!seenColumns.has(column.name)) seenColumns.set(column.name, column);
      });
    });
    const allColumns = [...seenColumns.values()];
    const numericColumns = allColumns.filter((column) => column.dtype === "numeric");

    return `
      <section class="synthesis-panel">
        <h2>자료 종합 비교</h2>
        <p class="muted">
          이 프로젝트에서 사용한 자료 중 2개 이상을 골라 나란히 비교할 수 있습니다.
          비교 결과는 결론이 아니라 관찰과 질문만 제공합니다.
        </p>
        <fieldset class="synthesis-dataset-picker">
          <legend>비교할 자료</legend>
          ${availableIds
            .map(
              (id) => `
                <label class="inline-check">
                  <input type="checkbox" data-synthesis-dataset="${escapeHtml(id)}" ${
                    panel.selectedDatasetIds.includes(id) ? "checked" : ""
                  } />
                  ${escapeHtml(synthesisDatasetLabel(id))}
                </label>
              `,
            )
            .join("")}
        </fieldset>
        ${
          readySelected.length >= 2
            ? `
              <fieldset class="synthesis-key-mapping">
                <legend>결합 기준 컬럼(자료별 지역·시점 등 공통 항목)</legend>
                ${readySelected
                  .map((id) => {
                    const columns = schemas[id]?.columns || [];
                    return renderAnalysisField(
                      synthesisDatasetLabel(id),
                      `<select data-synthesis-key="${escapeHtml(id)}">${renderColumnOptions(
                        columns,
                        panel.keyMappings[id] || columns[0]?.name || "",
                      )}</select>`,
                    );
                  })
                  .join("")}
              </fieldset>
              <label class="analysis-field">
                <span>비교 방법</span>
                <select id="synthesis-tool-name">
                  <option value="compute_cross_correlation" ${
                    panel.toolName === "compute_cross_correlation" ? "selected" : ""
                  }>교차 상관계수</option>
                  <option value="compute_cross_dataset_comparison" ${
                    panel.toolName === "compute_cross_dataset_comparison" ? "selected" : ""
                  }>교차 대표값 비교</option>
                  <option value="plot_comparative_line" ${
                    panel.toolName === "plot_comparative_line" ? "selected" : ""
                  }>비교 선그래프</option>
                  <option value="plot_comparative_bar" ${
                    panel.toolName === "plot_comparative_bar" ? "selected" : ""
                  }>비교 막대그래프</option>
                </select>
              </label>
              ${renderSynthesisToolFields(panel.toolName, allColumns, numericColumns)}
              <div class="actions">
                <button type="button" class="primary" id="run-synthesis">종합 비교 실행</button>
              </div>
            `
            : `<p class="muted">자료를 2개 이상 선택하면 결합 기준과 비교 방법을 고를 수 있습니다.</p>`
        }
        ${renderSynthesisResultPanel()}
      </section>
    `;
  }

  function attachSynthesisPanelEvents() {
    document.querySelectorAll("[data-synthesis-dataset]").forEach((input) => {
      input.addEventListener("change", () => toggleSynthesisDataset(input.dataset.synthesisDataset, input.checked));
    });
    document.querySelectorAll("[data-synthesis-key]").forEach((select) => {
      select.addEventListener("change", () => {
        synthesisPanelState().keyMappings[select.dataset.synthesisKey] = select.value;
      });
    });
    const toolSelect = document.getElementById("synthesis-tool-name");
    if (toolSelect) {
      toolSelect.addEventListener("change", () => {
        synthesisPanelState().toolName = toolSelect.value;
        renderAnalysisWorkspace();
      });
    }
    document.getElementById("run-synthesis")?.addEventListener("click", runSynthesis);
    document.getElementById("synthesis-observations-btn")?.addEventListener("click", fetchSynthesisObservations);
  }

  async function runSynthesis() {
    const panel = synthesisPanelState();
    const schemas = state.synthesisDatasetSchemas || {};
    const datasetIds = panel.selectedDatasetIds.filter((id) => schemas[id]);
    if (datasetIds.length < 2) {
      StatApi.toast("비교할 자료를 2개 이상 선택해 주세요.");
      return;
    }
    const keyColumnMappings = {};
    datasetIds.forEach((id) => {
      keyColumnMappings[id] = panel.keyMappings[id] || (schemas[id]?.columns || [])[0]?.name || "";
    });
    const toolName = panel.toolName;
    let toolArgs = {};
    if (toolName === "compute_cross_correlation") {
      toolArgs = { x_column: inputValue("synthesis-x-column"), y_column: inputValue("synthesis-y-column") };
    } else if (toolName === "compute_cross_dataset_comparison") {
      toolArgs = {
        value_columns: selectedValues("synthesis-value-columns"),
        statistics: checkedValues("synthesis-stat"),
      };
    } else if (toolName === "plot_comparative_line") {
      toolArgs = { x_col: inputValue("synthesis-x-col"), y_cols: selectedValues("synthesis-y-cols") };
    } else if (toolName === "plot_comparative_bar") {
      toolArgs = { category_col: inputValue("synthesis-category-col"), value_cols: selectedValues("synthesis-value-cols") };
    }
    const result = await StatApi.request(`/api/projects/${state.project.project_id}/synthesis`, {
      method: "POST",
      body: JSON.stringify({
        tool_name: toolName,
        tool_args: toolArgs,
        join_spec: { dataset_ids: datasetIds, key_column_mappings: keyColumnMappings },
      }),
    });
    const project = await StatApi.request(`/api/projects/${state.project.project_id}`);
    const synthesisHistory = await StatApi.request(`/api/projects/${state.project.project_id}/synthesis`);
    state = { ...state, synthesisResult: result, synthesisObservations: null, synthesisHistory, project };
    renderAnalysisWorkspace();
  }

  async function fetchSynthesisObservations() {
    if (!state.synthesisResult) return;
    const observations = await StatApi.request(
      `/api/synthesis/${state.synthesisResult.synthesis_result_id}/observations`,
    );
    state = { ...state, synthesisObservations: observations };
    renderAnalysisWorkspace();
  }

  function latestStepPayload(stepType) {
    const projectSteps = Array.isArray(state.project?.steps) ? state.project.steps : [];
    for (let index = projectSteps.length - 1; index >= 0; index -= 1) {
      if (projectSteps[index]?.step_type === stepType) return projectSteps[index].payload || {};
    }
    return {};
  }

  function currentTopicTitle() {
    return state.project?.custom_topic_title || state.topic?.title || state.project?.custom_topic_question || "선택한 주제";
  }

  function currentTopicQuestion() {
    return state.project?.custom_topic_question || state.topic?.question || state.topic?.title || "";
  }

  function selectedDatasetId() {
    return state.project?.dataset_id || state.dataset?.dataset_id || "";
  }

  function selectedDatasetSummaryRows() {
    if (!state.dataset) return "";
    const rows = [
      ["출처", state.dataset.source_note || state.dataset.source || "-"],
      ["기간", state.dataset.time_range || "-"],
      ["지역 단위", state.dataset.geographic_unit || "-"],
    ];
    if (state.datasetSummary?.row_count) {
      rows.push(["규모", `${formatNumber(state.datasetSummary.row_count, false)}행 · ${formatNumber(state.dataset.columns?.length || 0, false)}열`]);
    }
    return `<dl class="advice-detail-list compact-dl">${rows
      .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
      .join("")}</dl>`;
  }

  function renderSelectedTopicStage() {
    const topicPayload = latestStepPayload("topic_selected");
    const advisorInput = state.questionDraft || topicPayload.advisor_input || "";
    const question = currentTopicQuestion();
    view.innerHTML = `
      <section class="stage-recap selected-stage-card">
        <div>
          <p class="eyebrow">현재 프로젝트의 주제</p>
          <h2>${escapeHtml(currentTopicTitle())}</h2>
          <p>${escapeHtml(question)}</p>
          <div class="meta-row">
            <span class="chip school-level-chip">학교급 · ${escapeHtml(schoolLevelLabel())}</span>
          </div>
          ${
            state.topic?.guidance
              ? `<p class="muted topic-guidance">${escapeHtml(state.topic.guidance)}</p>`
              : ""
          }
        </div>
        ${
          advisorInput
            ? `<div class="stage-memory">
                <strong>처음 적은 내용</strong>
                <p>${escapeHtml(advisorInput)}</p>
              </div>`
            : ""
        }
        <div class="actions">
          <button type="button" id="topic-to-dataset" class="primary">자료 단계로 이동</button>
          <button type="button" id="topic-project-manager">프로젝트 관리</button>
          <button type="button" id="topic-new-project">새 프로젝트</button>
        </div>
      </section>
    `;
    document.getElementById("topic-to-dataset")?.addEventListener("click", () => navigateToStep(STEP.DATA));
    document.getElementById("topic-project-manager")?.addEventListener("click", openProjectManager);
    document.getElementById("topic-new-project")?.addEventListener("click", restart);
  }

  function renderSelectedDatasetPanel() {
    if (!state.dataset) return "";
    return `
      <section class="stage-recap selected-stage-card">
        <div>
          <p class="eyebrow">현재 선택한 자료</p>
          <h2>${escapeHtml(state.dataset.name || selectedDatasetId())}</h2>
          <p>${escapeHtml(state.dataset.description || "")}</p>
        </div>
        ${selectedDatasetSummaryRows()}
        <div class="actions">
          <button type="button" class="primary" id="dataset-to-analysis">분석 단계로 이동</button>
        </div>
      </section>
    `;
  }

  function attachSelectedDatasetPanelEvents() {
    document.getElementById("dataset-to-analysis")?.addEventListener("click", () => navigateToStep(STEP.ANALYSIS));
  }

  function latestAnalysisResult() {
    if (state.analysis) return state.analysis;
    const history = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    return history[history.length - 1] || null;
  }

  function analysisRowLabelFor(analysis) {
    return analysis?.row_selection?.row_count
      ? `선택한 ${formatNumber(analysis.row_selection.row_count, false)}행`
      : "전체 자료";
  }

  function interpretationDraft(analysis) {
    const drafts = state.interpretationDrafts || {};
    const draft = drafts[analysis.analysis_result_id];
    return draft === undefined ? analysis.interpretation || "" : draft;
  }

  function interpretationIsDirty(analysis) {
    return interpretationDraft(analysis).trim() !== (analysis.interpretation || "").trim();
  }

  function save() {
    StatState.setStudentState(state);
    renderProgress();
    renderStepControls();
    renderSummary();
    renderAiCoach();
    scheduleTutorialRender();
  }

  function availableSteps() {
    const available = new Set([STEP.TOPIC]);
    if (state.topic || state.questionAdvice || Array.isArray(state.datasets)) available.add(STEP.DATA);
    if (state.dataset && state.options?.length) available.add(STEP.ANALYSIS);
    if (state.report) {
      available.add(STEP.REPORT);
      available.add(STEP.FEEDBACK);
    }
    return available;
  }

  function isStepAvailable(index) {
    return availableSteps().has(index);
  }

  function nearestAvailableStep(target) {
    const available = availableSteps();
    if (available.has(target)) return target;
    for (let index = target; index >= 0; index -= 1) {
      if (available.has(index)) return index;
    }
    return 0;
  }

  function previousAvailableStep() {
    for (let index = state.step - 1; index >= 0; index -= 1) {
      if (isStepAvailable(index)) return index;
    }
    return null;
  }

  function nextAvailableStep() {
    for (let index = state.step + 1; index < steps.length; index += 1) {
      if (isStepAvailable(index)) return index;
    }
    return null;
  }

  function renderProgress() {
    const available = availableSteps();
    progress.innerHTML = steps
      .map((label, index) => {
        const classes = [
          index === state.step ? "active" : "",
          available.has(index) ? "available" : "locked",
          index < state.step && available.has(index) ? "completed" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `
          <li class="${classes}">
            <button
              type="button"
              data-step="${index}"
              ${available.has(index) ? "" : "disabled"}
              ${index === state.step ? 'aria-current="step"' : ""}
              aria-label="${index + 1}단계 ${label}"
            >
              <span class="progress-step-number" aria-hidden="true">${index + 1}</span>
              <span class="progress-step-label">${label}</span>
            </button>
          </li>
        `;
      })
      .join("");
    progress.querySelectorAll("[data-step]").forEach((button) => {
      button.addEventListener("click", () => navigateToStep(Number(button.dataset.step)));
    });
  }

  function renderStepControls() {
    const previousStep = previousAvailableStep();
    const nextStep = nextAvailableStep();
    stepControls.innerHTML = `
      <button type="button" id="prev-step" ${previousStep === null ? "disabled" : ""}>이전 단계</button>
      <span>${state.step + 1} / ${steps.length} · ${steps[state.step]}</span>
      <button type="button" id="next-step" ${nextStep === null ? "disabled" : ""}>다음 단계</button>
    `;
    document.getElementById("prev-step").addEventListener("click", () => {
      if (previousStep !== null) navigateToStep(previousStep);
    });
    document.getElementById("next-step").addEventListener("click", () => {
      if (nextStep !== null) navigateToStep(nextStep);
    });
  }

  function renderSummary() {
    if (!summary || !feedbackBox) return;
    const rows = [
      ["프로젝트", state.project?.project_id || "-"],
      ["주제", state.topic?.title || "-"],
      ["자료", state.dataset?.name || "-"],
      ["상태", statusLabel(state.project?.status)],
    ];
    summary.innerHTML = rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
    if (state.report?.feedback_text) {
      feedbackBox.innerHTML = `<h2>교사 피드백</h2><p>${escapeHtml(state.report.feedback_text)}</p>`;
    } else {
      feedbackBox.innerHTML = `<h2>교사 피드백</h2><p class="muted">아직 저장된 피드백이 없습니다.</p>`;
    }
  }

  function localCoach() {
    const guardrail = "AI 코치는 결론을 대신 쓰지 않고, 다음에 확인할 관찰 포인트만 제안합니다.";
    if (!state.project) {
      if (state.startMode === "question") {
        return {
          role_name: "AI 탐구 코치",
          message: "떠오르는 주제나 현상을 적으면 탐구 가능한 통계 질문 후보를 함께 좁혀 볼 수 있습니다.",
          next_actions: ["조사 대상을 떠올리기", "숫자나 선택지로 기록할 수 있는 변수를 생각하기"],
          guardrail,
          metadata: { source: "local" },
        };
      }
      return {
        role_name: "AI 탐구 코치",
        message: "새 프로젝트를 어떤 방식으로 시작할지 고르세요. 직접 적어도 되고 예시 주제에서 출발해도 됩니다.",
        next_actions: ["탐구 질문 직접 입력하기", "예시 주제 카드에서 고르기"],
        guardrail,
        metadata: { source: "local" },
      };
    }
    const defaults = [
      "현재 단계의 선택지를 천천히 비교해 보세요.",
      "다음 단계로 넘어가기 전에 숫자 근거가 충분한지 확인해 보세요.",
    ];
    if (state.step === STEP.DATA) {
      return {
        role_name: "AI 탐구 코치",
        message: "자료 단계입니다. AI 추천 자료, 직접 검색, CSV 업로드 중에서 탐구 질문을 답하는 데 가장 알맞은 방식을 고를 수 있습니다.",
        next_actions: [
          "탐구 질문에 맞는 AI 추천 자료 먼저 확인하기",
          "필요하면 검색어로 공식 통계 후보 넓히기",
          "직접 수집한 자료가 있으면 CSV로 올리기",
        ],
        guardrail,
        metadata: { source: "local" },
      };
    }
    return {
      role_name: "AI 탐구 코치",
      message: `${steps[state.step]} 단계입니다. 필요하면 버튼을 눌러 AI 코치에게 지금 단계의 힌트를 받아 보세요.`,
      next_actions: defaults,
      guardrail,
      metadata: { source: "local" },
    };
  }

  function renderAiCoach() {
    if (!aiCoachBox) return;
    const coach = state.coach?.ui_step === state.step ? state.coach : localCoach();
    aiCoachBox.innerHTML = `
      <h2>${escapeHtml(coach.role_name || "AI 탐구 코치")}</h2>
      <p>${escapeHtml(coach.message)}</p>
      <ul class="coach-list">
        ${(coach.next_actions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
      <p class="muted">${escapeHtml(coach.guardrail || "")}</p>
      <div class="coach-actions">
        <button type="button" id="ask-ai-coach" ${state.project ? "" : "disabled"}>AI 코치에게 묻기</button>
      </div>
    `;
    document.getElementById("ask-ai-coach").addEventListener("click", loadAiCoach);
  }

  async function loadAiCoach() {
    if (!state.project?.project_id) {
      StatApi.toast("주제를 선택한 뒤 AI 코치에게 물어볼 수 있습니다.");
      return;
    }
    const button = aiCoachBox.querySelector("#ask-ai-coach");
    if (button) {
      button.disabled = true;
      button.textContent = "AI 코치 생각 중...";
    }
    aiCoachBox.insertAdjacentHTML(
      "beforeend",
      loadingMarkup(
        "현재 단계에 맞는 힌트를 준비하고 있습니다.",
        {
          label: "현재 단계",
          text: `${steps[state.step]} 단계`,
        },
        "compact",
        "coach-loading",
      ),
    );
    try {
      const coach = await StatApi.request(`/api/projects/${state.project.project_id}/ai-coach`, {
        method: "POST",
        body: JSON.stringify({ prompt_text: `${steps[state.step]} 단계에서 다음 행동 제안` }),
      });
      state = { ...state, coach: { ...coach, ui_step: state.step } };
    } catch (error) {
      const fallback = localCoach();
      state = {
        ...state,
        coach: {
          ...fallback,
          ui_step: state.step,
          message: `${fallback.message} 서버 AI 코치 호출은 실패했습니다: ${error.message}`,
        },
      };
    }
    save();
  }

  function loadingContextRows(context = {}) {
    const source = typeof context === "string" ? { text: context } : context || {};
    if (!source || typeof source !== "object") return [];
    const rows = [];
    const mainText = String(source.text ?? "").trim();
    if (mainText) {
      rows.push({ label: source.label || "학생 입력", value: mainText });
    }
    const items = Array.isArray(source.items) ? source.items : [];
    items.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const value = String(item.value ?? "").trim();
      if (!value) return;
      rows.push({ label: item.label || "참고 내용", value });
    });
    return rows;
  }

  function renderLoadingContext(context = {}) {
    const rows = loadingContextRows(context);
    if (!rows.length) return "";
    return `
      <div class="loading-context">
        ${rows
          .map(
            (row) => `
              <section>
                <strong>${escapeHtml(row.label)}</strong>
                <p>${escapeHtml(row.value)}</p>
              </section>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function loadingMarkup(text, context = {}, variant = "", id = "") {
    const classes = ["loading-panel", variant ? `loading-panel-${variant}` : ""].filter(Boolean).join(" ");
    return `
      <section ${id ? `id="${escapeHtml(id)}"` : ""} class="${classes}" aria-live="polite" aria-busy="true">
        <div class="loading-head">
          <div class="loading-dots" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <p class="loading-message">${escapeHtml(text)}</p>
        </div>
        ${renderLoadingContext(context)}
      </section>
    `;
  }

  function setLoading(text, context = {}) {
    view.innerHTML = loadingMarkup(text, context);
  }

  function navigateToStep(targetStep) {
    state.projectManagerOpen = false;
    if (!isStepAvailable(targetStep)) {
      StatApi.toast("아직 이동할 수 없는 단계입니다. 앞 단계를 먼저 완료해 주세요.");
      return;
    }
    state.step = targetStep;
    save();
    renderStep().catch((error) => StatApi.toast(error.message));
  }

  function openProjectManager() {
    state.projectManagerOpen = true;
    StatState.setStudentState(state);
    renderProjectManager().catch((error) => StatApi.toast(error.message));
  }

  function closeProjectManager() {
    state.projectManagerOpen = false;
    StatState.setStudentState(state);
    renderCurrentState();
  }

  function projectDisplayTitle(project) {
    return project.custom_topic_question || project.custom_topic_title || project.topic_id || "새 탐구 프로젝트";
  }

  async function renderProjectManager() {
    progress.innerHTML = "";
    stepControls.innerHTML = `
      <button type="button" id="back-to-inquiry">탐구 화면으로 돌아가기</button>
      <span>프로젝트 관리</span>
      <button type="button" id="new-project-from-manager" class="primary">새 프로젝트</button>
    `;
    const projects = await StatApi.request("/api/projects");
    view.innerHTML = `
      <section>
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">프로젝트 관리</p>
            <h2>내 탐구 프로젝트</h2>
          </div>
        </div>
        ${
          projects.length
            ? `<div class="bulk-toolbar">
                <label class="inline-check">
                  <input type="checkbox" id="select-all-managed-projects" />
                  전체 선택
                </label>
                <span class="muted" id="managed-project-selection-count">선택 0건</span>
                <span class="bulk-spacer"></span>
                <button type="button" class="danger" id="delete-selected-projects" disabled>선택 삭제</button>
              </div>`
            : ""
        }
        <div class="project-list">
          ${
            projects.length
              ? projects
                  .map(
                    (project) => `
                      <article class="project-row project-row-selectable">
                        <label class="project-row-check">
                          <input
                            type="checkbox"
                            data-managed-project="${escapeHtml(project.project_id)}"
                            aria-label="${escapeHtml(projectDisplayTitle(project))} 선택"
                          />
                        </label>
                        <div class="project-row-main">
                          <strong>${escapeHtml(projectDisplayTitle(project))}</strong>
                          <p class="muted">${statusLabel(project.status)} · ${
                            project.dataset_ids?.length || (project.dataset_id ? 1 : 0)
                          }개 자료 · ${project.analysis_result_ids?.length || (project.latest_analysis_result_id ? 1 : 0)}개 분석</p>
                        </div>
                        <div class="actions">
                          <button type="button" data-resume-project="${escapeHtml(project.project_id)}">이어하기</button>
                          <button type="button" class="danger" data-delete-project="${escapeHtml(project.project_id)}">삭제</button>
                        </div>
                      </article>
                    `,
                  )
                  .join("")
              : `<p class="muted">아직 저장된 프로젝트가 없습니다.</p>`
          }
        </div>
      </section>
    `;
    document.getElementById("back-to-inquiry").addEventListener("click", closeProjectManager);
    document.getElementById("new-project-from-manager").addEventListener("click", restart);
    attachProjectManagerBulkEvents();
    view.querySelectorAll("[data-resume-project]").forEach((button) => {
      button.addEventListener("click", () => resumeProject(button.dataset.resumeProject).catch((error) => StatApi.toast(error.message)));
    });
    view.querySelectorAll("[data-delete-project]").forEach((button) => {
      button.addEventListener("click", () => deleteProjects([button.dataset.deleteProject]).catch((error) => StatApi.toast(error.message)));
    });
  }

  function selectedManagedProjectIds() {
    return [...view.querySelectorAll("[data-managed-project]:checked")].map((input) => input.dataset.managedProject);
  }

  function updateProjectManagerBulkState() {
    const checkboxes = [...view.querySelectorAll("[data-managed-project]")];
    const checked = checkboxes.filter((input) => input.checked);
    const selectAll = document.getElementById("select-all-managed-projects");
    if (selectAll) {
      selectAll.checked = Boolean(checkboxes.length) && checked.length === checkboxes.length;
      selectAll.indeterminate = checked.length > 0 && checked.length < checkboxes.length;
    }
    const countTarget = document.getElementById("managed-project-selection-count");
    if (countTarget) countTarget.textContent = `선택 ${checked.length}건`;
    const deleteSelected = document.getElementById("delete-selected-projects");
    if (deleteSelected) deleteSelected.disabled = !checked.length;
  }

  function attachProjectManagerBulkEvents() {
    document.getElementById("select-all-managed-projects")?.addEventListener("change", (event) => {
      view.querySelectorAll("[data-managed-project]").forEach((checkbox) => {
        checkbox.checked = event.target.checked;
      });
      updateProjectManagerBulkState();
    });
    view.querySelectorAll("[data-managed-project]").forEach((checkbox) => {
      checkbox.addEventListener("change", updateProjectManagerBulkState);
    });
    document.getElementById("delete-selected-projects")?.addEventListener("click", () => {
      deleteProjects(selectedManagedProjectIds()).catch((error) => StatApi.toast(error.message));
    });
    updateProjectManagerBulkState();
  }

  async function resumeProject(projectId) {
    const project = await StatApi.request(`/api/projects/${projectId}`);
    const isCustomTopic = project.topic_id?.startsWith("custom_");
    const topicPayload = Array.isArray(project.steps)
      ? [...project.steps].reverse().find((step) => step.step_type === "topic_selected")?.payload || {}
      : {};
    let topic = null;
    if (project.topic_id) {
      topic = isCustomTopic
        ? {
            topic_id: project.topic_id,
            title: project.custom_topic_title || project.custom_topic_question,
            question: project.custom_topic_question,
          }
        : await StatApi.request(
            `/api/topics/${project.topic_id}${
              project.school_level ? `?school_level=${encodeURIComponent(project.school_level)}` : ""
            }`,
          );
    }
    const datasetId = project.dataset_id;
    const analyses = await StatApi.request(`/api/projects/${project.project_id}/analyses`);
    const latestAnalysis = analyses[analyses.length - 1] || null;
    const synthesisHistory = await StatApi.request(`/api/projects/${project.project_id}/synthesis`);
    const report = project.report_id ? await StatApi.request(`/api/reports/${project.report_id}`) : null;
    const nextState = {
      ...state,
      projectManagerOpen: false,
      project,
      topic,
      schoolLevel: project.school_level || state.schoolLevel || null,
      startMode: isCustomTopic ? "question" : "example",
      questionDraft: topicPayload.advisor_input || state.questionDraft || "",
      decidedTopicDraft: project.custom_topic_question || topicPayload.decided_topic || state.decidedTopicDraft || "",
      datasetMode: datasetId ? state.datasetMode || "search" : null,
      analysisHistory: analyses,
      analysis: latestAnalysis,
      synthesisHistory,
      synthesisPanel: defaultSynthesisPanel(),
      synthesisDatasetSchemas: {},
      synthesisResult: null,
      synthesisObservations: null,
      report,
      reportLayout: report?.layout || null,
      reportConclusionDraft: undefined,
      hints: null,
      coach: null,
      interpretationDrafts: {},
      interpretationFeedback: {},
      analysisRunOpen: false,
    };
    if (datasetId) {
      const [schema, summaryData, sheet, options, derivedSuggestions] = await Promise.all([
        StatApi.request(`/api/datasets/${datasetId}/schema`),
        StatApi.request(`/api/datasets/${datasetId}/summary`),
        StatApi.request(`/api/datasets/${datasetId}/sheet?limit=100`),
        project.status === "dataset_chosen" || project.status === "analysis_done"
          ? StatApi.request(`/api/projects/${project.project_id}/analysis-options`)
          : Promise.resolve([]),
        project.status === "dataset_chosen" || project.status === "analysis_done"
          ? StatApi.request(`/api/projects/${project.project_id}/derived-variable-suggestions`)
          : Promise.resolve([]),
      ]);
      Object.assign(nextState, {
        dataset: schema,
        datasetSummary: summaryData,
        sheet,
        sheetEdits: {},
        sheetFilters: {},
        analysisRows: { mode: "all", selected: [] },
        customAnalysisFields: {},
        options,
        derivedSuggestions,
      });
    }
    const targetStep = !project.topic_id
      ? STEP.TOPIC
      : report
        ? STEP.REPORT
        : datasetId
          ? STEP.ANALYSIS
          : STEP.DATA;
    state = { ...nextState, step: targetStep };
    save();
    renderStep().catch((error) => StatApi.toast(error.message));
  }

  async function deleteProjects(projectIds) {
    const ids = [...new Set(projectIds)].filter(Boolean);
    if (!ids.length) return;
    const message =
      ids.length === 1
        ? "이 프로젝트와 연결된 보고서/분석 이력을 삭제할까요?"
        : `선택한 프로젝트 ${ids.length}개와 연결된 보고서/분석 이력을 삭제할까요?`;
    if (!window.confirm(message)) return;
    for (const projectId of ids) {
      await StatApi.request(`/api/projects/${projectId}`, { method: "DELETE" });
    }
    if (state.project?.project_id && ids.includes(state.project.project_id)) {
      StatState.clearStudentState();
      state = {
        ...state,
        projectManagerOpen: true,
        project: null,
        topic: null,
        datasets: null,
        dataset: null,
        datasetSummary: null,
        sheet: null,
        sheetEdits: {},
        sheetFilters: {},
        analysisRows: { mode: "all", selected: [] },
        customAnalysisFields: {},
        options: [],
        analysis: null,
        report: null,
      };
    }
    StatApi.toast(`프로젝트 ${ids.length}개를 삭제했습니다.`);
    await renderProjectManager();
  }

  async function ensureDatasets() {
    if (!Array.isArray(state.sharedArtifacts)) {
      try {
        state.sharedArtifacts = await StatApi.request("/api/projects/shared-artifacts");
      } catch {
        state.sharedArtifacts = [];
      }
    }
    if (state.project?.dataset_id && !state.dataset) {
      state.dataset = await StatApi.request(datasetSchemaPath(state.project.dataset_id));
    }
    if (state.project?.dataset_id && !state.datasetMode) {
      state.datasetMode = "search";
    }
    if (Array.isArray(state.datasets)) {
      save();
      return;
    }
    if (!state.topic?.topic_id) return;
    if (state.topic.topic_id.startsWith("custom_")) {
      state.datasets = [];
      save();
      return;
    }
    state.datasets = await StatApi.request(`/api/topics/${state.topic.topic_id}/datasets`);
    save();
  }

  async function ensureAnalysisOptions() {
    if (!state.project?.project_id || !state.dataset?.dataset_id) return;
    const datasetId = state.dataset.dataset_id;
    if (!state.dataset.columns) {
      state.dataset = await StatApi.request(datasetSchemaPath(datasetId));
    }
    if (!state.datasetSummary) {
      state.datasetSummary = await StatApi.request(`/api/datasets/${datasetId}/summary`);
    }
    if (!state.options?.length) {
      state.options = await StatApi.request(`/api/projects/${state.project.project_id}/analysis-options`);
    }
    if (!state.sheet) {
      state.sheet = await StatApi.request(`/api/datasets/${datasetId}/sheet?limit=100`);
      state.sheetEdits = {};
    }
    if (!state.derivedSuggestions) {
      state.derivedSuggestions = await StatApi.request(
        `/api/projects/${state.project.project_id}/derived-variable-suggestions`,
      );
    }
    save();
  }

  async function renderStep() {
    if (state.projectManagerOpen) {
      await renderProjectManager();
      return;
    }
    state.step = nearestAvailableStep(state.step);
    save();
    if (!StatAuth.isSignedIn()) {
      renderLoginWait();
      return;
    }
    if (state.step === 0) {
      if (state.project?.topic_id && state.topic?.topic_id) {
        renderSelectedTopicStage();
      } else if (!schoolLevel()) {
        renderSchoolLevelChoice();
      } else if (state.startMode === "example") {
        await loadTopics();
      } else if (state.startMode === "question") {
        renderQuestionAdvisor();
      } else {
        renderProjectStartChoice();
      }
    } else if (state.step === STEP.DATA) {
      await ensureDatasets();
      renderDatasets(state.datasets || []);
    } else if (state.step === STEP.ANALYSIS) {
      await ensureAnalysisOptions();
      renderAnalysisWorkspace();
    } else if (state.step === STEP.REPORT) {
      renderReportBuilder();
    } else if (state.step === STEP.FEEDBACK) {
      renderSubmitted();
    }
  }

  const SCHOOL_LEVELS = {
    middle: {
      label: "중학교",
      summary: "도수분포와 대푯값, 그래프 읽기 중심으로 예시와 조언을 맞춥니다.",
      detail: "도수·상대도수·평균·중앙값·최빈값과 기본 그래프 해석을 중심으로 안내합니다.",
    },
    high: {
      label: "고등학교",
      summary: "상관관계와 회귀의 직관적 해석까지 넓혀서 예시와 조언을 맞춥니다.",
      detail: "산포도·상관계수·추세 해석까지 다루되 가설검정이나 신뢰구간은 요구하지 않습니다.",
    },
  };

  function schoolLevel() {
    const level = state.project?.school_level || state.schoolLevel;
    return SCHOOL_LEVELS[level] ? level : null;
  }

  function schoolLevelLabel(level = schoolLevel()) {
    return SCHOOL_LEVELS[level]?.label || "미선택";
  }

  function requireSchoolLevel() {
    const level = schoolLevel();
    if (!level) {
      StatApi.toast("먼저 학교급을 선택해 주세요.");
      state = { ...state, step: STEP.TOPIC };
      save();
      renderSchoolLevelChoice();
      return null;
    }
    return level;
  }

  function renderSchoolLevelBar() {
    const level = schoolLevel();
    if (!level) return "";
    const locked = Boolean(state.project?.project_id);
    return `
      <div class="actions school-level-bar">
        <span class="chip school-level-chip">학교급 · ${escapeHtml(schoolLevelLabel(level))}</span>
        <span class="muted">${escapeHtml(SCHOOL_LEVELS[level].summary)}</span>
        ${
          locked
            ? `<span class="muted">이 프로젝트에 저장된 학교급입니다.</span>`
            : `<button type="button" id="change-school-level">학교급 변경</button>`
        }
      </div>
    `;
  }

  function attachSchoolLevelBarEvents() {
    document.getElementById("change-school-level")?.addEventListener("click", () => {
      renderSchoolLevelChoice();
    });
  }

  function renderSchoolLevelChoice() {
    const current = schoolLevel();
    view.innerHTML = `
      <div>
        <p class="eyebrow">1단계 시작</p>
        <h2>어떤 학교급에서 탐구하나요?</h2>
        <p class="muted">선택한 학교급에 맞추어 예시 주제, AI 조언, 분석 방법 추천과 해석 안내가 달라집니다.</p>
      </div>
      <div class="card-grid start-choice-grid">
        ${Object.entries(SCHOOL_LEVELS)
          .map(
            ([value, info]) => `
              <article class="topic-card start-choice-card${current === value ? " selected" : ""}">
                <p class="eyebrow">학교급</p>
                <h3>${escapeHtml(info.label)}</h3>
                <p>${escapeHtml(info.detail)}</p>
                <button type="button" class="primary" data-school-level="${value}">
                  ${current === value ? "계속하기" : "선택"}
                </button>
              </article>
            `,
          )
          .join("")}
      </div>
    `;
    view.querySelectorAll("[data-school-level]").forEach((button) => {
      button.addEventListener("click", () => selectSchoolLevel(button.dataset.schoolLevel));
    });
  }

  function selectSchoolLevel(level) {
    if (!SCHOOL_LEVELS[level]) return;
    const changed = state.schoolLevel !== level;
    state = {
      ...state,
      schoolLevel: level,
      ...(changed ? { datasets: null, questionAdvice: null, coach: null } : {}),
    };
    save();
    renderStep().catch((error) => StatApi.toast(error.message));
  }

  function renderProjectStartChoice() {
    view.innerHTML = `
      ${renderSchoolLevelBar()}
      <div class="card-grid start-choice-grid">
        <article class="topic-card start-choice-card">
          <p class="eyebrow">직접 시작</p>
          <h3>탐구 질문 입력</h3>
          <p>궁금한 주제나 현상을 자유롭게 적고, AI에게 ${escapeHtml(schoolLevelLabel())} 통계 탐구 질문 후보를 받아봅니다.</p>
          <button type="button" class="primary" id="choose-question-input">선택</button>
        </article>
        <article class="topic-card start-choice-card">
          <p class="eyebrow">예시에서 시작</p>
          <h3>예시 주제 탐구</h3>
          <p>${escapeHtml(schoolLevelLabel())} 수준에 맞는 탐구 주제 카드 중 하나를 고르고 자료 선택과 분석 단계로 이어갑니다.</p>
          <button type="button" class="primary" id="choose-example-topic">선택</button>
        </article>
      </div>
    `;
    attachSchoolLevelBarEvents();
    document.getElementById("choose-question-input").addEventListener("click", () => {
      state = { ...state, startMode: "question" };
      save();
      renderQuestionAdvisor();
    });
    document.getElementById("choose-example-topic").addEventListener("click", () => {
      state = { ...state, startMode: "example", questionAdvice: null, questionDraft: "" };
      save();
      loadTopics().catch((error) => StatApi.toast(error.message));
    });
  }

  function renderQuestionAdvice(advice) {
    const candidates = Array.isArray(advice?.candidate_questions) ? advice.candidate_questions : [];
    const adviceMode = advice?.advice_mode || advice?.metadata?.advice_mode || state.questionAdviceMode || "direct_survey";
    const isBigData = adviceMode === "big_data";
    return `
      <section class="question-advice">
        <div>
          <p class="eyebrow">에이전트 조언</p>
          <h2>${isBigData ? "빅데이터 활용 탐구 계획" : "통계 탐구 질문 후보"}</h2>
          ${
            advice?.student_input_summary
              ? `<p class="muted">${escapeHtml(advice.student_input_summary)}</p>`
              : ""
          }
          ${advice?.overall_advice ? `<p>${escapeHtml(advice.overall_advice)}</p>` : ""}
        </div>
        ${isBigData ? renderBigDataSourcePlan(advice?.data_source_plan) : ""}
        <div class="question-candidate-list">
          ${candidates
            .map((candidate) => {
              const data = candidate.data_to_collect || {};
              const variables = Array.isArray(data.variables) ? data.variables : [];
              return `
                <article class="candidate-question-card">
                  <div class="meta-row"><span class="chip">${escapeHtml(candidate.type || "탐구")}</span></div>
                  <h3>${escapeHtml(candidate.title || "탐구 질문 후보")}</h3>
                  <p><strong>${escapeHtml(candidate.question || "")}</strong></p>
                  <p>${escapeHtml(candidate.why_it_fits_middle_school_statistics || "")}</p>
                  <dl class="advice-detail-list">
                    <dt>조사 대상</dt>
                    <dd>${escapeHtml(data.target || "-")}</dd>
                    <dt>측정 변수</dt>
                    <dd>${variables.map((item) => escapeHtml(item)).join(", ") || "-"}</dd>
                    <dt>수집 방법</dt>
                    <dd>${escapeHtml(data.collection_method || "-")}</dd>
                    <dt>표본 힌트</dt>
                    <dd>${escapeHtml(data.sample_size_hint || "-")}</dd>
                  </dl>
                  <h4>추천 분석</h4>
                  ${renderAdviceList(candidate.recommended_analysis)}
                  <h4>예상 가능한 결과</h4>
                  ${renderPossibleResults(candidate.possible_results)}
                  <h4>주의할 점</h4>
                  ${renderAdviceList(candidate.cautions)}
                  ${
                    candidate.good_choice_when
                      ? `<p class="muted">${escapeHtml(candidate.good_choice_when)}</p>`
                      : ""
                  }
                  ${candidate.question ? `<div class="actions"><button type="button" class="select-candidate-question" data-question="${escapeHtml(candidate.question)}">이 질문 선택 →</button></div>` : ""}
                </article>
              `;
            })
            .join("")}
        </div>
        <div class="split compact advice-followup">
          <section>
            <h3>다듬는 방법</h3>
            ${renderAdviceList(advice?.refinement_tips)}
          </section>
          <section>
            <h3>선택 기준</h3>
            ${renderAdviceList(advice?.student_decision_guide)}
          </section>
        </div>
        <section class="advice-next">
          <h3>다음에 생각해 볼 질문</h3>
          ${renderAdviceList(advice?.next_questions_for_student)}
        </section>
      </section>
    `;
  }

  function renderBigDataSourcePlan(plan = {}) {
    const sources = Array.isArray(plan?.recommended_sources) ? plan.recommended_sources : [];
    const candidates = Array.isArray(plan?.candidate_datasets) ? plan.candidate_datasets : [];
    const kosis = Array.isArray(plan?.kosis_recommendations) ? plan.kosis_recommendations : [];
    const nextActions = Array.isArray(plan?.next_data_actions) ? plan.next_data_actions : [];
    const limitations = Array.isArray(plan?.limitations) ? plan.limitations : [];
    return `
      <section class="big-data-plan">
        <div>
          <h3>실제 자료 후보 근거</h3>
          <p class="muted">공식 통계 API와 검색 가능한 자료 후보를 먼저 확인한 뒤 질문을 다듬은 결과입니다.</p>
        </div>
        ${
          sources.length
            ? `<div class="source-card-grid">
                ${sources
                  .map(
                    (source) => `
                      <article class="source-card">
                        <div class="meta-row">
                          <span class="chip">${escapeHtml(source.source_id || "source")}</span>
                          <span class="chip">${escapeHtml(source.access_status || "확인 필요")}</span>
                        </div>
                        <strong>${escapeHtml(source.display_name || "자료 소스")}</strong>
                        <p>${escapeHtml(source.why_suitable || "탐구 질문과 관련된 공개 통계 후보입니다.")}</p>
                      </article>
                    `,
                  )
                  .join("")}
              </div>`
            : `<p class="muted">추천 자료 소스를 충분히 찾지 못했습니다. 검색어를 더 구체화해 보세요.</p>`
        }
        ${
          candidates.length || kosis.length
            ? `<div class="split compact">
                <section>
                  <h3>API/공개자료 후보</h3>
                  ${renderDatasetEvidenceList(candidates)}
                </section>
                <section>
                  <h3>KOSIS 후보</h3>
                  ${renderKosisEvidenceList(kosis)}
                </section>
              </div>`
            : ""
        }
        <div class="split compact">
          <section>
            <h3>다음 자료 확인 행동</h3>
            ${renderAdviceList(nextActions)}
          </section>
          <section>
            <h3>해석 주의점</h3>
            ${renderAdviceList(limitations)}
          </section>
        </div>
      </section>
    `;
  }

  function renderDatasetEvidenceList(candidates = []) {
    if (!candidates.length) return `<p class="muted">다른 API 후보를 먼저 확인해 보세요.</p>`;
    return `
      <ul class="evidence-list">
        ${candidates
          .map(
            (candidate) => `
              <li>
                <strong>${escapeHtml(candidate.dataset_title || candidate.dataset_id || "자료 후보")}</strong>
                <span>${escapeHtml([candidate.source_id, candidate.unit, candidate.access_status].filter(Boolean).join(" · ") || "세부 정보 확인 필요")}</span>
              </li>
            `,
          )
          .join("")}
      </ul>
    `;
  }

  function renderKosisEvidenceList(items = []) {
    if (!items.length) return `<p class="muted">KOSIS 후보가 없거나 아직 검색할 수 없습니다.</p>`;
    return `
      <ul class="evidence-list">
        ${items
          .map(
            (item) => `
              <li>
                <strong>${escapeHtml(item.dataset_title || "KOSIS 자료 후보")}</strong>
                <span>${escapeHtml([item.source_agency, item.period_range, item.unit].filter(Boolean).join(" · ") || "세부 정보 확인 필요")}</span>
                ${
                  item.relation_to_research_question
                    ? `<p>${escapeHtml(item.relation_to_research_question)}</p>`
                    : ""
                }
              </li>
            `,
          )
          .join("")}
      </ul>
    `;
  }

  function renderDecisionTopicForm() {
    if (!state.questionAdvice) return "";
    const projectCreated = Boolean(state.project?.project_id && state.topic?.topic_id);
    return `
      <form id="decision-topic-form" class="decision-topic-form">
        <div>
          <p class="eyebrow">탐구 결정</p>
          <h2>결정한 주제 입력</h2>
          <p class="muted">AI 조언을 참고해 실제로 탐구할 통계 질문을 한 문장으로 정리해 주세요.</p>
        </div>
        <textarea
          id="decided-topic-input"
          maxlength="300"
          placeholder="예: 급식 만족도와 잔반량 사이에는 어떤 관계가 있을까?"
          ${projectCreated ? "disabled" : ""}
        >${escapeHtml(state.decidedTopicDraft || state.topic?.question || "")}</textarea>
        <div class="actions">
          ${
            projectCreated
              ? `<button type="button" class="primary" id="go-dataset-step">자료 단계로 이동</button>`
              : `<button type="submit" class="primary">이 주제로 자료 단계 시작</button>`
          }
        </div>
      </form>
    `;
  }

  function renderQuestionAdvisor() {
    view.innerHTML = `
      ${renderSchoolLevelBar()}
      <form id="question-advisor-form" class="question-advisor-form">
        <div>
          <p class="eyebrow">탐구 질문 입력</p>
          <h2>탐구하고 싶은 주제, 현상, 질문에 대해 자유롭게 설명해 주세요.</h2>
        </div>
        <textarea
          id="question-advisor-input"
          maxlength="4000"
          placeholder="예: 학교 급식 만족도와 잔반량이 어떤 관계인지 궁금해요."
        >${escapeHtml(state.questionDraft || "")}</textarea>
        <div class="actions">
          <button type="button" id="back-start-choice">시작 방식 다시 선택</button>
        </div>
        <div class="actions advice-mode-actions">
          <button type="submit" class="primary" data-advice-mode="direct_survey">직접 자료 조사 탐구 조언받기</button>
          <button type="submit" data-advice-mode="big_data">빅데이터 활용 계획 조언받기</button>
        </div>
      </form>
      ${state.questionAdvice ? renderQuestionAdvice(state.questionAdvice) : ""}
      ${renderDecisionTopicForm()}
      ${
        state.questionAdvice
          ? `<div class="actions">
              <button type="button" id="reset-question-advice">다시 입력</button>
              <button type="button" class="primary" id="continue-example-topic">예시 주제 탐구로 계속</button>
            </div>`
          : ""
      }
    `;
    attachSchoolLevelBarEvents();
    const input = document.getElementById("question-advisor-input");
    input.addEventListener("input", (event) => {
      state.questionDraft = event.target.value;
      StatState.setStudentState(state);
    });
    document.getElementById("question-advisor-form").addEventListener("submit", requestQuestionAdvice);
    document.getElementById("back-start-choice").addEventListener("click", () => {
      state = { ...state, startMode: null };
      save();
      renderProjectStartChoice();
    });
    const resetButton = document.getElementById("reset-question-advice");
    if (resetButton) {
      resetButton.addEventListener("click", () => {
        state = { ...state, questionAdvice: null };
        save();
        renderQuestionAdvisor();
      });
    }
    const continueButton = document.getElementById("continue-example-topic");
    if (continueButton) {
      continueButton.addEventListener("click", () => {
        state = { ...state, startMode: "example" };
        save();
        loadTopics().catch((error) => StatApi.toast(error.message));
      });
    }
    const decisionForm = document.getElementById("decision-topic-form");
    if (decisionForm) {
      decisionForm.addEventListener("submit", submitDecidedTopic);
    }
    const decidedInput = document.getElementById("decided-topic-input");
    if (decidedInput && !decidedInput.disabled) {
      decidedInput.addEventListener("input", (event) => {
        state.decidedTopicDraft = event.target.value;
        StatState.setStudentState(state);
      });
    }
    view.querySelectorAll(".select-candidate-question").forEach((btn) => {
      btn.addEventListener("click", () => {
        const question = btn.dataset.question || "";
        state.decidedTopicDraft = question;
        save();
        const target = document.getElementById("decided-topic-input");
        if (target && !target.disabled) {
          target.value = question;
          target.focus();
          target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    });
    const goDataset = document.getElementById("go-dataset-step");
    if (goDataset) {
      goDataset.addEventListener("click", () => navigateToStep(STEP.DATA));
    }
  }

  async function requestQuestionAdvice(event) {
    event.preventDefault();
    const input = document.getElementById("question-advisor-input");
    const studentInput = input.value.trim();
    const adviceMode = event.submitter?.dataset?.adviceMode || state.questionAdviceMode || "direct_survey";
    if (!studentInput) {
      StatApi.toast("탐구하고 싶은 내용을 먼저 입력해 주세요.");
      input.focus();
      return;
    }
    const level = requireSchoolLevel();
    if (!level) return;
    state = { ...state, questionDraft: studentInput, questionAdviceMode: adviceMode, questionAdvice: null };
    save();
    setLoading(
      adviceMode === "big_data"
        ? "AI가 공식 통계 API 후보를 확인하고 빅데이터 탐구 계획을 정리하는 중입니다."
        : "AI가 통계 탐구 질문 후보를 정리하는 중입니다.",
      {
        label: "학생 입력",
        text: studentInput,
        items: [
          {
            label: "조언 방식",
            value: adviceMode === "big_data" ? "빅데이터 활용 계획 조언" : "직접 자료 조사 탐구 조언",
          },
          { label: "학교급", value: schoolLevelLabel(level) },
        ],
      },
    );
    try {
      const advice = await StatApi.request("/api/projects/question-advice", {
        method: "POST",
        body: JSON.stringify({
          student_input: studentInput,
          advice_mode: adviceMode,
          school_level: level,
        }),
      });
      state = { ...state, questionAdvice: advice, questionAdviceMode: advice.advice_mode || adviceMode, coach: null };
      save();
      renderQuestionAdvisor();
    } catch (error) {
      StatApi.toast(error.message);
      renderQuestionAdvisor();
    }
  }

  async function submitDecidedTopic(event) {
    event.preventDefault();
    const input = document.getElementById("decided-topic-input");
    const decidedTopic = input.value.trim();
    if (!decidedTopic) {
      StatApi.toast("결정한 탐구 주제를 입력해 주세요.");
      input.focus();
      return;
    }
    const level = requireSchoolLevel();
    if (!level) return;
    setLoading("결정한 주제로 프로젝트를 시작하는 중입니다.", {
      label: "결정한 주제",
      text: decidedTopic,
      items: [{ label: "학교급", value: schoolLevelLabel(level) }],
    });
    try {
      const project = await StatApi.request("/api/projects/custom-topic", {
        method: "POST",
        body: JSON.stringify({
          decided_topic: decidedTopic,
          advisor_input: state.questionDraft || "",
          school_level: level,
        }),
      });
      state = {
        ...state,
        step: STEP.DATA,
        startMode: "question",
        project,
        topic: {
          topic_id: project.topic_id,
          title: project.custom_topic_title || "직접 입력 주제",
          question: project.custom_topic_question || decidedTopic,
          category: "직접 입력",
          level,
          recommended_charts: [],
        },
        schoolLevel: level,
        datasets: [],
        sharedArtifacts: null,
        dataset: null,
        datasetMode: null,
        datasetSummary: null,
        sheet: null,
        sheetEdits: {},
        sheetFilters: {},
        analysisRows: { mode: "all", selected: [] },
        customAnalysisFields: {},
        derivedSuggestions: null,
        uploadPlan: null,
        kosisPlan: null,
        statApiPlan: null,
        kosisQuestionDraft: decidedTopic,
        kosisSearchDraft: "",
        statApiQuestionDraft: decidedTopic,
        options: [],
        analysis: null,
        hints: null,
        report: null,
        coach: null,
        decidedTopicDraft: decidedTopic,
        interpretationDrafts: {},
        interpretationFeedback: {},
      };
      save();
      await ensureDatasets();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderQuestionAdvisor();
    }
  }

  async function loadTopics() {
    const level = requireSchoolLevel();
    if (!level) return;
    state.step = 0;
    state.startMode = "example";
    save();
    setLoading("주제를 불러오는 중입니다.", {
      label: "학교급",
      text: schoolLevelLabel(level),
    });
    const topics = await StatApi.request(`/api/topics?school_level=${encodeURIComponent(level)}`);
    view.innerHTML = `
      ${renderSchoolLevelBar()}
      <div class="actions topic-start-actions">
        <button type="button" id="back-to-start-choice">시작 방식 다시 선택</button>
        <button type="button" class="primary" id="switch-to-question-input">탐구 질문 입력</button>
      </div>
      <div class="card-grid">
        ${topics
          .map(
            (topic) => `
              <article class="topic-card">
                <h3>${escapeHtml(topic.title)}</h3>
                <p>${escapeHtml(topic.question)}</p>
                ${
                  topic.guidance
                    ? `<p class="muted topic-guidance">${escapeHtml(topic.guidance)}</p>`
                    : ""
                }
                <div class="meta-row">
                  <span class="chip">${escapeHtml(topic.category)}</span>
                  ${topic.concepts.map((concept) => `<span class="chip">${escapeHtml(concept)}</span>`).join("")}
                </div>
                <button class="primary" data-topic="${topic.topic_id}" data-topic-title="${escapeHtml(topic.title)}">선택</button>
              </article>
            `,
          )
          .join("")}
      </div>
    `;
    attachSchoolLevelBarEvents();
    document.getElementById("back-to-start-choice").addEventListener("click", () => {
      state = { ...state, startMode: null };
      save();
      renderProjectStartChoice();
    });
    document.getElementById("switch-to-question-input").addEventListener("click", () => {
      state = { ...state, startMode: "question" };
      save();
      renderQuestionAdvisor();
    });
    view.querySelectorAll("[data-topic]").forEach((button) => {
      button.addEventListener("click", () => selectTopic(button.dataset.topic, button.dataset.topicTitle));
    });
  }

  async function selectTopic(topicId, topicTitle = "") {
    const level = requireSchoolLevel();
    if (!level) return;
    setLoading("프로젝트를 만들고 주제를 저장하는 중입니다.", {
      label: "선택한 예시 주제",
      text: topicTitle || topicId,
      items: [{ label: "학교급", value: schoolLevelLabel(level) }],
    });
    const project = await StatApi.request("/api/projects", {
      method: "POST",
      body: JSON.stringify({ school_level: level }),
    });
    const selected = await StatApi.request(`/api/projects/${project.project_id}/select-topic`, {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId }),
    });
    const topic = await StatApi.request(
      `/api/topics/${topicId}?school_level=${encodeURIComponent(level)}`,
    );
    const datasets = await StatApi.request(`/api/topics/${topicId}/datasets`);
    state = {
      ...state,
      step: STEP.DATA,
      startMode: "example",
      schoolLevel: level,
      project: selected,
      topic,
      datasets,
      sharedArtifacts: null,
      dataset: null,
      datasetMode: null,
      datasetSummary: null,
      sheet: null,
      sheetEdits: {},
      sheetFilters: {},
      sheetView: { columnWidth: 150, columnWidths: {}, fontSize: 14 },
      analysisRows: { mode: "all", selected: [] },
      customAnalysisFields: {},
      derivedSuggestions: null,
      uploadPlan: null,
      kosisPlan: null,
      statApiPlan: null,
      kosisQuestionDraft: topic.question,
      kosisSearchDraft: "",
      statApiQuestionDraft: topic.question,
      options: [],
      analysis: null,
      hints: null,
      report: null,
      coach: null,
      interpretationDrafts: {},
      interpretationFeedback: {},
    };
    save();
    await ensureDatasets();
    renderDatasets(state.datasets || datasets);
  }

  function renderCsvUploadMethod() {
    if (state.uploadPlan?.dataset) {
      const dataset = state.uploadPlan.dataset;
      const plan = state.uploadPlan.processing_plan || {};
      const profile = plan.data_profile || {};
      const analyses = plan.recommended_analyses || dataset.recommended_analyses || [];
      return `
        <section class="upload-panel ready dataset-method-card">
          <div>
            <p class="eyebrow">AI 자료 처리 제안</p>
            <h2>${escapeHtml(dataset.name)}</h2>
            <p class="muted">${escapeHtml(plan.message || "자료의 분석 후보를 만들었습니다.")}</p>
          </div>
          <div class="profile-grid">
            <div><strong>${formatNumber(profile.row_count || 0, false)}</strong><span>행</span></div>
            <div><strong>${formatNumber(profile.column_count || 0, false)}</strong><span>컬럼</span></div>
            <div><strong>${formatNumber(profile.numeric_column_count || 0, false)}</strong><span>수치형</span></div>
            <div><strong>${formatNumber(profile.missing_count || 0, false)}</strong><span>결측</span></div>
          </div>
          <div class="split compact">
            <section>
              <h3>처리 점검</h3>
              <ul class="hint-list">
                ${(plan.cleaning_suggestions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
            </section>
            <section>
              <h3>탐구 연결</h3>
              <ul class="hint-list">
                ${analyses
                  .slice(0, 3)
                  .map((item) => `<li><strong>${escapeHtml(item.label)}</strong> · ${escapeHtml(item.description)}</li>`)
                  .join("")}
              </ul>
            </section>
          </div>
          <div class="actions">
            <button type="button" id="reset-upload">다른 자료 선택</button>
            <button type="button" class="primary" id="use-uploaded-dataset">이 자료로 이어가기</button>
          </div>
          <p class="muted">${escapeHtml(plan.guardrail || "")}</p>
        </section>
      `;
    }
    return `
      <form id="csv-upload-form" class="upload-panel dataset-method-card">
        <div>
          <p class="eyebrow">내 자료 가져오기</p>
          <h2>CSV 업로드</h2>
          <p class="muted">직접 조사했거나 내려받은 표 자료를 올리면 AI가 분석에 쓸 항목과 전처리 방향을 점검합니다.</p>
        </div>
        <div class="upload-controls">
          <input id="csv-file" name="file" type="file" accept=".csv,text/csv" />
          <input id="csv-name" name="dataset_name" type="text" maxlength="80" placeholder="자료 이름" />
          <button type="submit" class="primary">AI 처리 제안 받기</button>
        </div>
      </form>
    `;
  }

  function renderDatasetUseMethods(importedCount) {
    const isWizardActive = typeof mergeWizardState !== "undefined" && mergeWizardState && mergeWizardState.step > 0;
    const canMerge = importedCount >= 1;
    return `
      <section class="data-source-choice">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">자료 활용 방법</p>
            <h2>공식 통계 자료를 추천받거나 직접 검색하세요</h2>
          </div>
        </div>
        <div class="data-import-grid" style="margin-top: 1rem;">
          <article class="upload-panel dataset-method-card">
            <div>
              <p class="eyebrow">AI 추천 자료 사용</p>
              <h2>탐구 질문에 맞는 공식 통계 후보 받기</h2>
              <p class="muted">AI가 탐구 질문을 검색 전략으로 바꾸고, 실제로 확인할 수 있는 공식 통계 후보와 분석 연결점을 제안합니다.</p>
            </div>
            <div class="meta-row">
              <span class="chip">AI 추천</span>
              <span class="chip">실제 자료 확인</span>
            </div>
            <div class="actions">
              <button type="button" class="primary" data-dataset-mode="suggested">AI 추천 자료 보기</button>
            </div>
          </article>
          <form id="official-stat-search-form" class="upload-panel dataset-method-card">
            <div>
              <p class="eyebrow">직접 검색</p>
              <h2>공식 통계 자료 찾기</h2>
              <p class="muted">검색어를 입력하면 연결된 공식 통계 출처를 함께 확인하고, 탐구 질문과의 관련성을 정리합니다.</p>
            </div>
            <div class="kosis-search-controls">
              <textarea id="official-search-question" maxlength="1000" placeholder="탐구 질문">${escapeHtml(
                state.kosisQuestionDraft || state.statApiQuestionDraft || state.topic?.question || "",
              )}</textarea>
              <input
                id="official-search-keyword"
                maxlength="120"
                placeholder="검색어 예: 청소년 스마트폰, 사교육비, 폭염일수"
                value="${escapeHtml(state.kosisSearchDraft || "")}"
              />
              <button type="submit" class="primary">검색어로 자료 찾기</button>
            </div>
          </form>
        </div>
        <details class="secondary-data-methods" ${isWizardActive ? "open" : ""}>
          <summary style="cursor: pointer; margin-top: 1rem; color: var(--text-muted);">다른 방법 (CSV 업로드, 자료 결합)</summary>
          <div class="data-import-grid" style="margin-top: 0.75rem;">
            ${renderCsvUploadMethod()}
            <article class="upload-panel dataset-method-card ${canMerge ? "" : "is-disabled"}">
              <div>
                <p class="eyebrow">자료 결합</p>
                <h2>다중 자료 결합 (Merge)</h2>
                <p class="muted">${canMerge ? "두 개 이상의 자료를 지역·시점을 함께 기준으로 결합하여 새로운 자료를 만듭니다." : "자료를 먼저 하나 이상 가져온 뒤 결합 기능을 사용할 수 있습니다."}</p>
              </div>
              <div class="meta-row">
                <span class="chip">다변량 분석</span>
                <span class="chip">지도 시각화 지원</span>
              </div>
              <div class="actions">
                <button type="button" class="primary" data-dataset-mode="merge" ${canMerge ? "" : "disabled"}>자료 결합 도우미</button>
              </div>
            </article>
          </div>
        </details>
        <p class="muted" style="margin-top: 1rem;">가져온 자료 ${formatNumber(importedCount, false)}개가 이 프로젝트에 연결되어 있습니다.</p>
      </section>
    `;
  }

  function renderDatasetCard(dataset) {
    const isSelected = selectedDatasetId() === dataset.dataset_id;
    return `
      <article class="dataset-card ${isSelected ? "is-selected" : ""}">
        <h3>${escapeHtml(dataset.name)}</h3>
        <p>${escapeHtml(dataset.description)}</p>
        <p class="muted">${escapeHtml(dataset.source_note)}</p>
        <div class="meta-row">
          ${isSelected ? `<span class="chip selected-chip">선택됨</span>` : ""}
          <span class="chip">${escapeHtml(dataset.time_range)}</span>
          <span class="chip">${escapeHtml(dataset.geographic_unit || "단위 없음")}</span>
        </div>
        <button class="primary" data-dataset="${escapeHtml(dataset.dataset_id)}">${isSelected ? "다시 선택" : "선택"}</button>
      </article>
    `;
  }

  function renderExampleDatasetSection(exampleDatasets) {
    if (state.startMode !== "example") return "";
    if (!Array.isArray(exampleDatasets) || !exampleDatasets.length) return "";
    const synthesisHint =
      exampleDatasets.length >= 2
        ? " 두 자료를 모두 선택해 두면 분석 단계에서 종합 비교까지 해 볼 수 있습니다."
        : "";
    return `
      <section class="dataset-section example-dataset-section">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">예시 자료</p>
            <h2>예시 자료 사용하기</h2>
            <p class="muted">
              선택한 주제에 맞춰 미리 준비한 공식 통계입니다. 검색이나 업로드 없이 바로 분석을 시작할 수 있습니다.${escapeHtml(
                synthesisHint,
              )}
              다른 자료를 쓰고 싶으면 아래에서 직접 찾거나 올릴 수 있습니다.
            </p>
          </div>
        </div>
        <div class="card-grid">${exampleDatasets.map(renderDatasetCard).join("")}</div>
      </section>
    `;
  }

  function renderDatasetModeSwitcher(mode) {
    return `
      <div class="dataset-mode-bar">
        <button type="button" class="${mode === "suggested" ? "primary" : ""}" data-dataset-mode="suggested">AI 추천 자료</button>
        <button type="button" class="${mode === "search" ? "primary" : ""}" data-dataset-mode="search">
          직접 검색/업로드
        </button>
      </div>
    `;
  }

  function attachDatasetModeEvents() {
    view.querySelectorAll("[data-dataset-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        const nextMode = button.dataset.datasetMode;
        state = { ...state, datasetMode: nextMode };
        save();
        if (nextMode === "suggested") {
          loadSuggestedKosisDatasets();
        } else {
          renderDatasets(state.datasets || []);
        }
      });
    });
  }

  function isCurrentKosisPlan(plan = state.kosisPlan) {
    if (!plan || !state.topic?.topic_id) return false;
    return plan.metadata?.topic_id === state.topic.topic_id;
  }

  function currentResearchQuestion() {
    return (state.kosisQuestionDraft || state.topic?.question || state.topic?.title || "").trim();
  }

  function isDatasetAlreadyImported(datasetTitle) {
    const name = (datasetTitle || "").trim();
    if (!name) return false;
    return (state.datasets || []).some((ds) => ds.name === name);
  }

  function renderKosisRecommendations() {
    const plan = state.kosisPlan;
    if (!plan) return "";
    const recommendations = plan.recommendations || {};
    const datasets = Array.isArray(recommendations.recommended_datasets)
      ? recommendations.recommended_datasets
      : [];
    const fallback = recommendations.fallback_if_no_good_kosis_data || {};
    if (!datasets.length) {
      return `
        <section class="empty-dataset-state">
          <h2>자료 후보를 찾지 못했습니다</h2>
          <p class="muted">${escapeHtml(
            fallback.message || "검색어를 바꾸거나 CSV 업로드를 이용해 주세요.",
          )}</p>
        </section>
      `;
    }
    const isStudentSearch = plan.metadata?.suggestion_mode === "student_keyword";
    return `
      <section class="kosis-results">
        <div>
          <p class="eyebrow">공식 통계 자료 후보</p>
          <h2>${isStudentSearch ? "검색어로 찾은 실제 자료" : "AI가 추천한 실제 자료"}</h2>
          ${
            plan.metadata?.student_search_keyword || plan.search_plan?.student_search_keyword
              ? `<p class="muted">검색어: ${escapeHtml(
                  plan.metadata?.student_search_keyword || plan.search_plan?.student_search_keyword,
                )}</p>`
              : ""
          }
          ${
            recommendations.data_need_summary?.comparison_or_analysis_goal
              ? `<p class="muted">${escapeHtml(recommendations.data_need_summary.comparison_or_analysis_goal)}</p>`
              : ""
          }
        </div>
        <div class="question-candidate-list">
          ${datasets
            .map(
              (dataset, index) => `
                <article class="candidate-question-card kosis-candidate-card">
                  <div class="meta-row">
                    <span class="chip">${escapeHtml(dataset.source_agency || dataset.org_name || "KOSIS")}</span>
                    <span class="chip">${escapeHtml(dataset.period_range || "기간 확인 필요")}</span>
                    <span class="chip">${escapeHtml(dataset.unit || "단위 확인 필요")}</span>
                  </div>
                  <h3>${escapeHtml(dataset.dataset_title || dataset.tbl_name || "공식 통계 자료 후보")}</h3>
                  <p>${escapeHtml(dataset.student_friendly_summary || dataset.why_recommended || "")}</p>
                  ${
                    dataset.relation_to_research_question
                      ? `<p class="muted">${escapeHtml(dataset.relation_to_research_question)}</p>`
                      : ""
                  }
                  <dl class="advice-detail-list">
                    <dt>통계표</dt>
                    <dd>${escapeHtml(dataset.tbl_id || "-")} · ${escapeHtml(dataset.tbl_name || "-")}</dd>
                    <dt>분류</dt>
                    <dd>${escapeHtml((dataset.available_dimensions || []).join(", ") || "확인 필요")}</dd>
                    <dt>항목</dt>
                    <dd>${escapeHtml((dataset.available_items || []).join(", ") || "확인 필요")}</dd>
                  </dl>
                  <h4>가능한 분석</h4>
                  ${renderAdviceList(dataset.usable_analysis)}
                  <h4>주의할 점</h4>
                  ${renderAdviceList([].concat(dataset.limitations || [], dataset.cautions || []))}
                  <div class="actions">
                    ${
                      dataset.table_url
                        ? `<a class="button-link" href="${escapeHtml(dataset.table_url)}" target="_blank" rel="noreferrer">원문에서 보기</a>`
                        : ""
                    }
                    ${
                      isDatasetAlreadyImported(dataset.dataset_title || dataset.tbl_name || "공식 통계 자료 후보")
                        ? `<button type="button" class="secondary" disabled>이미 가져온 자료</button>`
                        : `<button type="button" class="primary" data-kosis-index="${index}">이 자료 가져오기</button>`
                    }
                  </div>
                </article>
              `,
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function statAccessLabel(status) {
    const labels = {
      AUTO_SUPPORTED: "자동 수집 가능",
      SUPPORTED_BUT_KEY_MISSING: "인증키 설정 필요",
      MANUAL_CSV_AVAILABLE: "직접 다운로드 가능",
      FOUND_BUT_UNSUPPORTED: "현재 자동 수집 미지원",
      API_ONLY_UNSUPPORTED: "관리자 연동 필요",
      NO_GOOD_PUBLIC_DATA: "공개자료 부족",
    };
    return labels[status] || status || "상태 확인 필요";
  }

  function statSourceLabel(sourceId) {
    const labels = {
      public_data_catalog: "공공데이터포털",
      ecos: "한국은행 ECOS",
      index_nuri: "지표누리",
      sgis: "SGIS",
      kma_asos_hourly: "기상청 ASOS",
      kma_asos_daily: "기상청 ASOS",
      airkorea: "에어코리아",
      neis: "NEIS",
      schoolinfo: "학교알리미",
      world_bank: "World Bank",
      oecd: "OECD",
    };
    return labels[sourceId] || sourceId;
  }

  function renderStatApiCandidates() {
    const plan = state.statApiPlan;
    if (!plan) return "";
    const candidates = Array.isArray(plan.candidates) ? plan.candidates : [];
    const searchedSources = Array.isArray(plan.metadata?.searched_source_ids)
      ? plan.metadata.searched_source_ids.map(statSourceLabel)
      : [];
    if (!candidates.length) {
      return `
        <section class="empty-dataset-state">
          <h2>추가 자료 후보를 찾지 못했습니다</h2>
          <p class="muted">검색어를 바꾸거나 탐구 질문의 대상, 기간, 지역, 변수를 더 구체화해 다시 검색해 주세요.</p>
        </section>
      `;
    }
    return `
      <section class="kosis-results">
        <div>
          <p class="eyebrow">공식 통계 자료 후보</p>
          <h2>KOSIS 외 연결 출처에서 찾은 후보</h2>
          <p class="muted">${
            searchedSources.length
              ? `${escapeHtml(searchedSources.join(", "))}까지 함께 확인했습니다. `
              : ""
          }자동 수집 버튼은 백엔드 커넥터와 인증 상태가 모두 확인된 자료에만 표시됩니다.</p>
        </div>
        <div class="question-candidate-list">
          ${candidates
            .map((candidate, index) => {
              const access = candidate.access_info || {};
              const canAutoFetch = Boolean(access.auto_fetch_available);
              const manualUrl = candidate.manual_download_url || access.manual_download_url;
              const catalogType = candidate.raw?.catalog_type;
              return `
                <article class="candidate-question-card kosis-candidate-card">
                  <div class="meta-row">
                    <span class="chip">${escapeHtml(candidate.provider || candidate.source_id)}</span>
                    ${catalogType ? `<span class="chip">공공데이터포털 ${escapeHtml(catalogType)}</span>` : ""}
                    <span class="chip">${escapeHtml(statAccessLabel(access.access_status))}</span>
                    <span class="chip">${escapeHtml(candidate.unit || "단위 확인 필요")}</span>
                  </div>
                  <h3>${escapeHtml(candidate.dataset_title || "통계 API 자료 후보")}</h3>
                  <p>${escapeHtml(candidate.description || access.reason || "")}</p>
                  <dl class="advice-detail-list">
                    <dt>소스</dt>
                    <dd>${escapeHtml(candidate.source_id || "-")} · ${escapeHtml(candidate.dataset_id || "-")}</dd>
                    <dt>차원</dt>
                    <dd>${escapeHtml((candidate.available_dimensions || []).join(", ") || "확인 필요")}</dd>
                    <dt>지표</dt>
                    <dd>${escapeHtml((candidate.available_measures || []).join(", ") || "확인 필요")}</dd>
                  </dl>
                  <h4>주의할 점</h4>
                  ${renderAdviceList([].concat(candidate.cautions || [], access.reason || []))}
                  <div class="actions">
                    ${
                      canAutoFetch
                        ? isDatasetAlreadyImported(candidate.dataset_title || "통계 API 자료 후보")
                          ? `<button type="button" class="secondary" disabled>이미 가져온 자료</button>`
                          : `<button type="button" class="primary" data-stat-api-index="${index}">자료 가져오기</button>`
                        : ""
                    }
                    ${
                      manualUrl
                        ? `<a class="button-link" href="${escapeHtml(manualUrl)}" target="_blank" rel="noreferrer">직접 다운로드</a>`
                        : ""
                    }
                    ${
                      candidate.docs_url
                        ? `<a class="button-link" href="${escapeHtml(candidate.docs_url)}" target="_blank" rel="noreferrer">API 문서</a>`
                        : ""
                    }
                  </div>
                </article>
              `;
            })
            .join("")}
        </div>
      </section>
    `;
  }

  function attachUploadEvents() {
    const form = document.getElementById("csv-upload-form");
    if (form) form.addEventListener("submit", uploadCsv);
    const officialSearchForm = document.getElementById("official-stat-search-form");
    if (officialSearchForm) officialSearchForm.addEventListener("submit", searchOfficialStatDatasets);
    const officialSearchQuestion = document.getElementById("official-search-question");
    if (officialSearchQuestion) {
      officialSearchQuestion.addEventListener("input", (event) => {
        state.kosisQuestionDraft = event.target.value;
        state.statApiQuestionDraft = event.target.value;
        StatState.setStudentState(state);
      });
    }
    const officialSearchKeyword = document.getElementById("official-search-keyword");
    if (officialSearchKeyword) {
      officialSearchKeyword.addEventListener("input", (event) => {
        state.kosisSearchDraft = event.target.value;
        StatState.setStudentState(state);
      });
    }
    const resetUpload = document.getElementById("reset-upload");
    if (resetUpload) {
      resetUpload.addEventListener("click", () => {
        state = { ...state, uploadPlan: null, datasetMode: "search" };
        save();
        renderDatasets(state.datasets || []);
      });
    }
    const useUploaded = document.getElementById("use-uploaded-dataset");
    if (useUploaded) {
      useUploaded.addEventListener("click", () => selectDataset(state.uploadPlan.dataset.dataset_id));
    }
    attachKosisRecommendationEvents();
    attachStatApiCandidateEvents();
  }

  function attachKosisRecommendationEvents() {
    view.querySelectorAll("[data-kosis-index]").forEach((button) => {
      button.addEventListener("click", () => importKosisDataset(Number(button.dataset.kosisIndex)));
    });
    document.getElementById("load-kosis-suggestions")?.addEventListener("click", () => {
      loadSuggestedKosisDatasets();
    });
  }

  function attachStatApiCandidateEvents() {
    view.querySelectorAll("[data-stat-api-index]").forEach((button) => {
      button.addEventListener("click", () => importStatApiDataset(Number(button.dataset.statApiIndex)));
    });
  }

  function mergeDataset(datasets, dataset) {
    if (!dataset) return datasets || [];
    const existing = (datasets || []).filter((item) => item.dataset_id !== dataset.dataset_id);
    return [dataset, ...existing];
  }

  async function uploadCsv(event) {
    event.preventDefault();
    if (!state.topic?.topic_id) {
      StatApi.toast("주제를 먼저 선택해 주세요.");
      return;
    }
    const fileInput = document.getElementById("csv-file");
    const nameInput = document.getElementById("csv-name");
    const file = fileInput?.files?.[0];
    if (!file) {
      StatApi.toast("업로드할 CSV 파일을 선택해 주세요.");
      return;
    }
    const formData = new FormData();
    const datasetName = nameInput?.value?.trim() || "";
    formData.append("file", file);
    formData.append("topic_id", state.topic.topic_id);
    if (datasetName) formData.append("dataset_name", datasetName);
    if (schoolLevel()) formData.append("school_level", schoolLevel());
    setLoading("CSV를 읽고 AI 처리 제안을 만드는 중입니다.", {
      label: "업로드 파일",
      text: file.name,
      items: [{ label: "자료 이름", value: datasetName || file.name }],
    });
    const uploadPlan = await StatApi.request("/api/datasets/upload", {
      method: "POST",
      body: formData,
    });
    state = {
      ...state,
      datasetMode: "search",
      uploadPlan,
      datasets: mergeDataset(state.datasets, uploadPlan.dataset),
      dataset: null,
      datasetSummary: null,
      sheet: null,
      sheetEdits: {},
      sheetFilters: {},
      analysisRows: { mode: "all", selected: [] },
      customAnalysisFields: {},
      derivedSuggestions: null,
      options: [],
      analysis: null,
      hints: null,
      report: null,
      coach: null,
      interpretationDrafts: {},
      interpretationFeedback: {},
    };
    save();
    renderDatasets(state.datasets || []);
  }

  async function recommendKosisDatasets(event) {
    event.preventDefault();
    if (!state.topic?.topic_id) {
      StatApi.toast("주제를 먼저 선택해 주세요.");
      return;
    }
    const questionInput = document.getElementById("kosis-question");
    const searchInput = document.getElementById("kosis-search-keyword");
    const researchQuestion = (questionInput?.value || state.topic?.question || "").trim();
    const searchKeyword = (searchInput?.value || "").trim();
    if (!searchKeyword) {
      StatApi.toast("검색어를 입력해 주세요.");
      searchInput?.focus();
      return;
    }
    state = { ...state, kosisQuestionDraft: researchQuestion, kosisSearchDraft: searchKeyword, datasetMode: "search" };
    save();
    setLoading("입력한 검색어로 공식 통계 자료를 찾고 탐구 질문과의 관련성을 정리하는 중입니다.", {
      label: "탐구 질문",
      text: researchQuestion,
      items: [{ label: "검색어", value: searchKeyword }],
    });
    try {
      const kosisPlan = await StatApi.request("/api/datasets/kosis/search", {
        method: "POST",
        body: JSON.stringify({
          topic_id: state.topic.topic_id,
          search_keyword: searchKeyword,
          research_question: researchQuestion,
          grade_level: schoolLevel() || "middle_high",
        }),
      });
      state = {
        ...state,
        kosisPlan: {
          ...kosisPlan,
          metadata: {
            ...(kosisPlan.metadata || {}),
            topic_id: state.topic.topic_id,
            suggestion_mode: "student_keyword",
          },
        },
        uploadPlan: null,
        datasetMode: "search",
      };
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  async function searchOfficialStatDatasets(event) {
    event.preventDefault();
    if (!state.topic?.topic_id) {
      StatApi.toast("주제를 먼저 선택해 주세요.");
      return;
    }
    const questionInput = document.getElementById("official-search-question");
    const searchInput = document.getElementById("official-search-keyword");
    const researchQuestion = (questionInput?.value || state.topic?.question || "").trim();
    const searchKeyword = (searchInput?.value || "").trim();
    if (!searchKeyword) {
      StatApi.toast("검색어를 입력해 주세요.");
      searchInput?.focus();
      return;
    }
    state = {
      ...state,
      kosisQuestionDraft: researchQuestion,
      statApiQuestionDraft: researchQuestion,
      kosisSearchDraft: searchKeyword,
      datasetMode: "search",
      kosisPlan: null,
      statApiPlan: null,
    };
    save();
    setLoading("KOSIS와 공공데이터포털 등 연결된 공식 통계 출처를 함께 확인하는 중입니다.", {
      label: "탐구 질문",
      text: researchQuestion,
      items: [{ label: "검색어", value: searchKeyword }],
    });
    try {
      const [kosisResult, statApiResult] = await Promise.allSettled([
        StatApi.request("/api/datasets/kosis/search", {
          method: "POST",
          body: JSON.stringify({
            topic_id: state.topic.topic_id,
            search_keyword: searchKeyword,
            research_question: researchQuestion,
            grade_level: schoolLevel() || "middle_high",
          }),
        }),
        StatApi.request("/api/stat/search-datasets", {
          method: "POST",
          body: JSON.stringify({
            research_question: researchQuestion,
            grade_level: schoolLevel() || state.topic.level || "middle_high",
            keywords: [searchKeyword],
          }),
        }),
      ]);
      const failures = [];
      const nextState = {
        ...state,
        datasetMode: "search",
        uploadPlan: null,
      };
      if (kosisResult.status === "fulfilled") {
        nextState.kosisPlan = {
          ...kosisResult.value,
          metadata: {
            ...(kosisResult.value.metadata || {}),
            topic_id: state.topic.topic_id,
            suggestion_mode: "student_keyword",
          },
        };
      } else {
        failures.push(kosisResult.reason?.message || "일부 공식 통계 검색에 실패했습니다.");
      }
      if (statApiResult.status === "fulfilled") {
        nextState.statApiPlan = statApiResult.value;
      } else {
        failures.push(statApiResult.reason?.message || "일부 공식 통계 검색에 실패했습니다.");
      }
      if (kosisResult.status !== "fulfilled" && statApiResult.status !== "fulfilled") {
        StatApi.toast(failures[0] || "자료 검색에 실패했습니다.");
      } else if (failures.length) {
        StatApi.toast("일부 출처 검색은 실패했지만 확인 가능한 후보를 표시합니다.");
      }
      state = nextState;
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  async function loadSuggestedKosisDatasets() {
    if (!state.topic?.topic_id) {
      StatApi.toast("주제를 먼저 선택해 주세요.");
      return;
    }
    if (isCurrentKosisPlan() && state.kosisPlan.metadata?.suggestion_mode !== "student_keyword") {
      renderDatasets(state.datasets || []);
      return;
    }
    const researchQuestion = currentResearchQuestion();
    if (!researchQuestion) {
      StatApi.toast("탐구 질문을 먼저 정해 주세요.");
      return;
    }
    setLoading("AI가 탐구 질문을 검색 전략으로 바꾸고 실제 자료 후보를 확인하는 중입니다.", {
      label: "탐구 질문",
      text: researchQuestion,
      items: [{ label: "자료 활용", value: "AI 추천 자료 사용" }],
    });
    try {
      const isCustomTopic = state.topic.topic_id.startsWith("custom_");
      const gradeLevel = schoolLevel() || state.topic.level || "middle_high";
      const endpoint = isCustomTopic
        ? "/api/datasets/kosis/recommend"
        : `/api/topics/${state.topic.topic_id}/dataset-suggestions?school_level=${encodeURIComponent(gradeLevel)}`;
      const requestOptions = isCustomTopic
        ? {
            method: "POST",
            body: JSON.stringify({
              topic_id: state.topic.topic_id,
              research_question: researchQuestion,
              grade_level: gradeLevel,
            }),
          }
        : undefined;
      const kosisPlan = await StatApi.request(endpoint, requestOptions);
      state = {
        ...state,
        kosisPlan: {
          ...kosisPlan,
          metadata: {
            ...(kosisPlan.metadata || {}),
            topic_id: state.topic.topic_id,
            suggestion_mode: isCustomTopic ? "custom_topic_ai" : "example_topic_cached_ai",
          },
        },
        kosisQuestionDraft: researchQuestion,
        uploadPlan: null,
        datasetMode: "suggested",
      };
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  async function searchStatApiDatasets(event) {
    event.preventDefault();
    if (!state.topic?.topic_id) {
      StatApi.toast("주제를 먼저 선택해 주세요.");
      return;
    }
    const questionInput = document.getElementById("stat-api-question");
    const researchQuestion = (questionInput?.value || state.topic?.question || "").trim();
    if (!researchQuestion) {
      StatApi.toast("탐구 질문을 먼저 입력해 주세요.");
      questionInput?.focus();
      return;
    }
    state = { ...state, statApiQuestionDraft: researchQuestion, datasetMode: "search" };
    save();
    setLoading("연결된 공식 통계 출처에서 자료 후보와 자동 수집 가능 여부를 확인하는 중입니다.", {
      label: "탐구 질문",
      text: researchQuestion,
    });
    try {
      const statApiPlan = await StatApi.request("/api/stat/search-datasets", {
        method: "POST",
        body: JSON.stringify({
          research_question: researchQuestion,
          grade_level: schoolLevel() || state.topic.level || "middle_high",
        }),
      });
      state = { ...state, statApiPlan, uploadPlan: null, datasetMode: "search" };
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  async function importStatApiDataset(index) {
    const candidates = state.statApiPlan?.candidates || [];
    const candidate = candidates[index];
    if (!candidate) {
      StatApi.toast("가져올 통계 API 후보를 찾을 수 없습니다.");
      return;
    }
    const access = candidate.access_info || {};
    if (!access.auto_fetch_available) {
      StatApi.toast("이 후보는 현재 자동 수집을 사용할 수 없습니다. 직접 다운로드 후 CSV 업로드를 사용해 주세요.");
      return;
    }
    let targetDatasetId = candidate.dataset_id;
    let targetIndicatorId = candidate.raw?.indicator_id || candidate.dataset_id;
    let datasetTitle = candidate.dataset_title;

    if (targetDatasetId.endsWith("manual-search")) {
      const userInput = prompt(`${candidate.source_id.toUpperCase()} 통계표 코드 또는 지표 ID를 입력하세요.\n(예: ECOS의 경우 060Y001)`);
      if (!userInput) {
        StatApi.toast("입력이 취소되었습니다.");
        return;
      }
      targetDatasetId = userInput.trim();
      targetIndicatorId = userInput.trim();
      datasetTitle = `직접 입력 자료 (${targetDatasetId})`;
    }

    setLoading("외부 통계 API 자료를 표준 CSV로 변환하고 프로젝트 자료로 등록하는 중입니다.", {
      label: "선택한 자료",
      text: datasetTitle || targetDatasetId,
      items: [{ label: "출처", value: candidate.source_id }],
    });
    try {
      const payload = await StatApi.request("/api/stat/fetch-csv", {
        method: "POST",
        body: JSON.stringify({
          source_id: candidate.source_id,
          dataset_id: targetDatasetId,
          indicator_id: targetIndicatorId,
          country_codes: ["KOR", "JPN", "USA"],
          start_period: "2010",
          end_period: String(new Date().getFullYear()),
          topic_id: state.topic.topic_id,
          import_as_dataset: true,
          dataset_name: datasetTitle,
        }),
      });
      const uploadPlan = payload.imported_dataset;
      if (!uploadPlan?.dataset) {
        StatApi.toast("CSV 변환은 완료됐지만 프로젝트 자료 등록 결과를 찾지 못했습니다.");
        renderDatasets(state.datasets || []);
        return;
      }
      state = {
        ...state,
        datasetMode: "search",
        uploadPlan,
        datasets: mergeDataset(state.datasets, uploadPlan.dataset),
        dataset: null,
        datasetSummary: null,
        sheet: null,
        sheetEdits: {},
        sheetFilters: {},
        analysisRows: { mode: "all", selected: [] },
        customAnalysisFields: {},
        derivedSuggestions: null,
        options: [],
        analysis: null,
        hints: null,
        report: null,
        coach: null,
        interpretationDrafts: {},
        interpretationFeedback: {},
      };
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  async function importKosisDataset(index) {
    const recommendations = state.kosisPlan?.recommendations?.recommended_datasets || [];
    const recommendation = recommendations[index];
    if (!recommendation) {
      StatApi.toast("가져올 자료 후보를 찾을 수 없습니다.");
      return;
    }
    setLoading("선택한 자료를 가져와 CSV로 변환하는 중입니다.", {
      label: "선택한 자료",
      text: recommendation.dataset_title || recommendation.tbl_name || recommendation.dataset_id,
      items: [{ label: "출처", value: recommendation.source || recommendation.org_name || "KOSIS" }],
    });
    try {
      const uploadPlan = await StatApi.request("/api/datasets/kosis/import", {
        method: "POST",
        body: JSON.stringify({
          topic_id: state.topic.topic_id,
          recommendation,
        }),
      });
      state = {
        ...state,
        datasetMode: "search",
        uploadPlan,
        datasets: mergeDataset(state.datasets, uploadPlan.dataset),
        dataset: null,
        datasetSummary: null,
        sheet: null,
        sheetEdits: {},
        sheetFilters: {},
        analysisRows: { mode: "all", selected: [] },
        customAnalysisFields: {},
        derivedSuggestions: null,
        options: [],
        analysis: null,
        hints: null,
        report: null,
        coach: null,
        interpretationDrafts: {},
        interpretationFeedback: {},
      };
      save();
      renderDatasets(state.datasets || []);
    } catch (error) {
      StatApi.toast(error.message);
      renderDatasets(state.datasets || []);
    }
  }

  function renderDatasets(datasets) {
    if (!state.topic?.topic_id) {
      view.innerHTML = `
        <section class="empty-dataset-state">
          <h2>결정한 주제가 필요합니다</h2>
          <p class="muted">AI 조언 화면에서 결정한 주제를 입력하면 자료를 가져올 수 있습니다.</p>
          <div class="actions">
            <button type="button" class="primary" id="return-question-advice">결정한 주제 입력으로 이동</button>
          </div>
        </section>
      `;
      document.getElementById("return-question-advice").addEventListener("click", () => {
        state = { ...state, step: 0, startMode: "question" };
        save();
        renderQuestionAdvisor();
      });
      return;
    }
    const baseDatasets = Array.isArray(datasets) ? datasets : [];
    const allDatasets =
      state.dataset?.dataset_id && !baseDatasets.some((dataset) => dataset.dataset_id === state.dataset.dataset_id)
        ? [state.dataset, ...baseDatasets]
        : baseDatasets;
    const rawImportedDatasets = allDatasets.filter((dataset) => dataset.uploaded);
    
    const importedDatasets = [];
    const seenSignatures = new Set();
    for (const ds of rawImportedDatasets) {
      const sig = ds.name + "|" + (ds.source_note || "");
      if (!seenSignatures.has(sig)) {
        importedDatasets.push(ds);
        seenSignatures.add(sig);
      }
    }
    const importedDatasetCards = importedDatasets.map(renderDatasetCard).join("");
    const exampleDatasets = allDatasets.filter((dataset) => !dataset.uploaded);
    const exampleSection = renderExampleDatasetSection(exampleDatasets);
    const selectedDatasetPanel = renderSelectedDatasetPanel();
    const sharedDatasetCards = (state.sharedArtifacts || [])
      .filter((artifact) => artifact.stage === "dataset")
      .map(
        (artifact) => `
          <article class="dataset-card shared-dataset-card">
            <p class="eyebrow">공유 자료</p>
            <h3>${escapeHtml(artifact.title)}</h3>
            <p>${escapeHtml(artifact.description)}</p>
            <p class="muted">${escapeHtml(artifact.source || "공유 산출물")}</p>
            <button
              class="primary"
              data-shared-dataset="${escapeHtml(artifact.dataset_id)}"
              data-shared-project="${escapeHtml(artifact.project_id)}"
            >분석에 사용</button>
          </article>
        `,
      )
      .join("");
    const sharedSection = sharedDatasetCards
      ? `<section class="shared-artifact-panel"><h2>교사가 공유한 자료</h2><div class="card-grid">${sharedDatasetCards}</div></section>`
      : "";

    function attachDatasetSelectionEvents() {
      view.querySelectorAll("[data-dataset]").forEach((button) => {
        button.addEventListener("click", () => selectDataset(button.dataset.dataset));
      });
      view.querySelectorAll("[data-shared-dataset]").forEach((button) => {
        button.addEventListener("click", () =>
          useSharedDataset(button.dataset.sharedDataset, button.dataset.sharedProject).catch((error) =>
            StatApi.toast(error.message),
          ),
        );
      });
    }

    const mode = state.datasetMode;
    const importedSection = importedDatasetCards
      ? `<section class="dataset-section">
          <div class="section-title compact-title">
            <div>
              <p class="eyebrow">가져온 자료</p>
              <h2>분석에 사용할 수 있는 자료</h2>
            </div>
          </div>
          <div class="card-grid">${importedDatasetCards}</div>
        </section>`
      : "";
    const suggestedResults =
      mode === "suggested"
        ? `<section class="dataset-section">
            <div class="section-title compact-title">
              <div>
                <p class="eyebrow">AI 추천 자료</p>
                <h2>탐구 질문에 맞는 공식 통계 후보</h2>
              </div>
            </div>
            ${
              isCurrentKosisPlan() && state.kosisPlan.metadata?.suggestion_mode !== "student_keyword"
                ? renderKosisRecommendations()
                : `<section class="empty-dataset-state">
                    <h2>AI 추천 자료를 불러와야 합니다</h2>
                    <p class="muted">탐구 질문에 맞는 검색 전략을 만들고 실제 확인 가능한 공식 통계 후보를 제시합니다.</p>
                    <button type="button" class="primary" id="load-kosis-suggestions">AI 추천 자료 받기</button>
                  </section>`
            }
          </section>`
        : "";
    const searchResults =
      mode === "search"
        ? `
          ${renderKosisRecommendations()}
          ${renderStatApiCandidates()}
          ${
            !state.kosisPlan && !state.statApiPlan && !importedDatasetCards
              ? `<section class="empty-dataset-state">
                  <h2>아직 가져온 자료가 없습니다</h2>
                  <p class="muted">직접 검색이나 CSV 업로드로 분석 자료를 만들 수 있습니다.</p>
                </section>`
              : ""
          }
        `
        : "";

    const mergeWizard =
      mode === "merge"
        ? renderMergeWizard(importedDatasets)
        : "";

    view.innerHTML = `
      ${exampleSection}
      ${selectedDatasetPanel}
      ${renderDatasetUseMethods(importedDatasets.length)}
      ${suggestedResults}
      ${searchResults}
      ${mergeWizard}
      ${importedSection}
      ${sharedSection}
    `;
    attachSelectedDatasetPanelEvents();
    attachDatasetModeEvents();
    attachUploadEvents();
    attachKosisRecommendationEvents();
    attachDatasetSelectionEvents();
    if (typeof attachMergeEvents === "function") {
      attachMergeEvents(importedDatasets);
    }
  }

  async function hydrateSelectedDataset(project, datasetId, uploadPlan = null) {
    const schema = await StatApi.request(`/api/datasets/${datasetId}/schema`);
    const summaryData = await StatApi.request(`/api/datasets/${datasetId}/summary`);
    const sheet = await StatApi.request(`/api/datasets/${datasetId}/sheet?limit=100`);
    const options = await StatApi.request(`/api/projects/${project.project_id}/analysis-options`);
    const derivedSuggestions = await StatApi.request(
      `/api/projects/${project.project_id}/derived-variable-suggestions`,
    );
    state = {
      ...state,
      step: STEP.ANALYSIS,
      project,
      dataset: schema,
      datasetSummary: summaryData,
      sheet,
      sheetEdits: {},
      sheetFilters: {},
      analysisRows: { mode: "all", selected: [] },
      customAnalysisFields: {},
      derivedSuggestions,
      uploadPlan,
      options,
      analysis: null,
      hints: null,
      report: null,
      coach: null,
      interpretationDrafts: {},
      interpretationFeedback: {},
    };
    save();
    renderAnalysisWorkspace();
  }

  async function selectDataset(datasetId) {
    const datasetLabel =
      (state.datasets || []).find((item) => item.dataset_id === datasetId)?.name ||
      state.uploadPlan?.dataset?.name ||
      datasetId;
    setLoading("자료 구조와 분석 후보를 불러오는 중입니다.", {
      label: "선택한 자료",
      text: datasetLabel,
    });
    const project = await StatApi.request(`/api/projects/${state.project.project_id}/select-dataset`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    await hydrateSelectedDataset(
      project,
      datasetId,
      state.uploadPlan?.dataset?.dataset_id === datasetId ? state.uploadPlan : null,
    );
  }

  async function useSharedDataset(datasetId, sourceProjectId) {
    setLoading("공유받은 자료를 내 프로젝트에 연결하는 중입니다.", {
      label: "공유 자료",
      text: datasetId,
      items: [{ label: "공유한 프로젝트", value: sourceProjectId }],
    });
    const project = await StatApi.request(`/api/projects/${state.project.project_id}/use-shared-dataset`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId, source_project_id: sourceProjectId }),
    });
    await hydrateSelectedDataset(project, datasetId, null);
  }

  function analysisColumns(dtype) {
    const columns = state.dataset?.columns || [];
    if (dtype === "numeric") return columns.filter((column) => column.dtype === "numeric");
    if (dtype === "categorical") return columns.filter((column) => column.dtype === "categorical");
    return columns;
  }

  function columnOptionLabel(column) {
    if (!column) return "";
    return column.display_name && column.display_name !== column.name
      ? `${column.display_name} (${column.name})`
      : column.name;
  }

  function renderColumnOptions(columns, selected = "") {
    const selectedSet = new Set(Array.isArray(selected) ? selected : [selected]);
    return columns
      .map(
        (column) =>
          `<option value="${escapeHtml(column.name)}" ${selectedSet.has(column.name) ? "selected" : ""}>${escapeHtml(
            columnOptionLabel(column),
          )}</option>`,
      )
      .join("");
  }

  function renderAnalysisField(label, content) {
    return `
      <label class="analysis-field">
        <span>${escapeHtml(label)}</span>
        ${content}
      </label>
    `;
  }

  function firstColumnName(columns, excluded = []) {
    const blocked = new Set(excluded.filter(Boolean));
    return columns.find((column) => !blocked.has(column.name))?.name || columns[0]?.name || "";
  }

  const MAX_GROUPABLE_VALUES = 8;

  function firstGroupableName(columns) {
    const groupable = columns.find((column) => {
      const count = state.datasetSummary?.columns?.[column.name]?.unique_count;
      return Number.isInteger(count) && count >= 2 && count <= MAX_GROUPABLE_VALUES;
    });
    return groupable?.name || columns[0]?.name || "";
  }

  function renderCustomToolFields(toolName) {
    const numeric = analysisColumns("numeric");
    const all = analysisColumns("all");
    const fieldState = state.customAnalysisFields || {};
    const categorySource = all;
    const firstCategory = categorySource[0]?.name || "";
    const firstNumeric = numeric[0]?.name || "";
    const secondNumeric = numeric[1]?.name || firstNumeric;
    const numericOptions = (selected = "") => renderColumnOptions(numeric, selected);
    const categoryOptions = (selected = "", columns = categorySource) => renderColumnOptions(columns, selected);
    const allOptions = (selected = "") => renderColumnOptions(all, selected);
    if (toolName === "compute_descriptive_stats") {
      const storedColumns = (Array.isArray(fieldState.columns) ? fieldState.columns : []).filter((name) =>
        numeric.some((column) => column.name === name),
      );
      const statsColumns = storedColumns.length ? storedColumns : [firstNumeric].filter(Boolean);
      const statsGroupCandidates = all.filter((column) => !statsColumns.includes(column.name));
      const statsGroupBy = validColumnName(statsGroupCandidates, fieldState.group_by, "");
      return `
        ${renderAnalysisField(
          "수치형 항목",
          `<select id="custom-columns" data-custom-field="columns" multiple size="4">${renderColumnOptions(
            numeric,
            statsColumns,
          )}</select>`,
        )}
        <div class="analysis-field">
          <span>통계량</span>
          <div class="checkbox-grid">
            ${["mean", "median", "min", "max", "std", "q1", "q3", "iqr"]
              .map(
                (stat, index) => `
                  <label><input type="checkbox" name="custom-stat" value="${stat}" ${
                    index < 4 ? "checked" : ""
                  } /> ${metricLabel(stat)}</label>
                `,
              )
              .join("")}
          </div>
        </div>
        ${renderAnalysisField(
          "집단 나누기",
          `<select id="custom-group-by" data-custom-field="group_by" data-custom-refresh="true">
            <option value="">나누지 않음(전체)</option>${categoryOptions(statsGroupBy, statsGroupCandidates)}
          </select>`,
        )}
        <p class="field-hint">집단을 고르면 집단별 통계량을 한 표에서 나란히 비교합니다(집단 2~8개).</p>
        ${renderAnalysisValueSelector(statsGroupBy, "비교할 집단값")}
      `;
    }
    if (toolName === "plot_line") {
      const xCol = validColumnName(all, fieldState.x_col, all[0]?.name || "");
      const yCol = validColumnName(numeric, fieldState.y_col, firstNumeric);
      const seriesCandidates = all.filter((column) => column.name !== xCol && column.name !== yCol);
      const series = validColumnName(seriesCandidates, fieldState.series, "");
      return `
        ${renderAnalysisField("가로축", `<select id="custom-x-col" data-custom-field="x_col">${allOptions(xCol)}</select>`)}
        ${renderAnalysisField("세로축", `<select id="custom-y-col" data-custom-field="y_col">${numericOptions(yCol)}</select>`)}
        ${renderAnalysisField(
          "범주 추가",
          `<select id="custom-series" data-custom-field="series" data-custom-refresh="true">
            <option value="">추가 안 함</option>${categoryOptions(series, seriesCandidates)}
          </select>`,
        )}
        ${renderAnalysisValueSelector(series, "계열로 사용할 범주값")}
      `;
    }
    if (toolName === "plot_bar" || toolName === "plot_pie") {
      const categoryCol = validColumnName(categorySource, fieldState.category_col, firstCategory);
      const valueFallback = firstColumnName(numeric, [categoryCol]) || firstNumeric;
      const valueCol = validColumnName(numeric, fieldState.value_col, valueFallback);
      const groupCandidates = all.filter((column) => column.name !== categoryCol && column.name !== valueCol);
      const groupCol = toolName === "plot_bar" ? validColumnName(groupCandidates, fieldState.group_col, "") : "";
      return `
        ${renderAnalysisField(
          "범주 항목",
          `<select id="custom-category-col" data-custom-field="category_col" data-custom-refresh="true">${renderColumnOptions(
            categorySource,
            categoryCol,
          )}</select>`,
        )}
        ${renderAnalysisField("값 항목", `<select id="custom-value-col" data-custom-field="value_col">${numericOptions(valueCol)}</select>`)}
        ${
          toolName === "plot_bar"
            ? `
              ${renderAnalysisField(
                "범주 추가",
                `<select id="custom-group-col" data-custom-field="group_col" data-custom-refresh="true">
                  <option value="">추가 안 함</option>${renderColumnOptions(groupCandidates, groupCol)}
                </select>`,
              )}
              ${renderAnalysisField(
                "정렬",
                `<select id="custom-sort-order" data-custom-field="sort_order">
                  <option value="">자료 순서</option>
                  <option value="desc" ${fieldState.sort_order === "desc" ? "selected" : ""}>큰 값부터</option>
                  <option value="asc" ${fieldState.sort_order === "asc" ? "selected" : ""}>작은 값부터</option>
                </select>`,
              )
              }
            `
            : ""
        }
        ${renderAnalysisValueSelector(categoryCol, "범주값 선택")}
        ${toolName === "plot_bar" && groupCol ? renderAnalysisValueSelector(groupCol, "추가 범주값 선택") : ""}
      `;
    }
    if (toolName === "plot_histogram" || toolName === "plot_frequency_polygon") {
      const column = validColumnName(numeric, fieldState.column, firstNumeric);
      return `
        ${renderAnalysisField("수치형 항목", `<select id="custom-column" data-custom-field="column">${numericOptions(column)}</select>`)}
        ${renderAnalysisField("구간 수", `<input id="custom-bins" data-custom-field="bins" type="number" min="5" max="20" value="${escapeHtml(fieldState.bins || "8")}" />`)}
      `;
    }
    if (toolName === "plot_boxplot") {
      const column = validColumnName(numeric, fieldState.column, firstNumeric);
      const groupCandidates = all.filter((item) => item.name !== column);
      const groupBy = validColumnName(groupCandidates, fieldState.group_by, "");
      return `
        ${renderAnalysisField("수치형 항목", `<select id="custom-column" data-custom-field="column">${numericOptions(column)}</select>`)}
        ${renderAnalysisField(
          "범주 추가",
          `<select id="custom-group-by" data-custom-field="group_by" data-custom-refresh="true">
            <option value="">추가 안 함</option>${categoryOptions(groupBy, groupCandidates)}
          </select>`,
        )}
        ${renderAnalysisValueSelector(groupBy, "그룹으로 사용할 범주값")}
      `;
    }
    if (toolName === "plot_scatter") {
      return `
        ${renderAnalysisField(
          "가로축",
          `<select id="custom-x-col" data-custom-field="x_col">${numericOptions(
            validColumnName(numeric, fieldState.x_col, firstNumeric),
          )}</select>`,
        )}
        ${renderAnalysisField(
          "세로축",
          `<select id="custom-y-col" data-custom-field="y_col">${renderColumnOptions(
            numeric,
            validColumnName(numeric, fieldState.y_col, secondNumeric),
          )}</select>`,
        )}
        <label class="inline-check"><input id="custom-trendline" type="checkbox" checked /> 추세선 표시</label>
      `;
    }
    if (toolName === "compute_correlation") {
      return `
        ${renderAnalysisField(
          "첫 번째 수치형 항목",
          `<select id="custom-x-col" data-custom-field="x_col">${numericOptions(
            validColumnName(numeric, fieldState.x_col, firstNumeric),
          )}</select>`,
        )}
        ${renderAnalysisField(
          "두 번째 수치형 항목",
          `<select id="custom-y-col" data-custom-field="y_col">${renderColumnOptions(
            numeric,
            validColumnName(numeric, fieldState.y_col, secondNumeric),
          )}</select>`,
        )}
      `;
    }
    if (toolName === "compute_grouped_correlation" || toolName === "plot_grouped_scatter") {
      const xCol = validColumnName(numeric, fieldState.x_col, firstNumeric);
      const yCol = validColumnName(numeric, fieldState.y_col, secondNumeric);
      const groupCandidates = all.filter((column) => column.name !== xCol && column.name !== yCol);
      const groupBy = validColumnName(groupCandidates, fieldState.group_by, firstGroupableName(groupCandidates));
      return `
        ${renderAnalysisField("첫 번째 수치형 항목", `<select id="custom-x-col" data-custom-field="x_col" data-custom-refresh="true">${numericOptions(xCol)}</select>`)}
        ${renderAnalysisField(
          "두 번째 수치형 항목",
          `<select id="custom-y-col" data-custom-field="y_col" data-custom-refresh="true">${numericOptions(yCol)}</select>`,
        )}
        ${renderAnalysisField(
          "집단 구분",
          `<select id="custom-group-by" data-custom-field="group_by" data-custom-refresh="true">${categoryOptions(
            groupBy,
            groupCandidates,
          )}</select>`,
        )}
        <p class="field-hint">집단은 2개 이상 8개 이하로 나뉘는 항목을 고르세요.</p>
        ${renderAnalysisValueSelector(groupBy, "비교할 집단값")}
      `;
    }
    if (toolName === "plot_map") {
      const latCol = validColumnName(numeric, fieldState.lat_col, firstNumeric);
      const lonCol = validColumnName(numeric, fieldState.lon_col, secondNumeric);
      const colorFallback = firstColumnName(numeric, [latCol, lonCol]) || firstNumeric;
      const colorCol = validColumnName(numeric, fieldState.color_col, colorFallback);
      const sizeCol = validColumnName(numeric, fieldState.size_col, "");
      const groupCandidates = all.filter(
        (column) => column.name !== latCol && column.name !== lonCol && column.name !== colorCol,
      );
      const groupBy = validColumnName(groupCandidates, fieldState.group_by, "");
      return `
        ${renderAnalysisField("위도", `<select id="custom-lat-col" data-custom-field="lat_col" data-custom-refresh="true">${numericOptions(latCol)}</select>`)}
        ${renderAnalysisField(
          "경도",
          `<select id="custom-lon-col" data-custom-field="lon_col" data-custom-refresh="true">${numericOptions(lonCol)}</select>`,
        )}
        ${renderAnalysisField(
          "색으로 표시할 값",
          `<select id="custom-color-col" data-custom-field="color_col" data-custom-refresh="true">${numericOptions(colorCol)}</select>`,
        )}
        ${renderAnalysisField(
          "크기로 표시할 값",
          `<select id="custom-size-col" data-custom-field="size_col">
            <option value="">선택 안 함</option>${numericOptions(sizeCol)}
          </select>`,
        )}
        ${renderAnalysisField(
          "모양으로 구분할 집단",
          `<select id="custom-group-by" data-custom-field="group_by" data-custom-refresh="true">
            <option value="">구분 안 함</option>${categoryOptions(groupBy, groupCandidates)}
          </select>`,
        )}
        ${renderAnalysisValueSelector(groupBy, "모양으로 구분할 집단값")}
      `;
    }
    if (toolName === "create_frequency_table" || toolName === "plot_stem_leaf") {
      const source = toolName === "plot_stem_leaf" ? numeric : all;
      const column = validColumnName(source, fieldState.column, source[0]?.name || "");
      return `
        ${renderAnalysisField(
          "항목",
          `<select id="custom-column" data-custom-field="column">${renderColumnOptions(source, column)}</select>`,
        )}
        ${
          toolName === "create_frequency_table"
            ? renderAnalysisField("구간 수", `<input id="custom-bins" data-custom-field="bins" type="number" min="5" max="20" value="${escapeHtml(fieldState.bins || "8")}" />`)
            : ""
        }
      `;
    }
    if (toolName === "create_crosstab") {
      const crosstabSource = all;
      const rowColumn = validColumnName(crosstabSource, fieldState.row_column, crosstabSource[0]?.name || "");
      const colColumn = validColumnName(
        crosstabSource.filter((column) => column.name !== rowColumn),
        fieldState.col_column,
        crosstabSource.find((column) => column.name !== rowColumn)?.name || rowColumn,
      );
      return `
        ${renderAnalysisField(
          "행 항목",
          `<select id="custom-row-column" data-custom-field="row_column" data-custom-refresh="true">${renderColumnOptions(
            crosstabSource,
            rowColumn,
          )}</select>`,
        )}
        ${renderAnalysisField(
          "열 항목",
          `<select id="custom-col-column" data-custom-field="col_column" data-custom-refresh="true">${renderColumnOptions(
            crosstabSource,
            colColumn,
          )}</select>`,
        )}
        <label class="inline-check"><input id="custom-normalize" type="checkbox" /> 상대도수로 보기</label>
        ${renderAnalysisValueSelector(rowColumn, "행 범주값 선택")}
        ${colColumn && colColumn !== rowColumn ? renderAnalysisValueSelector(colColumn, "열 범주값 선택") : ""}
      `;
    }
    if (toolName === "plot_choropleth") {
      const geoCandidates = all;
      const geoCol = validColumnName(geoCandidates, fieldState.region_col, geoCandidates[0]?.name || "");
      const valueCol = validColumnName(numeric, fieldState.value_col, firstNumeric);
      const classes = mapClassCount();
      return `
        ${renderMapLevelFields()}
        ${renderAnalysisField("지역 항목", `<select id="custom-region-col" data-custom-field="region_col">${categoryOptions(geoCol, geoCandidates)}</select>`)}
        ${renderAnalysisField("수치형 항목", `<select id="custom-value-col" data-custom-field="value_col">${numericOptions(valueCol)}</select>`)}
        ${renderAnalysisField(
          "색을 나눌 계급 수",
          `<input id="custom-n-classes" data-custom-field="n_classes" data-custom-refresh="true" type="number" min="3" max="7" value="${classes}" />`,
        )}
        ${renderMapScalePicker(classes)}
      `;
    }
    return "";
  }

  function mapClassCount() {
    const raw = Number((state.customAnalysisFields || {}).n_classes);
    return Number.isInteger(raw) && raw >= 3 && raw <= 7 ? raw : 5;
  }

  function selectedMapLevel() {
    const level = (state.customAnalysisFields || {}).map_level;
    const known = (state.mapLevels || []).some((item) => item.level === level && item.available);
    return known ? level : "sido";
  }

  function selectedColorScale() {
    const scaleId = (state.customAnalysisFields || {}).color_scale;
    const known = (state.mapColorScales || []).some((group) =>
      (group.scales || []).some((scale) => scale.scale_id === scaleId),
    );
    return known ? scaleId : "blue";
  }

  function selectedParentRegion(level) {
    const fields = state.customAnalysisFields || {};
    const sido = fields.parent_sido || "";
    if (level === "sigungu") return sido;
    if (level === "emd") return sido && fields.parent_sigungu ? `${sido} ${fields.parent_sigungu}` : "";
    return "";
  }

  function renderMapLevelFields() {
    const levels = state.mapLevels || [];
    if (!levels.length) {
      return `<p class="map-level-note">지도 단위를 불러오는 중입니다…</p>`;
    }
    const level = selectedMapLevel();
    const current = levels.find((item) => item.level === level) || levels[0];
    const fields = state.customAnalysisFields || {};
    const options = levels
      .map((item) => {
        const label = item.available
          ? item.display_name
          : `${item.display_name} — 사용할 수 없음`;
        return `<option value="${escapeHtml(item.level)}" ${item.level === level ? "selected" : ""} ${
          item.available ? "" : "disabled"
        }>${escapeHtml(label)}</option>`;
      })
      .join("");

    const note = current.requires_label
      ? `${current.description} 전국을 한 장에 그리면 경계가 뭉개져 읽을 수 없기 때문입니다.`
      : current.description;
    const unavailable = levels
      .filter((item) => !item.available && item.unavailable_reason)
      .map((item) => `${item.display_name}: ${item.unavailable_reason}`)
      .join(" / ");

    const sidoOptions = (state.mapSidoRegions || [])
      .map(
        (region) =>
          `<option value="${escapeHtml(region.name)}" ${region.name === fields.parent_sido ? "selected" : ""}>${escapeHtml(region.name)}</option>`,
      )
      .join("");
    const sigunguList = state.mapSigunguRegions || [];
    const sigunguOptions = sigunguList
      .map(
        (region) =>
          `<option value="${escapeHtml(region.short_name)}" ${region.short_name === fields.parent_sigungu ? "selected" : ""}>${escapeHtml(region.short_name)}</option>`,
      )
      .join("");

    const needsSido = level === "sigungu" || level === "emd";
    const needsSigungu = level === "emd";
    return `
      ${renderAnalysisField(
        "지도 단위",
        `<select id="custom-map-level" data-custom-field="map_level" data-custom-refresh="true">${options}</select>`,
      )}
      <p class="map-level-note">${escapeHtml(note)}${unavailable ? ` (${escapeHtml(unavailable)})` : ""}</p>
      ${
        needsSido
          ? renderAnalysisField(
              "어느 시도",
              `<select id="custom-parent-sido" data-custom-field="parent_sido" data-custom-refresh="true">
                <option value="">시도를 고르세요</option>${sidoOptions}
              </select>`,
            )
          : ""
      }
      ${
        needsSigungu
          ? renderAnalysisField(
              "어느 시군구",
              `<select id="custom-parent-sigungu" data-custom-field="parent_sigungu" data-custom-refresh="true" ${
                sigunguList.length ? "" : "disabled"
              }>
                <option value="">${sigunguList.length ? "시군구를 고르세요" : "시도를 먼저 고르세요"}</option>${sigunguOptions}
              </select>`,
            )
          : ""
      }
    `;
  }

  async function ensureMapOptions() {
    const classes = mapClassCount();
    const fields = state.customAnalysisFields || {};
    const wantedSido = fields.parent_sido || "";
    let changed = false;
    try {
      if (!state.mapLevels) {
        state.mapLevels = (await StatApi.mapLevels()).data || [];
        changed = true;
      }
      if (!state.mapColorScales || state.mapColorScaleClasses !== classes) {
        state.mapColorScales = (await StatApi.mapColorScales(classes)).data || [];
        state.mapColorScaleClasses = classes;
        changed = true;
      }
      if (!state.mapSidoRegions) {
        state.mapSidoRegions = (await StatApi.mapChildRegions("sido")).data || [];
        changed = true;
      }
      if (wantedSido && state.mapSigunguParent !== wantedSido) {
        state.mapSigunguRegions = (await StatApi.mapChildRegions("sigungu", wantedSido)).data || [];
        state.mapSigunguParent = wantedSido;
        changed = true;
      }
      if (!wantedSido && state.mapSigunguParent) {
        state.mapSigunguRegions = [];
        state.mapSigunguParent = "";
        changed = true;
      }
    } catch (error) {
      state.mapLevels = state.mapLevels || [];
      state.mapColorScales = state.mapColorScales || [];
      state.mapSidoRegions = state.mapSidoRegions || [];
      StatApi.toast(error.message);
      changed = true;
    }
    if (changed) renderAnalysisWorkspace();
  }

  function renderMapScalePicker(classes) {
    const groups = state.mapColorScales || [];
    if (!groups.length) {
      return `<p class="map-level-note">색조를 불러오는 중입니다…</p>`;
    }
    const selected = selectedColorScale();
    const body = groups
      .map(
        (group) => `
          <div class="map-scale-group">
            <h4>${escapeHtml(group.type_label)}</h4>
            <p>${escapeHtml(group.type_hint)}</p>
            <div class="map-scale-options">
              ${(group.scales || [])
                .map(
                  (scale) => `
                    <label class="map-scale-option">
                      <input type="radio" name="custom-color-scale" data-custom-field="color_scale" data-custom-refresh="true"
                        value="${escapeHtml(scale.scale_id)}" ${scale.scale_id === selected ? "checked" : ""} />
                      <span>${escapeHtml(scale.name)}</span>
                      <span class="map-scale-swatches" aria-hidden="true">
                        ${(scale.colors || [])
                          .map((color) => `<i style="background:${escapeHtml(color)}"></i>`)
                          .join("")}
                      </span>
                    </label>
                  `,
                )
                .join("")}
            </div>
          </div>
        `,
      )
      .join("");
    return `
      <fieldset class="map-scale-picker">
        <legend>색조 (계급 ${classes}개)</legend>
        ${body}
      </fieldset>
    `;
  }

  function renderSheetColumnFilter(column) {
    const filters = activeSheetFilters();
    const criteria = filters[column.name] || {};
    const values = categoricalUniqueValues(column.name);
    if (column.dtype === "categorical" && values.length) {
      const selectedValues = Array.isArray(criteria.values)
        ? criteria.values.includes("__NO_MATCH__")
          ? []
          : criteria.values
        : values;
      const selected = new Set(selectedValues);
      const selectedCount = selectedValues.length;
      const triggerLabel =
        selectedCount === values.length
          ? "값 필터: 전체"
          : selectedCount === 0
            ? "값 필터: 없음"
            : `값 필터: ${selectedCount}개`;
      return `
        <details class="sheet-column-filter-menu" data-sheet-filter-menu="${escapeHtml(column.name)}">
          <summary class="sheet-column-filter-trigger">${escapeHtml(triggerLabel)}</summary>
          <div class="sheet-column-filter-dropdown" role="group" aria-label="${escapeHtml(column.display_name || column.name)} 값 필터">
            <div class="sheet-column-filter-actions">
              <button type="button" class="sheet-filter-action" data-sheet-filter-select-all="${escapeHtml(column.name)}">모두 선택</button>
              <button type="button" class="sheet-filter-action" data-sheet-filter-clear-selection="${escapeHtml(column.name)}">선택 해제</button>
            </div>
            <div class="sheet-column-filter-values">
              ${values
                .map(
                  (value) => `
                    <label>
                      <input
                        type="checkbox"
                        data-sheet-filter-value="${escapeHtml(column.name)}"
                        value="${escapeHtml(value)}"
                        ${selected.has(value) ? "checked" : ""}
                      />
                      <span>${escapeHtml(value)}</span>
                    </label>
                  `,
                )
                .join("")}
            </div>
          </div>
        </details>
      `;
    }
    return `
      <input
        class="sheet-column-filter"
        data-sheet-filter-query="${escapeHtml(column.name)}"
        value="${escapeHtml(criteria.query || "")}"
        placeholder="포함 필터"
        aria-label="${escapeHtml(column.display_name || column.name)} 포함 필터"
      />
    `;
  }

  function validColumnName(columns, candidate, fallback = "") {
    return columns.some((column) => column.name === candidate) ? candidate : fallback;
  }

  function renderAnalysisValueSelector(columnName, label) {
    if (!columnName) return "";
    const values = categoricalUniqueValues(columnName);
    if (!values.length) return "";
    const summary = state.datasetSummary?.columns?.[columnName] || {};
    const displayName = state.dataset?.columns?.find((column) => column.name === columnName)?.display_name || columnName;
    return `
      <fieldset class="analysis-value-filter" data-analysis-filter-field="${escapeHtml(columnName)}" data-analysis-filter-total="${values.length}">
        <legend>${escapeHtml(label)} · ${escapeHtml(displayName)}</legend>
        <label class="inline-check analysis-filter-all">
          <input type="checkbox" data-analysis-filter-toggle="${escapeHtml(columnName)}" checked />
          전체 값 사용
        </label>
        <div class="checkbox-grid analysis-value-grid">
          ${values
            .map(
              (value) => `
                <label>
                  <input
                    type="checkbox"
                    data-analysis-filter-value="${escapeHtml(columnName)}"
                    value="${escapeHtml(value)}"
                    checked
                  />
                  ${escapeHtml(value)}
                </label>
              `,
            )
            .join("")}
        </div>
        ${
          summary.unique_values_truncated
            ? `<p class="muted">고유값이 많아 앞의 ${values.length}개 값만 표시합니다. 더 좁은 조건은 자료 표 필터를 함께 사용하세요.</p>`
            : ""
        }
      </fieldset>
    `;
  }

  function renderCustomAnalysisForm() {
    const tools = [
      "plot_line",
      "plot_bar",
      "plot_histogram",
      "plot_boxplot",
      "plot_scatter",
      "compute_descriptive_stats",
      "compute_correlation",
      "compute_grouped_correlation",
      "plot_grouped_scatter",
      "plot_map",
      "create_frequency_table",
      "create_crosstab",
      "plot_pie",
      "plot_frequency_polygon",
      "plot_stem_leaf",
      "plot_choropleth",
    ];
    const selectedTool = tools.includes(state.customAnalysisTool) ? state.customAnalysisTool : tools[0];
    state.customAnalysisTool = selectedTool;
    return `
      <form id="custom-analysis-form" class="custom-analysis-form">
        <div>
          <p class="eyebrow">직접 선택</p>
          <h2>원하는 항목과 분석 방법</h2>
        </div>
        ${renderAnalysisField(
          "분석 방법",
          `<select id="custom-tool-name">${tools
            .map(
              (toolName) =>
                `<option value="${toolName}" ${toolName === selectedTool ? "selected" : ""}>${toolLabel(toolName)}</option>`,
            )
            .join("")}</select>`,
        )}
        <div class="custom-analysis-fields">${renderCustomToolFields(selectedTool)}</div>
        <div class="actions">
          <button type="submit" class="primary">선택한 방식으로 분석 실행</button>
        </div>
      </form>
    `;
  }

  function renderSpreadsheetPanel() {
    const sheet = state.sheet;
    if (!sheet) {
      return `
        <section class="sheet-panel">
          <div>
            <p class="eyebrow">자료 표</p>
            <h2>스프레드시트 확인</h2>
            <p class="muted">표시할 행이 없습니다.</p>
          </div>
        </section>
      `;
    }
    const columns = sheet.columns || state.dataset.columns || [];
    const startRow = sheet.row_count ? sheet.offset + 1 : 0;
    const endRow = Math.min(sheet.offset + sheet.rows.length, sheet.row_count);
    const nextOffset = sheet.offset + sheet.rows.length;
    const hasPrevious = sheet.offset > 0;
    const hasNext = nextOffset < sheet.row_count;
    const viewSettings = sheetViewSettings();
    const rowRouter = analysisRowState();
    const selectedRows = new Set(rowRouter.selected);
    const sheetFilterCount = activeSheetFilterCount();
    const totalRowCount = Number(sheet.total_row_count ?? sheet.row_count);
    const tableWidth = sheetTableWidth(columns);
    return `
      <section class="sheet-panel">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">자료 표</p>
            <h2>스프레드시트 확인${sheet.editable ? " 및 수정" : ""}</h2>
            <p class="muted">${
              sheetFilterCount
                ? `필터 적용 ${formatNumber(sheet.row_count, false)}행 / 전체 ${formatNumber(totalRowCount, false)}행 중 ${formatNumber(
                    startRow,
                    false,
                  )}-${formatNumber(endRow, false)}행`
                : `전체 ${formatNumber(sheet.row_count, false)}행 중 ${formatNumber(startRow, false)}-${formatNumber(endRow, false)}행`
            }</p>
          </div>
          <div class="actions">
            <button type="button" id="previous-sheet-page" ${hasPrevious ? "" : "disabled"}>이전 100행</button>
            <button type="button" id="next-sheet-page" ${hasNext ? "" : "disabled"}>다음 100행</button>
            <button type="button" id="reload-sheet">새로고침</button>
            ${
              sheet.editable && columns.length > 1
                ? `<span class="muted sheet-selection-count" id="selected-sheet-columns-count">선택 0열</span>
                  <button type="button" class="danger" id="delete-selected-columns" disabled>선택 열 삭제</button>`
                : ""
            }
            ${
              sheet.editable
                ? `<button type="button" class="primary" id="save-sheet-edits" ${
                    Object.keys(state.sheetEdits || {}).length ? "" : "disabled"
                  }>수정 저장</button>`
                : ""
            }
          </div>
        </div>
        <div class="sheet-display-controls">
          <label>
            <span>글씨 크기</span>
            <input id="sheet-font-size" type="range" min="12" max="18" step="1" value="${viewSettings.fontSize}" />
            <output id="sheet-font-size-output">${viewSettings.fontSize}px</output>
          </label>
          <button type="button" id="reset-sheet-column-widths" ${hasCustomSheetColumnWidths(columns) ? "" : "disabled"}>열 너비 초기화</button>
          <button type="button" id="clear-sheet-filters" ${sheetFilterCount ? "" : "disabled"}>필터 초기화</button>
        </div>
        <div class="analysis-row-router">
          <div>
            <p class="eyebrow">분석 대상</p>
            <h2>행 단위 선택</h2>
            <p class="muted">체크한 행만 분석하거나, 전체 자료를 그대로 분석할 수 있습니다. 표 필터 ${sheetFilterCount}개는 분석에도 함께 적용됩니다.</p>
          </div>
          <div class="analysis-row-router-controls">
            <label class="inline-check">
              <input type="radio" name="analysis-row-mode" value="all" ${rowRouter.mode === "all" ? "checked" : ""} />
              전체 자료 사용
            </label>
            <label class="inline-check">
              <input type="radio" name="analysis-row-mode" value="selected" ${rowRouter.mode === "selected" ? "checked" : ""} />
              선택한 행만 사용
            </label>
            <strong id="analysis-row-selection-count">${escapeHtml(analysisRowLabel())}</strong>
            <button type="button" id="clear-analysis-row-selection" ${selectedRows.size ? "" : "disabled"}>행 선택 해제</button>
          </div>
        </div>
        <div class="sheet-wrap" style="--sheet-column-width: ${viewSettings.columnWidth}px; --sheet-font-size: ${viewSettings.fontSize}px; --sheet-table-width: ${tableWidth}px;">
          <table class="sheet-table">
            <colgroup>
              <col class="sheet-row-select-col" style="width: 52px;" />
              <col class="sheet-row-number-col" style="width: 56px;" />
              ${columns
                .map(
                  (column) =>
                    `<col data-sheet-col="${escapeHtml(column.name)}" style="width: ${sheetColumnWidth(column.name)}px;" />`,
                )
                .join("")}
            </colgroup>
            <thead>
              <tr>
                <th class="sheet-row-select-cell">
                  <label class="sheet-row-select-all">
                    <input type="checkbox" id="select-visible-sheet-rows" aria-label="현재 페이지 행 전체 선택" />
                    행
                  </label>
                </th>
                <th>
                  ${
                    sheet.editable && columns.length > 1
                      ? `<label class="sheet-select-all">
                          <input type="checkbox" id="select-all-sheet-columns" aria-label="전체 열 선택" />
                          #
                        </label>`
                      : "#"
                  }
                </th>
                ${columns
                  .map(
                    (column) => `
                      <th data-sheet-column="${escapeHtml(column.name)}" style="--column-width: ${sheetColumnWidth(column.name)}px;">
                        <div class="sheet-column-heading">
                          <label class="sheet-column-title">
                            ${
                              sheet.editable && columns.length > 1
                                ? `<input
                                    type="checkbox"
                                    data-sheet-column-select
                                    value="${escapeHtml(column.name)}"
                                    aria-label="${escapeHtml(column.display_name || column.name)} 열 선택"
                                  />`
                                : ""
                            }
                            <span>${escapeHtml(column.display_name || column.name)}</span>
                          </label>
                          <button
                            type="button"
                            class="sheet-column-resize-handle"
                            data-sheet-column-resize="${escapeHtml(column.name)}"
                            aria-label="${escapeHtml(column.display_name || column.name)} 열 너비 조정"
                            title="끌어서 열 너비 조정"
                          ></button>
                        </div>
                        ${renderSheetColumnFilter(column)}
                      </th>
                    `,
                  )
                  .join("")}
              </tr>
            </thead>
            <tbody>
              ${sheet.rows?.length
                ? sheet.rows
                    .map(
                      (row) => `
                        <tr>
                          <td class="sheet-row-select-cell">
                            <input
                              type="checkbox"
                              data-sheet-row-select
                              value="${Number(row.__row_index)}"
                              aria-label="${Number(row.__row_index) + 1}행 분석 대상 선택"
                              ${selectedRows.has(Number(row.__row_index)) ? "checked" : ""}
                            />
                          </td>
                          <th class="sheet-row-number">${Number(row.__row_index) + 1}</th>
                          ${columns
                            .map((column) => {
                              const value = row[column.name] ?? "";
                              const key = `${row.__row_index}:${column.name}`;
                              const edited = Object.prototype.hasOwnProperty.call(state.sheetEdits || {}, key)
                                ? state.sheetEdits[key]
                                : value;
                              return `
                                <td data-sheet-column="${escapeHtml(column.name)}" style="--column-width: ${sheetColumnWidth(column.name)}px;">
                                  ${
                                    sheet.editable
                                      ? `<input class="sheet-cell-input" data-row-index="${row.__row_index}" data-column="${escapeHtml(
                                          column.name,
                                        )}" value="${escapeHtml(edited)}" />`
                                      : escapeHtml(value)
                                  }
                                </td>
                              `;
                            })
                            .join("")}
                        </tr>
                      `,
                    )
                    .join("")
                : `
                    <tr>
                      <td colspan="${columns.length + 2}" class="muted">표시할 행이 없습니다.</td>
                    </tr>
                  `}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderDerivedVariablePanel() {
    const suggestions = Array.isArray(state.derivedSuggestions) ? state.derivedSuggestions : [];
    return `
      <section class="derived-panel">
        <div>
          <p class="eyebrow">파생변수</p>
          <h2>새 자료 항목 만들기</h2>
          <p class="muted">수식은 {컬럼명}, + - * / ^ &, abs(), round(), sqrt(), left(), right(), mid()를 사용할 수 있습니다.</p>
        </div>
        ${
          suggestions.length
            ? `<div class="derived-suggestion-list">
                ${suggestions
                  .map(
                    (item, index) => `
                      <article class="option-card">
                        <h3>${escapeHtml(item.label || item.display_name || item.new_column)}</h3>
                        <p>${escapeHtml(item.why || item.description || "")}</p>
                        <code>${escapeHtml(item.formula || "")}</code>
                        <button type="button" class="primary" data-derived-index="${index}">이 파생변수 만들기</button>
                      </article>
                    `,
                  )
                  .join("")}
              </div>`
            : `<p class="muted">현재 자료 구조에서는 AI가 꼭 필요한 파생변수를 찾지 못했습니다.</p>`
        }
        <form id="manual-derived-form" class="custom-analysis-form">
          <div class="custom-analysis-fields">
            ${renderAnalysisField("새 항목 이름", `<input id="derived-column-name" maxlength="80" placeholder="예: rate_percent" />`)}
            ${renderAnalysisField("표시명", `<input id="derived-display-name" maxlength="80" placeholder="예: 비율(%)" />`)}
          </div>
          ${renderAnalysisField(
            "수식",
            `<input id="derived-formula" maxlength="500" placeholder="left({code}, 2) & '-' & sqrt({value})" />`,
          )}
          <div class="actions">
            <button type="submit" class="primary">수식으로 파생변수 만들기</button>
          </div>
        </form>
      </section>
    `;
  }

  function renderAnalysisWorkspace() {
    const hasResult = Boolean(latestAnalysisResult());
    const runOpen = hasResult ? Boolean(state.analysisRunOpen) : true;
    view.innerHTML = `
      ${renderAnalysisResultsSection()}
      <details class="analysis-run-panel" id="analysis-run-panel" ${runOpen ? "open" : ""}>
        <summary>${hasResult ? "다른 방식으로 한 번 더 분석하기" : "분석 실행하기"}</summary>
        <section>
          <h2>자료 항목</h2>
          ${renderSourceNotes()}
          ${renderColumnMeaningPanel()}
          ${renderColumnCards()}
          <details class="dataset-summary-table">
            <summary>숫자 요약을 표로 보기</summary>
            ${renderDatasetSummary()}
          </details>
        </section>
        ${renderSpreadsheetPanel()}
        ${renderSynthesisPanel()}
        <div class="meta-row">
          <span class="chip school-level-chip">학교급 · ${escapeHtml(schoolLevelLabel())}</span>
          <span class="muted">${escapeHtml(SCHOOL_LEVELS[schoolLevel()]?.summary || "학교급에 맞춘 분석 추천입니다.")}</span>
        </div>
        <div class="card-grid">
          ${state.options
            .map(
              (option, index) => `
                <article class="option-card">
                  <h3>${option.label}</h3>
                  <p>${option.description}</p>
                  <div class="meta-row"><span class="chip">${toolLabel(option.tool_name)}</span></div>
                  <button class="primary" data-option="${index}">실행</button>
                </article>
              `,
            )
            .join("")}
        </div>
        ${renderDerivedVariablePanel()}
        ${renderCustomAnalysisForm()}
      </details>
    `;
    const runPanel = document.getElementById("analysis-run-panel");
    runPanel?.addEventListener("toggle", () => {
      state.analysisRunOpen = runPanel.open;
      StatState.setStudentState(state);
    });
    if (state.customAnalysisTool === "plot_choropleth") ensureMapOptions();
    attachAnalysisResultEvents();
    attachColumnSuggestionEvents();
    attachColumnMeaningEvents();
    attachSynthesisPanelEvents();
    attachSheetEvents();
    attachDerivedEvents();
    view.querySelectorAll("[data-option]").forEach((button) => {
      button.addEventListener("click", () => runAnalysis(Number(button.dataset.option)));
    });
    const toolSelect = document.getElementById("custom-tool-name");
    if (toolSelect) {
      toolSelect.addEventListener("change", () => {
        state.customAnalysisTool = toolSelect.value;
        StatState.setStudentState(state);
        renderAnalysisWorkspace();
      });
    }
    view.querySelectorAll("[data-custom-field]").forEach((control) => {
      control.addEventListener("change", (event) => {
        const value = event.target.multiple
          ? [...event.target.selectedOptions].map((option) => option.value)
          : event.target.value;
        state.customAnalysisFields = {
          ...(state.customAnalysisFields || {}),
          [event.target.dataset.customField]: value,
        };
        StatState.setStudentState(state);
        if (event.target.dataset.customRefresh === "true") renderAnalysisWorkspace();
      });
    });
    const updateAnalysisFilterToggle = (columnName) => {
      const values = [...view.querySelectorAll("[data-analysis-filter-value]")].filter(
        (input) => input.dataset.analysisFilterValue === columnName,
      );
      const toggle = [...view.querySelectorAll("[data-analysis-filter-toggle]")].find(
        (input) => input.dataset.analysisFilterToggle === columnName,
      );
      if (!toggle) return;
      const checked = values.filter((input) => input.checked);
      toggle.checked = values.length > 0 && checked.length === values.length;
      toggle.indeterminate = checked.length > 0 && checked.length < values.length;
    };
    view.querySelectorAll("[data-analysis-filter-toggle]").forEach((toggle) => {
      toggle.addEventListener("change", () => {
        view.querySelectorAll("[data-analysis-filter-value]").forEach((input) => {
          if (input.dataset.analysisFilterValue === toggle.dataset.analysisFilterToggle) {
            input.checked = toggle.checked;
          }
        });
        updateAnalysisFilterToggle(toggle.dataset.analysisFilterToggle);
      });
    });
    view.querySelectorAll("[data-analysis-filter-value]").forEach((input) => {
      input.addEventListener("change", () => updateAnalysisFilterToggle(input.dataset.analysisFilterValue));
    });
    const customForm = document.getElementById("custom-analysis-form");
    if (customForm) customForm.addEventListener("submit", runCustomAnalysis);
  }

  function attachSheetEvents() {
    document
      .getElementById("previous-sheet-page")
      ?.addEventListener("click", () =>
        loadSheet(Math.max((state.sheet?.offset || 0) - 100, 0)).catch((error) => StatApi.toast(error.message)),
      );
    document
      .getElementById("next-sheet-page")
      ?.addEventListener("click", () =>
        loadSheet((state.sheet?.offset || 0) + (state.sheet?.rows?.length || 100)).catch((error) =>
          StatApi.toast(error.message),
        ),
      );
    document.getElementById("reload-sheet")?.addEventListener("click", () => loadSheet().catch((error) => StatApi.toast(error.message)));
    document.getElementById("save-sheet-edits")?.addEventListener("click", () =>
      saveSheetEdits().catch((error) => StatApi.toast(error.message)),
    );
    document
      .getElementById("sheet-font-size")
      ?.addEventListener("input", (event) => updateSheetViewSetting("fontSize", event.target.value));
    document.getElementById("reset-sheet-column-widths")?.addEventListener("click", () => resetSheetColumnWidths());
    view.querySelectorAll("[data-sheet-column-resize]").forEach((handle) => {
      handle.addEventListener("pointerdown", startSheetColumnResize);
      handle.addEventListener("keydown", handleSheetColumnResizeKey);
    });
    document.getElementById("clear-sheet-filters")?.addEventListener("click", () => {
      state.sheetFilters = {};
      state.analysisRows = { mode: "all", selected: [] };
      StatState.setStudentState(state);
      loadSheet(0).catch((error) => StatApi.toast(error.message));
    });
    const applyCategoricalFilter = (columnName, selectedValues) => {
      const allValues = categoricalUniqueValues(columnName);
      const uniqueSelected = [...new Set((selectedValues || []).map((value) => String(value ?? "")).filter(Boolean))];
      if (!allValues.length) {
        updateSheetFilter(columnName, { values: uniqueSelected }).catch((error) => StatApi.toast(error.message));
        return;
      }
      if (!uniqueSelected.length) {
        updateSheetFilter(columnName, { values: ["__NO_MATCH__"] }).catch((error) => StatApi.toast(error.message));
        return;
      }
      if (uniqueSelected.length === allValues.length) {
        updateSheetFilter(columnName, { values: [] }).catch((error) => StatApi.toast(error.message));
        return;
      }
      updateSheetFilter(columnName, { values: uniqueSelected }).catch((error) => StatApi.toast(error.message));
    };
    const selectedCategoricalValues = (columnName) =>
      [...view.querySelectorAll("[data-sheet-filter-value]")]
        .filter((input) => input.dataset.sheetFilterValue === columnName && input.checked)
        .map((input) => input.value)
        .filter(Boolean);
    view.querySelectorAll("[data-sheet-filter-select-all]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const columnName = event.currentTarget.dataset.sheetFilterSelectAll;
        if (!columnName) return;
        view.querySelectorAll("[data-sheet-filter-value]").forEach((input) => {
          if (input.dataset.sheetFilterValue === columnName) input.checked = true;
        });
        applyCategoricalFilter(columnName, selectedCategoricalValues(columnName));
      });
    });
    view.querySelectorAll("[data-sheet-filter-clear-selection]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const columnName = event.currentTarget.dataset.sheetFilterClearSelection;
        if (!columnName) return;
        view.querySelectorAll("[data-sheet-filter-value]").forEach((input) => {
          if (input.dataset.sheetFilterValue === columnName) input.checked = false;
        });
        applyCategoricalFilter(columnName, []);
      });
    });
    view.querySelectorAll("[data-sheet-filter-value]").forEach((input) => {
      input.addEventListener("change", (event) => {
        const columnName = event.target.dataset.sheetFilterValue;
        if (!columnName) return;
        applyCategoricalFilter(columnName, selectedCategoricalValues(columnName));
      });
    });
    view.querySelectorAll("[data-sheet-filter-query]").forEach((input) => {
      input.addEventListener("change", (event) => {
        const columnName = event.target.dataset.sheetFilterQuery;
        updateSheetFilter(columnName, { query: event.target.value }).catch((error) => StatApi.toast(error.message));
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          const columnName = event.target.dataset.sheetFilterQuery;
          updateSheetFilter(columnName, { query: event.target.value }).catch((error) => StatApi.toast(error.message));
        }
      });
    });
    const updateAnalysisRowSelectionState = () => {
      const rows = analysisRowState();
      const selected = new Set(rows.selected);
      const visibleCheckboxes = [...view.querySelectorAll("[data-sheet-row-select]")];
      const visibleChecked = visibleCheckboxes.filter((input) => selected.has(Number(input.value)));
      const selectVisible = document.getElementById("select-visible-sheet-rows");
      if (selectVisible) {
        selectVisible.checked = Boolean(visibleCheckboxes.length) && visibleChecked.length === visibleCheckboxes.length;
        selectVisible.indeterminate = visibleChecked.length > 0 && visibleChecked.length < visibleCheckboxes.length;
      }
      document.querySelectorAll('input[name="analysis-row-mode"]').forEach((input) => {
        input.checked = input.value === rows.mode;
      });
      const countTarget = document.getElementById("analysis-row-selection-count");
      if (countTarget) countTarget.textContent = analysisRowLabel();
      const clearButton = document.getElementById("clear-analysis-row-selection");
      if (clearButton) clearButton.disabled = rows.selected.length === 0;
    };
    document.querySelectorAll('input[name="analysis-row-mode"]').forEach((input) => {
      input.addEventListener("change", (event) => {
        state.analysisRows = { ...analysisRowState(), mode: event.target.value === "selected" ? "selected" : "all" };
        StatState.setStudentState(state);
        updateAnalysisRowSelectionState();
      });
    });
    document.getElementById("select-visible-sheet-rows")?.addEventListener("change", (event) => {
      const selected = new Set(selectedAnalysisRowIndices());
      view.querySelectorAll("[data-sheet-row-select]").forEach((checkbox) => {
        const rowIndex = Number(checkbox.value);
        checkbox.checked = event.target.checked;
        if (event.target.checked) {
          selected.add(rowIndex);
        } else {
          selected.delete(rowIndex);
        }
      });
      state.analysisRows = { mode: "selected", selected: [...selected].sort((a, b) => a - b) };
      StatState.setStudentState(state);
      updateAnalysisRowSelectionState();
    });
    view.querySelectorAll("[data-sheet-row-select]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const selected = new Set(selectedAnalysisRowIndices());
        const rowIndex = Number(checkbox.value);
        if (checkbox.checked) {
          selected.add(rowIndex);
        } else {
          selected.delete(rowIndex);
        }
        state.analysisRows = { mode: "selected", selected: [...selected].sort((a, b) => a - b) };
        StatState.setStudentState(state);
        updateAnalysisRowSelectionState();
      });
    });
    document.getElementById("clear-analysis-row-selection")?.addEventListener("click", () => {
      state.analysisRows = { mode: "all", selected: [] };
      view.querySelectorAll("[data-sheet-row-select]").forEach((checkbox) => {
        checkbox.checked = false;
      });
      StatState.setStudentState(state);
      updateAnalysisRowSelectionState();
    });
    updateAnalysisRowSelectionState();
    const updateColumnSelectionState = () => {
      const checkboxes = [...view.querySelectorAll("[data-sheet-column-select]")];
      const checked = checkboxes.filter((input) => input.checked);
      const selectAll = document.getElementById("select-all-sheet-columns");
      if (selectAll) {
        selectAll.checked = Boolean(checkboxes.length) && checked.length === checkboxes.length;
        selectAll.indeterminate = checked.length > 0 && checked.length < checkboxes.length;
      }
      const countTarget = document.getElementById("selected-sheet-columns-count");
      if (countTarget) countTarget.textContent = `선택 ${checked.length}열`;
      const deleteSelected = document.getElementById("delete-selected-columns");
      if (deleteSelected) deleteSelected.disabled = !checked.length;
    };
    document.getElementById("select-all-sheet-columns")?.addEventListener("change", (event) => {
      view.querySelectorAll("[data-sheet-column-select]").forEach((checkbox) => {
        checkbox.checked = event.target.checked;
      });
      updateColumnSelectionState();
    });
    view.querySelectorAll("[data-sheet-column-select]").forEach((checkbox) => {
      checkbox.addEventListener("change", updateColumnSelectionState);
    });
    document.getElementById("delete-selected-columns")?.addEventListener("click", () => {
      const columns = [...view.querySelectorAll("[data-sheet-column-select]:checked")].map((input) => input.value);
      deleteSheetColumns(columns).catch((error) => StatApi.toast(error.message));
    });
    updateColumnSelectionState();
    view.querySelectorAll(".sheet-cell-input").forEach((input) => {
      input.addEventListener("input", (event) => {
        const target = event.target;
        const key = `${target.dataset.rowIndex}:${target.dataset.column}`;
        state.sheetEdits = { ...(state.sheetEdits || {}), [key]: target.value };
        const button = document.getElementById("save-sheet-edits");
        if (button) button.disabled = false;
        StatState.setStudentState(state);
      });
    });
  }

  function attachDerivedEvents() {
    view.querySelectorAll("[data-derived-index]").forEach((button) => {
      button.addEventListener("click", () => {
        const suggestion = state.derivedSuggestions?.[Number(button.dataset.derivedIndex)];
        if (suggestion) applyDerivedColumn(suggestion).catch((error) => StatApi.toast(error.message));
      });
    });
    const form = document.getElementById("manual-derived-form");
    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        applyDerivedColumn({
          new_column: inputValue("derived-column-name"),
          display_name: inputValue("derived-display-name"),
          formula: inputValue("derived-formula"),
          description: "학생이 직접 입력한 수식으로 만든 파생변수",
        }).catch((error) => StatApi.toast(error.message));
      });
    }
  }

  async function updateSheetFilter(columnName, criteria) {
    if (!columnName) return;
    const nextFilters = activeSheetFilters();
    const entry = normalizeFilterMap({ [columnName]: criteria })[columnName];
    if (entry) {
      nextFilters[columnName] = entry;
    } else {
      delete nextFilters[columnName];
    }
    state.sheetFilters = nextFilters;
    state.analysisRows = { mode: "all", selected: [] };
    StatState.setStudentState(state);
    await loadSheet(0);
  }

  function sheetQuery(offset = state.sheet?.offset || 0) {
    const params = new URLSearchParams({ limit: "100", offset: String(offset) });
    const filters = activeSheetFilters();
    if (Object.keys(filters).length) params.set("filters", JSON.stringify(filters));
    return params.toString();
  }

  async function loadSheet(offset = state.sheet?.offset || 0) {
    if (!state.dataset?.dataset_id) return;
    const sheet = await StatApi.request(`/api/datasets/${state.dataset.dataset_id}/sheet?${sheetQuery(offset)}`);
    state = { ...state, sheet, sheetEdits: {} };
    save();
    renderAnalysisWorkspace();
  }

  function applySheetViewSettings() {
    const settings = sheetViewSettings();
    const columns = state.sheet?.columns || state.dataset?.columns || [];
    const wrap = view.querySelector(".sheet-wrap");
    if (wrap) {
      wrap.style.setProperty("--sheet-column-width", `${settings.columnWidth}px`);
      wrap.style.setProperty("--sheet-font-size", `${settings.fontSize}px`);
      wrap.style.setProperty("--sheet-table-width", `${sheetTableWidth(columns)}px`);
    }
    columns.forEach((column) => applySheetColumnWidthToDom(column.name, sheetColumnWidth(column.name)));
    const fontOutput = document.getElementById("sheet-font-size-output");
    if (fontOutput) fontOutput.textContent = `${settings.fontSize}px`;
    const resetButton = document.getElementById("reset-sheet-column-widths");
    if (resetButton) resetButton.disabled = !hasCustomSheetColumnWidths(columns);
  }

  function updateSheetViewSetting(key, value) {
    state.sheetView = { ...sheetViewSettings(), [key]: Number(value) };
    StatState.setStudentState(state);
    applySheetViewSettings();
  }

  function applySheetColumnWidthToDom(columnName, width) {
    const safeWidth = clampNumber(width, 80, 520, sheetViewSettings().columnWidth);
    view.querySelectorAll("[data-sheet-column]").forEach((element) => {
      if (element.dataset.sheetColumn === columnName) {
        element.style.setProperty("--column-width", `${safeWidth}px`);
      }
    });
    view.querySelectorAll("[data-sheet-col]").forEach((element) => {
      if (element.dataset.sheetCol === columnName) {
        element.style.width = `${safeWidth}px`;
      }
    });
    const columns = state.sheet?.columns || state.dataset?.columns || [];
    const wrap = view.querySelector(".sheet-wrap");
    if (wrap) wrap.style.setProperty("--sheet-table-width", `${sheetTableWidth(columns)}px`);
  }

  function updateSheetColumnWidth(columnName, width, persist = true) {
    if (!columnName) return;
    const safeWidth = clampNumber(width, 80, 520, sheetColumnWidth(columnName));
    const settings = sheetViewSettings();
    state.sheetView = {
      ...settings,
      columnWidths: { ...settings.columnWidths, [columnName]: safeWidth },
    };
    applySheetColumnWidthToDom(columnName, safeWidth);
    if (persist) {
      StatState.setStudentState(state);
      applySheetViewSettings();
    }
  }

  function resetSheetColumnWidths() {
    state.sheetView = { ...sheetViewSettings(), columnWidths: {} };
    StatState.setStudentState(state);
    applySheetViewSettings();
  }

  function startSheetColumnResize(event) {
    if (event.button !== 0) return;
    const handle = event.currentTarget;
    const columnName = handle.dataset.sheetColumnResize;
    if (!columnName) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sheetColumnWidth(columnName);
    let nextWidth = startWidth;
    const wrap = view.querySelector(".sheet-wrap");
    wrap?.classList.add("is-resizing-column");
    handle.classList.add("is-active");
    const onPointerMove = (moveEvent) => {
      nextWidth = clampNumber(startWidth + moveEvent.clientX - startX, 80, 520, startWidth);
      updateSheetColumnWidth(columnName, nextWidth, false);
    };
    const stop = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      wrap?.classList.remove("is-resizing-column");
      handle.classList.remove("is-active");
      updateSheetColumnWidth(columnName, nextWidth, true);
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }

  function handleSheetColumnResizeKey(event) {
    if (!["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) return;
    const columnName = event.currentTarget.dataset.sheetColumnResize;
    if (!columnName) return;
    event.preventDefault();
    if (event.key === "Home") {
      updateSheetColumnWidth(columnName, sheetViewSettings().columnWidth, true);
      return;
    }
    const delta = event.key === "ArrowRight" ? 10 : -10;
    updateSheetColumnWidth(columnName, sheetColumnWidth(columnName) + delta, true);
  }

  async function deleteSheetColumns(columnNames) {
    const selected = [...new Set(columnNames)].filter(Boolean);
    if (!selected.length) return;
    const availableColumns = state.dataset?.columns || [];
    if (availableColumns.length - selected.length < 1) {
      StatApi.toast("모든 열을 삭제할 수는 없습니다. 분석에 필요한 열을 하나 이상 남겨 주세요.");
      return;
    }
    const labels = selected.map(
      (columnName) => availableColumns.find((item) => item.name === columnName)?.display_name || columnName,
    );
    const message =
      selected.length === 1
        ? `${labels[0]} 열을 삭제할까요?`
        : `선택한 ${selected.length}개 열(${labels.join(", ")})을 삭제할까요?`;
    if (!window.confirm(message)) return;
    setLoading("선택한 열을 자료에서 삭제하는 중입니다.", {
      label: "삭제할 열",
      text: labels.join(", "),
      items: [{ label: "현재 자료", value: state.dataset?.name || state.dataset?.dataset_id }],
    });
    const payload = await StatApi.request(`/api/datasets/${state.dataset.dataset_id}/columns/delete`, {
      method: "POST",
      body: JSON.stringify({ columns: selected }),
    });
    StatApi.toast(`열 ${selected.length}개를 삭제했습니다.`);
    await refreshDatasetAfterMutation(payload);
  }

  async function refreshDatasetAfterMutation(payload) {
    const datasetId = payload.dataset?.dataset_id || state.dataset?.dataset_id;
    const [schema, summaryData, options, derivedSuggestions] = await Promise.all([
      StatApi.request(`/api/datasets/${datasetId}/schema`),
      StatApi.request(`/api/datasets/${datasetId}/summary`),
      StatApi.request(`/api/projects/${state.project.project_id}/analysis-options`),
      StatApi.request(`/api/projects/${state.project.project_id}/derived-variable-suggestions`),
    ]);
    state = {
      ...state,
      dataset: schema,
      datasetSummary: summaryData,
      sheet: payload.sheet || (await StatApi.request(`/api/datasets/${datasetId}/sheet?limit=100`)),
      sheetEdits: {},
      sheetFilters: {},
      options,
      derivedSuggestions,
      analysis: null,
      hints: null,
      report: null,
    };
    save();
    renderAnalysisWorkspace();
  }

  async function saveSheetEdits() {
    const updates = Object.entries(state.sheetEdits || {}).map(([key, value]) => {
      const [rowIndex, ...columnParts] = key.split(":");
      return { row_index: Number(rowIndex), column: columnParts.join(":"), value };
    });
    if (!updates.length) return;
    setLoading("수정한 자료 값을 저장하는 중입니다.", {
      label: "수정한 값",
      text: `${updates.length}개 셀`,
      items: [{ label: "현재 자료", value: state.dataset?.name || state.dataset?.dataset_id }],
    });
    const payload = await StatApi.request(`/api/datasets/${state.dataset.dataset_id}/sheet`, {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    });
    await refreshDatasetAfterMutation(payload);
  }

  async function applyDerivedColumn(suggestion) {
    if (!suggestion?.new_column || !suggestion?.formula) {
      StatApi.toast("파생변수 이름과 수식을 입력해 주세요.");
      return;
    }
    setLoading("파생변수를 계산해 자료에 추가하는 중입니다.", {
      label: "새 변수",
      text: suggestion.display_name || suggestion.new_column,
      items: [{ label: "수식", value: suggestion.formula }],
    });
    const payload = await StatApi.request(`/api/datasets/${state.dataset.dataset_id}/derived-column`, {
      method: "POST",
      body: JSON.stringify({
        new_column: suggestion.new_column,
        display_name: suggestion.display_name || suggestion.new_column,
        formula: suggestion.formula,
        description: suggestion.description || suggestion.why || "",
      }),
    });
    StatApi.toast(`${payload.derived_column.display_name} 항목을 추가했습니다.`);
    await refreshDatasetAfterMutation(payload);
  }

  async function runAnalysis(index) {
    const option = state.options[index];
    await runAnalysisRequest(option.tool_name, option.tool_args);
  }

  function selectedValues(id) {
    const select = document.getElementById(id);
    return select ? [...select.selectedOptions].map((option) => option.value).filter(Boolean) : [];
  }

  function inputValue(id) {
    return document.getElementById(id)?.value || "";
  }

  function checkedValues(name) {
    return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
  }

  function customAnalysisFilterPayload() {
    const filters = {};
    const emptyColumns = [];
    view.querySelectorAll("[data-analysis-filter-field]").forEach((fieldset) => {
      const columnName = fieldset.dataset.analysisFilterField;
      const total = Number(fieldset.dataset.analysisFilterTotal || 0);
      const checked = [...fieldset.querySelectorAll("[data-analysis-filter-value]:checked")]
        .map((input) => input.value)
        .filter(Boolean);
      if (!columnName || !total) return;
      if (!checked.length) {
        emptyColumns.push(columnName);
      } else if (checked.length < total) {
        filters[columnName] = { values: checked };
      }
    });
    if (emptyColumns.length) {
      const labels = emptyColumns
        .map((columnName) => state.dataset?.columns?.find((column) => column.name === columnName)?.display_name || columnName)
        .join(", ");
      StatApi.toast(`${labels} 범주값을 하나 이상 선택해 주세요.`);
      return null;
    }
    return filters;
  }

  function customAnalysisArgs(toolName) {
    if (toolName === "compute_descriptive_stats") {
      const args = {
        columns: selectedValues("custom-columns"),
        statistics: checkedValues("custom-stat"),
      };
      const groupBy = inputValue("custom-group-by");
      if (groupBy) args.group_by = groupBy;
      return args;
    }
    if (toolName === "plot_line") {
      const xCol = inputValue("custom-x-col");
      const yCol = inputValue("custom-y-col");
      const args = {
        x_col: xCol,
        y_col: yCol,
        title: `${displayName(xCol)}별 ${displayName(yCol)}`,
      };
      const series = inputValue("custom-series");
      if (series) args.multi_series = series;
      return args;
    }
    if (toolName === "plot_bar" || toolName === "plot_pie") {
      const categoryCol = inputValue("custom-category-col");
      const valueCol = inputValue("custom-value-col");
      const args = {
        category_col: categoryCol,
        value_col: valueCol,
        title: `${displayName(categoryCol)}별 ${displayName(valueCol)}`,
      };
      const groupCol = inputValue("custom-group-col");
      if (toolName === "plot_bar" && groupCol) {
        args.group_col = groupCol;
        args.title = `${displayName(categoryCol)}·${displayName(groupCol)}별 ${displayName(valueCol)}`;
      }
      const sortOrder = inputValue("custom-sort-order");
      if (toolName === "plot_bar" && sortOrder) args.sort_order = sortOrder;
      return args;
    }
    if (toolName === "plot_histogram" || toolName === "plot_frequency_polygon") {
      const column = inputValue("custom-column");
      const args = {
        column,
        bins: Number(inputValue("custom-bins") || 8),
      };
      if (toolName === "plot_histogram") args.title = `${displayName(column)} 분포`;
      return args;
    }
    if (toolName === "plot_boxplot") {
      const column = inputValue("custom-column");
      const args = {
        columns: [column],
        title: `${displayName(column)} 상자그림`,
      };
      const groupBy = inputValue("custom-group-by");
      if (groupBy) args.group_by = groupBy;
      return args;
    }
    if (toolName === "plot_scatter") {
      const xCol = inputValue("custom-x-col");
      const yCol = inputValue("custom-y-col");
      return {
        x_col: xCol,
        y_col: yCol,
        show_trendline: Boolean(document.getElementById("custom-trendline")?.checked),
        title: `${displayName(xCol)}와 ${displayName(yCol)} 산점도`,
      };
    }
    if (toolName === "compute_correlation") {
      return {
        x_column: inputValue("custom-x-col"),
        y_column: inputValue("custom-y-col"),
      };
    }
    if (toolName === "compute_grouped_correlation") {
      return {
        x_column: inputValue("custom-x-col"),
        y_column: inputValue("custom-y-col"),
        group_by: inputValue("custom-group-by"),
      };
    }
    if (toolName === "plot_grouped_scatter") {
      const xCol = inputValue("custom-x-col");
      const yCol = inputValue("custom-y-col");
      const groupBy = inputValue("custom-group-by");
      return {
        x_col: xCol,
        y_col: yCol,
        group_by: groupBy,
        title: `${displayName(groupBy)}별 ${displayName(xCol)}와 ${displayName(yCol)}`,
      };
    }
    if (toolName === "plot_map") {
      const colorCol = inputValue("custom-color-col");
      const args = {
        lat_col: inputValue("custom-lat-col"),
        lon_col: inputValue("custom-lon-col"),
        color_col: colorCol,
        title: `지도 위 ${displayName(colorCol)} 분포`,
      };
      const sizeCol = inputValue("custom-size-col");
      if (sizeCol) args.size_col = sizeCol;
      const groupBy = inputValue("custom-group-by");
      if (groupBy) args.group_by = groupBy;
      return args;
    }
    if (toolName === "create_frequency_table") {
      const column = inputValue("custom-column");
      const args = { column };
      const dtype = state.dataset?.columns?.find((item) => item.name === column)?.dtype;
      if (dtype === "numeric") args.bins = Number(inputValue("custom-bins") || 8);
      return args;
    }
    if (toolName === "plot_stem_leaf") {
      return { column: inputValue("custom-column") };
    }
    if (toolName === "create_crosstab") {
      return {
        row_column: inputValue("custom-row-column"),
        col_column: inputValue("custom-col-column"),
        normalize: Boolean(document.getElementById("custom-normalize")?.checked),
      };
    }
    if (toolName === "plot_choropleth") {
      const regionCol = inputValue("custom-region-col");
      const valueCol = inputValue("custom-value-col");
      const level = selectedMapLevel();
      const args = {
        region_col: regionCol,
        value_col: valueCol,
        map_level: level,
        color_scale: selectedColorScale(),
        n_classes: mapClassCount(),
        title: `${displayName(regionCol)}별 ${displayName(valueCol)} 지도`,
      };
      const parent = selectedParentRegion(level);
      if (parent) args.parent_region = parent;
      return args;
    }
    return {};
  }

  async function runCustomAnalysis(event) {
    event.preventDefault();
    const toolName = inputValue("custom-tool-name");
    const filters = customAnalysisFilterPayload();
    if (filters === null) return;
    await runAnalysisRequest(toolName, customAnalysisArgs(toolName), filters);
  }

  async function runAnalysisRequest(toolName, toolArgs, customFilters = {}) {
    const rowIndices = analysisRowPayload();
    if (analysisRowState().mode === "selected" && !rowIndices.length) {
      StatApi.toast("선택한 행만 분석하려면 자료 표에서 분석할 행을 하나 이상 체크해 주세요.");
      return;
    }
    const filters = mergeFilterMaps(activeSheetFilters(), customFilters);
    setLoading("분석을 실행하고 차트를 저장하는 중입니다.", {
      label: "분석 방법",
      text: toolLabel(toolName),
      items: [
        { label: "분석 대상", value: analysisRowLabel() },
        { label: "현재 자료", value: state.dataset?.name || state.dataset?.dataset_id },
        { label: "필터", value: activeSheetFilterCount() ? `${activeSheetFilterCount()}개 적용` : "" },
      ],
    });
    const analysis = await StatApi.request(`/api/projects/${state.project.project_id}/run-analysis`, {
      method: "POST",
      body: JSON.stringify({ tool_name: toolName, tool_args: toolArgs, row_indices: rowIndices, filters }),
    });
    updateTutorialAnalysisProgress(toolName, toolArgs);
    const project = await StatApi.request(`/api/projects/${state.project.project_id}`);
    const analysisHistory = await StatApi.request(`/api/projects/${state.project.project_id}/analyses`);
    state = {
      ...state,
      step: STEP.ANALYSIS,
      analysis,
      analysisHistory,
      project,
      hints: null,
      analysisRunOpen: false,
      coach: null,
    };
    save();
    renderAnalysisWorkspace();
    scrollToAnalysisResult(analysis.analysis_result_id);
  }

  function scrollToAnalysisResult(analysisId) {
    const card = view.querySelector(`[data-analysis-card="${analysisId}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function analysisCardsToShow() {
    const history = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    if (history.length) return [...history].reverse();
    return state.analysis ? [state.analysis] : [];
  }

  function renderInterpretationFeedback(analysis) {
    const feedback = (state.interpretationFeedback || {})[analysis.analysis_result_id];
    if (!feedback) return "";
    const fallback =
      String(feedback.metadata?.source || "").includes("fallback") || Boolean(feedback.metadata?.error_code);
    const list = (title, items) =>
      items?.length
        ? `<h4>${title}</h4><ul class="hint-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : "";
    return `
      <section class="interpretation-feedback">
        <p class="eyebrow">AI 피드백</p>
        <p>${escapeHtml(feedback.summary || "")}</p>
        ${list("잘한 점", feedback.strengths)}
        ${list("보완할 점", feedback.improvements)}
        ${list("다시 생각해 볼 질문", feedback.questions)}
        ${fallback ? `<p class="muted">AI 응답이 불안정해 기본 피드백으로 이어갑니다.</p>` : ""}
        <p class="muted">${escapeHtml(feedback.warning || "")}</p>
      </section>
    `;
  }

  function renderInterpretationHints(analysis) {
    const isLatest = analysis.analysis_result_id === latestAnalysisResult()?.analysis_result_id;
    if (!isLatest) return "";
    const hints = state.hints ? normalizeHints(state.hints) : null;
    if (!hints) {
      return `
        <div class="actions">
          <button type="button" id="load-hints">관찰점·유도 질문 불러오기</button>
          <span class="muted">무엇을 볼지 막막하면 먼저 눌러 보세요.</span>
        </div>
      `;
    }
    const fallback =
      String(hints.metadata?.source || "").includes("fallback") || Boolean(hints.metadata?.error_code);
    return `
      <section class="interpretation-hints">
        <p class="eyebrow">관찰점</p>
        <ul class="hint-list">${hints.observations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <p class="eyebrow">유도 질문</p>
        <ul class="hint-list">${hints.questions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        ${fallback ? `<p class="muted">AI 응답이 불안정해 기본 관찰점으로 이어갑니다. 분석 결과는 그대로 쓸 수 있습니다.</p>` : ""}
        <p class="muted">${escapeHtml(hints.warning)}</p>
      </section>
    `;
  }

  function renderAnalysisResultCard(analysis, index, total) {
    const id = analysis.analysis_result_id;
    const draft = interpretationDraft(analysis);
    const saved = (analysis.interpretation || "").trim();
    const dirty = interpretationIsDirty(analysis);
    return `
      <article class="analysis-result-card" data-analysis-card="${escapeHtml(id)}">
        <header class="analysis-result-head">
          <div>
            <p class="eyebrow">분석 결과 ${total - index} / ${total}</p>
            <h2>${escapeHtml(toolLabel(analysis.tool_name))}</h2>
            <p class="muted">${escapeHtml(analysis.dataset_id)} · 분석 대상 ${escapeHtml(analysisRowLabelFor(analysis))}</p>
          </div>
          ${saved ? `<span class="chip interpretation-saved-chip">해석 저장됨</span>` : ""}
        </header>
        ${renderAnalysisData(analysis.result || {})}
        <p>${escapeHtml(analysis.result?.explanation_hint || analysis.explanation_hint || "")}</p>
        ${renderInterpretationHints(analysis)}
        <section class="interpretation-editor">
          <label class="analysis-field">
            <span>이 결과에 대한 내 해석</span>
            <textarea
              rows="4"
              maxlength="1600"
              placeholder="그래프나 표에서 읽은 사실을 한 문장, 그것이 탐구 질문에 어떤 뜻인지 한 문장으로 적어 보세요."
              data-interpretation-input="${escapeHtml(id)}"
            >${escapeHtml(draft)}</textarea>
          </label>
          <div class="actions">
            <button type="button" data-interpretation-feedback="${escapeHtml(id)}">AI 피드백 받기</button>
            <button type="button" class="primary" data-interpretation-save="${escapeHtml(id)}">해석 저장</button>
            <span class="muted" data-interpretation-status="${escapeHtml(id)}">${
              saved ? (dirty ? "고친 내용이 아직 저장되지 않았습니다." : "저장된 해석입니다.") : "아직 저장한 해석이 없습니다."
            }</span>
          </div>
          ${renderInterpretationFeedback(analysis)}
        </section>
      </article>
    `;
  }

  function renderAnalysisResultsSection() {
    const cards = analysisCardsToShow();
    if (!cards.length) return "";
    const savedCount = cards.filter((analysis) => (analysis.interpretation || "").trim()).length;
    return `
      <section class="analysis-results">
        ${cards.map((analysis, index) => renderAnalysisResultCard(analysis, index, cards.length)).join("")}
        <div class="actions analysis-results-actions">
          <button type="button" class="primary" id="go-report-step">
            ${state.report ? "보고서 단계로 이동" : "보고서 만들기 →"}
          </button>
          <button type="button" id="other-dataset">다른 자료로 분석</button>
          <button type="button" class="danger" id="stop-project">탐구 중단</button>
          <span class="muted">해석 ${savedCount} / ${cards.length}개 저장됨. 저장한 해석은 보고서에서 결과와 함께 실립니다.</span>
        </div>
      </section>
    `;
  }

  function attachAnalysisResultEvents() {
    document.getElementById("load-hints")?.addEventListener("click", loadHints);
    document.getElementById("other-dataset")?.addEventListener("click", () => navigateToStep(STEP.DATA));
    document.getElementById("stop-project")?.addEventListener("click", stopProject);
    document.getElementById("go-report-step")?.addEventListener("click", () =>
      goToReportStep().catch((error) => StatApi.toast(error.message)),
    );
    view.querySelectorAll("[data-interpretation-input]").forEach((textarea) => {
      textarea.addEventListener("input", () => {
        state.interpretationDrafts = {
          ...(state.interpretationDrafts || {}),
          [textarea.dataset.interpretationInput]: textarea.value,
        };
        StatState.setStudentState(state);
      });
    });
    view.querySelectorAll("[data-interpretation-feedback]").forEach((button) => {
      button.addEventListener("click", () =>
        requestInterpretationFeedback(button.dataset.interpretationFeedback).catch((error) =>
          StatApi.toast(error.message),
        ),
      );
    });
    view.querySelectorAll("[data-interpretation-save]").forEach((button) => {
      button.addEventListener("click", () =>
        saveInterpretation(button.dataset.interpretationSave).catch((error) => StatApi.toast(error.message)),
      );
    });
  }

  function analysisById(analysisId) {
    const history = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    return (
      history.find((analysis) => analysis.analysis_result_id === analysisId) ||
      (state.analysis?.analysis_result_id === analysisId ? state.analysis : null)
    );
  }

  function replaceAnalysisInState(updated) {
    const history = (Array.isArray(state.analysisHistory) ? state.analysisHistory : []).map((analysis) =>
      analysis.analysis_result_id === updated.analysis_result_id ? updated : analysis,
    );
    const analysis =
      state.analysis?.analysis_result_id === updated.analysis_result_id ? updated : state.analysis;
    const drafts = { ...(state.interpretationDrafts || {}) };
    delete drafts[updated.analysis_result_id];
    state = { ...state, analysisHistory: history, analysis, interpretationDrafts: drafts };
  }

  async function requestInterpretationFeedback(analysisId) {
    const analysis = analysisById(analysisId);
    if (!analysis) return;
    const text = interpretationDraft(analysis).trim();
    if (!text) {
      StatApi.toast("해석을 먼저 적은 뒤 피드백을 받아 보세요.");
      return;
    }
    const button = view.querySelector(`[data-interpretation-feedback="${analysisId}"]`);
    const status = view.querySelector(`[data-interpretation-status="${analysisId}"]`);
    if (button) {
      button.disabled = true;
      button.textContent = "AI가 해석을 읽는 중...";
    }
    if (status) status.textContent = "피드백을 준비하고 있습니다.";
    try {
      const feedback = await StatApi.request(
        `/api/projects/${state.project.project_id}/analyses/${analysisId}/interpretation-feedback`,
        { method: "POST", body: JSON.stringify({ interpretation_text: text }) },
      );
      state = {
        ...state,
        interpretationFeedback: { ...(state.interpretationFeedback || {}), [analysisId]: feedback },
      };
      save();
      rerenderCurrentStepView();
      scrollToAnalysisResult(analysisId);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "AI 피드백 받기";
      }
    }
  }

  async function saveInterpretation(analysisId) {
    const analysis = analysisById(analysisId);
    if (!analysis) return;
    const text = interpretationDraft(analysis);
    const updated = await StatApi.request(
      `/api/projects/${state.project.project_id}/analyses/${analysisId}/interpretation`,
      { method: "PUT", body: JSON.stringify({ interpretation_text: text }) },
    );
    replaceAnalysisInState(updated);
    if (isTutorialActive() && !tutorial.interpretationSaved && text.trim()) {
      tutorial.interpretationSaved = true;
      persistTutorialState();
    }
    save();
    rerenderCurrentStepView();
    StatApi.toast(text.trim() ? "해석을 저장했습니다." : "해석을 비웠습니다.");
  }

  function rerenderCurrentStepView() {
    if (state.step === STEP.REPORT) {
      renderReportBuilder();
    } else {
      renderAnalysisWorkspace();
    }
  }

  async function goToReportStep() {
    if (!state.report) {
      setLoading("보고서 뼈대를 만드는 중입니다.", {
        label: "탐구 질문",
        text: currentTopicQuestion(),
        items: [{ label: "분석 결과", value: `${analysisCardsToShow().length}건` }],
      });
      const report = await StatApi.request(`/api/projects/${state.project.project_id}/conclusion`, {
        method: "POST",
        body: JSON.stringify({ conclusion_text: "" }),
      });
      const project = await StatApi.request(`/api/projects/${state.project.project_id}`);
      const synthesisHistory = await StatApi.request(`/api/projects/${state.project.project_id}/synthesis`);
      state = {
        ...state,
        report,
        reportLayout: report.layout || null,
        project,
        synthesisHistory,
        coach: null,
      };
    }
    state.step = STEP.REPORT;
    save();
    renderReportBuilder();
  }

  async function loadHints() {
    try {
      const analysis = latestAnalysisResult();
      setLoading("관찰점과 유도 질문을 불러오는 중입니다.", {
        label: "최근 분석",
        text: analysis ? toolLabel(analysis.tool_name) : "분석 결과",
        items: [
          { label: "탐구 질문", value: currentTopicQuestion() },
          { label: "분석 대상", value: analysis?.row_selection?.row_count ? `선택한 ${analysis.row_selection.row_count}행` : "전체 자료" },
        ],
      });
      let hints;
      try {
        hints = await StatApi.request(`/api/projects/${state.project.project_id}/interpretation-hints`, {
          method: "POST",
          body: JSON.stringify({ prompt_text: "분석 결과에 대한 관찰점 요청" }),
        });
      } catch (error) {
        hints = normalizeHints({
          metadata: {
            source: "frontend-fallback",
            error_code: "HINTS_REQUEST_FAILED",
            note: error.message || "AI 질문 생성 요청에 실패했습니다.",
          },
        });
        StatApi.toast("AI 질문 생성이 불안정해 기본 관찰 질문으로 이어갑니다.");
      }
      state = { ...state, step: STEP.ANALYSIS, hints: normalizeHints(hints), coach: null };
      save();
      renderAnalysisWorkspace();
      scrollToAnalysisResult(analysis?.analysis_result_id);
    } catch(e) {
      console.error(e);
      StatApi.toast("관찰점 보기 준비 중 오류가 발생했습니다: " + e.message);
      renderAnalysisWorkspace();
    }
  }

  function normalizeHints(rawHints = {}) {
    rawHints = rawHints && typeof rawHints === "object" ? rawHints : {};
    const fallbackObservations = [
      "분석 결과에서 가장 큰 값과 가장 작은 값을 먼저 확인해 보세요.",
      "비슷한 값끼리 묶이는지, 튀는 값이나 갑작스러운 변화가 있는지 살펴보세요.",
      "그래프나 표가 보여 주는 사실과 아직 추측인 내용을 구분해 보세요.",
    ];
    const fallbackQuestions = [
      "이 결과만으로 내 탐구 질문에 답할 수 있는 사실은 무엇인가요?",
      "결론을 더 분명하게 하려면 어떤 비교나 추가 자료가 필요할까요?",
    ];
    const metadata = rawHints?.metadata && typeof rawHints.metadata === "object" ? rawHints.metadata : {};
    return {
      ...rawHints,
      observations: normalizeHintList(rawHints?.observations, fallbackObservations, 5),
      questions: normalizeHintList(rawHints?.questions, fallbackQuestions, 3),
      warning: rawHints?.warning || "이 안내는 결론을 대신 작성하지 않으며, 관찰과 질문만 제공합니다.",
      metadata: Object.keys(metadata).length ? metadata : { source: "frontend-normalized" },
    };
  }

  function normalizeHintList(value, fallbackItems, limit) {
    const items = Array.isArray(value)
      ? value.map((item) => String(item || "").trim()).filter(Boolean).slice(0, limit)
      : [];
    return items.length ? items : fallbackItems.slice(0, limit);
  }

  const REPORT_BLOCK_TYPE_LABELS = {
    heading: "제목",
    topic: "주제",
    dataset_source: "자료와 출처",
    analysis: "분석",
    synthesis: "종합 비교",
    chart: "그래프",
    image: "그림",
    table: "표",
    conclusion: "결론",
    text_note: "메모",
    highlight: "강조 상자",
    divider: "구분선",
  };
  const REPORT_GRID = {
    cols: 12,
    rows: 20,
    maxPages: 8,
    pageWidthMm: 210,
    pageHeightMm: 297,
    marginMm: 12,
    gapMm: 2,
  };
  REPORT_GRID.colWidthMm = (REPORT_GRID.pageWidthMm - 2 * REPORT_GRID.marginMm) / REPORT_GRID.cols;
  REPORT_GRID.rowHeightMm = (REPORT_GRID.pageHeightMm - 2 * REPORT_GRID.marginMm) / REPORT_GRID.rows;
  const REPORT_BLOCK_DEFAULT_SIZE = {
    heading: { w: 12, h: 2 },
    divider: { w: 12, h: 1 },
    topic: { w: 6, h: 4 },
    dataset_source: { w: 6, h: 5 },
    analysis: { w: 6, h: 7 },
    synthesis: { w: 6, h: 7 },
    chart: { w: 6, h: 7 },
    image: { w: 6, h: 6 },
    table: { w: 6, h: 5 },
    highlight: { w: 6, h: 3 },
    text_note: { w: 4, h: 3 },
    conclusion: { w: 12, h: 4 },
  };
  const REPORT_FONT_OPTIONS = [
    { value: "gothic", label: "고딕(기본)" },
    { value: "myeongjo", label: "명조(바탕)" },
    { value: "barun", label: "바른고딕" },
  ];
  const REPORT_FONT_STACKS = {
    gothic: '"NanumGothic", "Nanum Gothic", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif',
    myeongjo: '"NanumMyeongjo", "Nanum Myeongjo", "Batang", serif',
    barun: '"NanumBarunGothic", "Nanum Barun Gothic", "Malgun Gothic", sans-serif',
  };
  const REPORT_THEME_DEFAULTS = { font: "gothic", primary: "#173f3d", accent: "#287c7a" };
  const REPORT_BLOCK_DEFAULT_TITLES = {
    topic: "탐구 질문",
    dataset_source: "사용한 자료와 출처",
    analysis: "분석 결과",
    synthesis: "자료 종합 비교",
    chart: "그래프",
    conclusion: "결론",
    text_note: "메모",
    highlight: "핵심 발견",
    heading: "",
  };
  const REQUIRED_REPORT_BLOCK_TYPES = ["topic", "dataset_source", "conclusion"];
  const UNCAPTIONED_REPORT_BLOCK_TYPES = ["divider"];
  const FULL_WIDTH_REPORT_BLOCK_TYPES = ["heading", "divider"];
  const REPORT_ACCENTS = [
    { value: "none", label: "기본" },
    { value: "teal", label: "청록" },
    { value: "amber", label: "주황" },
    { value: "violet", label: "보라" },
    { value: "rose", label: "자주" },
  ];
  const REPORT_ACCENT_VALUES = REPORT_ACCENTS.map((accent) => accent.value);

  function newReportBlock(type, { refId = "", title = "", text = "", accent = "none", repeat = false, ...rest } = {}) {
    const size = REPORT_BLOCK_DEFAULT_SIZE[type] || { w: 6, h: 4 };
    const block = {
      block_id: `blk_${Math.random().toString(16).slice(2, 10)}`,
      type,
      ref_id: refId,
      title,
      text,
      accent,
      custom_color: REPORT_THEME_DEFAULTS.accent,
      repeat,
      x: 0,
      y: 0,
      w: FULL_WIDTH_REPORT_BLOCK_TYPES.includes(type) ? REPORT_GRID.cols : size.w,
      h: size.h,
      order: 0,
      ...rest,
    };
    if (type === "image") {
      block.source_kind = block.source_kind || "upload";
      block.alt_text = block.alt_text || "";
      block.fit = block.fit || "contain";
    }
    if (type === "table") {
      block.rows = Array.isArray(block.rows) ? block.rows : [["항목", "값"], ["", ""]];
      block.has_header = block.has_header !== false;
    }
    return block;
  }

  function reportBlockHeading(block) {
    const title = String(block.title || "").trim();
    return title || REPORT_BLOCK_DEFAULT_TITLES[block.type] || "";
  }

  function normalizeReportBlock(block) {
    const type = block.type;
    const size = REPORT_BLOCK_DEFAULT_SIZE[type] || { w: 6, h: 4 };
    const clampInt = (value, fallback, min, max) => {
      const parsed = Number.parseInt(value, 10);
      return Math.max(min, Math.min(Number.isFinite(parsed) ? parsed : fallback, max));
    };
    const w = clampInt(block.w, size.w, 1, REPORT_GRID.cols);
    const h = clampInt(block.h, size.h, 1, REPORT_GRID.rows);
    return {
      ...block,
      title: UNCAPTIONED_REPORT_BLOCK_TYPES.includes(type) ? "" : String(block.title || ""),
      text: UNCAPTIONED_REPORT_BLOCK_TYPES.includes(type) ? "" : String(block.text || ""),
      accent: REPORT_ACCENT_VALUES.includes(block.accent) || block.accent === "custom" ? block.accent : "none",
      custom_color: /^#[0-9a-fA-F]{6}$/.test(block.custom_color || "") ? block.custom_color : REPORT_THEME_DEFAULTS.accent,
      repeat: type === "chart" && Boolean(block.repeat),
      w,
      h,
      x: clampInt(block.x, 0, 0, REPORT_GRID.cols - w),
      y: clampInt(block.y, 0, 0, REPORT_GRID.rows - h),
    };
  }

  function normalizeReportTheme(theme) {
    const raw = theme && typeof theme === "object" ? theme : {};
    const hex = (value, fallback) => (/^#[0-9a-fA-F]{6}$/.test(value || "") ? String(value).toLowerCase() : fallback);
    return {
      font: REPORT_FONT_STACKS[raw.font] ? raw.font : REPORT_THEME_DEFAULTS.font,
      primary: hex(raw.primary, REPORT_THEME_DEFAULTS.primary),
      accent: hex(raw.accent, REPORT_THEME_DEFAULTS.accent),
    };
  }

  function reportLayout() {
    const layout = state.reportLayout || state.report?.layout || {};
    const pages = Array.isArray(layout.pages) && layout.pages.length ? layout.pages : [{ blocks: [] }];
    return {
      version: 3,
      template: ["executive", "story", "poster"].includes(layout.template) ? layout.template : "poster",
      paper: "a4",
      theme: normalizeReportTheme(layout.theme),
      pages: pages.slice(0, REPORT_GRID.maxPages).map((page, index) => ({
        page_id: String(page.page_id || "").startsWith("pg_") ? page.page_id : `pg_${index}_${Math.random().toString(16).slice(2, 8)}`,
        blocks: (Array.isArray(page.blocks) ? page.blocks : [])
          .sort((a, b) => Number(a.order) - Number(b.order))
          .map((block) => normalizeReportBlock(block)),
      })),
    };
  }

  function reportBlocks() {
    return reportLayout().pages.flatMap((page) => page.blocks);
  }

  function updateReportPages(mutate) {
    const layout = reportLayout();
    const pages = mutate(layout.pages.map((page) => ({ ...page, blocks: [...page.blocks] })));
    let order = 0;
    pages.forEach((page) => {
      page.blocks.forEach((block) => {
        order += 1;
        block.order = order;
      });
    });
    state = { ...state, reportLayout: { ...layout, pages } };
  }

  function updateReportLayoutBlocks(mutate) {
    updateReportPages((pages) => pages.map((page) => ({ ...page, blocks: mutate(page.blocks) })));
  }

  function findFreeSpot(blocks, w, h) {
    const occupied = (x, y) =>
      blocks.some((block) => x < block.x + block.w && x + w > block.x && y < block.y + block.h && y + h > block.y);
    for (let y = 0; y <= REPORT_GRID.rows - h; y += 1) {
      for (let x = 0; x <= REPORT_GRID.cols - w; x += 1) {
        if (!occupied(x, y)) return { x, y };
      }
    }
    return null;
  }

  function addReportBlock(type, refId = "", extra = {}) {
    const block = newReportBlock(type, { refId, ...extra });
    const layout = reportLayout();
    const startIndex = Math.max(0, Math.min(state.reportActivePage || 0, layout.pages.length - 1));
    const order = [...layout.pages.keys()].slice(startIndex).concat([...layout.pages.keys()].slice(0, startIndex));
    const target = order.find((index) => findFreeSpot(layout.pages[index].blocks, block.w, block.h));

    if (target === undefined && layout.pages.length >= REPORT_GRID.maxPages) {
      StatApi.toast(`쪽이 모두 찼습니다. 카드를 지우거나 크기를 줄인 뒤 다시 넣어 주세요.`);
      return;
    }
    updateReportPages((pages) => {
      if (target === undefined) {
        pages.push({ page_id: `pg_${Math.random().toString(16).slice(2, 10)}`, blocks: [] });
      }
      const page = pages[target === undefined ? pages.length - 1 : target];
      Object.assign(block, findFreeSpot(page.blocks, block.w, block.h) || { x: 0, y: 0 });
      page.blocks.push(block);
      return pages;
    });
    state = { ...state, reportActivePage: target === undefined ? reportLayout().pages.length - 1 : target };
    renderReportBuilder();
  }

  function addReportPage() {
    const layout = reportLayout();
    if (layout.pages.length >= REPORT_GRID.maxPages) return;
    updateReportPages((pages) => [...pages, { page_id: `pg_${Math.random().toString(16).slice(2, 10)}`, blocks: [] }]);
    state = { ...state, reportActivePage: reportLayout().pages.length - 1 };
    renderReportBuilder();
  }

  function removeReportPage(pageIndex) {
    if (reportLayout().pages.length <= 1) return;
    updateReportPages((pages) => pages.filter((_page, index) => index !== pageIndex));
    state = { ...state, reportActivePage: Math.min(state.reportActivePage || 0, reportLayout().pages.length - 1) };
    renderReportBuilder();
  }

  function setReportActivePage(pageIndex) {
    if ((state.reportActivePage || 0) === pageIndex) return;
    state = { ...state, reportActivePage: pageIndex };
    renderReportBuilder();
  }

  function moveReportBlockToPage(blockId, direction) {
    updateReportPages((pages) => {
      const fromIndex = pages.findIndex((page) => page.blocks.some((block) => block.block_id === blockId));
      const toIndex = fromIndex + (direction === "prev" ? -1 : 1);
      if (fromIndex < 0 || toIndex < 0 || toIndex >= pages.length) return pages;
      const block = pages[fromIndex].blocks.find((candidate) => candidate.block_id === blockId);
      const spot = findFreeSpot(pages[toIndex].blocks, block.w, block.h);
      if (!spot) {
        StatApi.toast("옮길 쪽에 빈 자리가 없습니다. 그 쪽 카드를 줄이거나 옮긴 뒤 다시 시도해 주세요.");
        return pages;
      }
      pages[fromIndex].blocks = pages[fromIndex].blocks.filter((candidate) => candidate.block_id !== blockId);
      Object.assign(block, spot);
      pages[toIndex].blocks.push(block);
      return pages;
    });
    renderReportBuilder();
  }

  function placedReportChartKeys() {
    const keys = new Set();
    reportBlocks().forEach((block) => {
      if (block.type === "chart") {
        keys.add(reportChartKey(block.ref_id));
        return;
      }
      if (block.type !== "analysis" || !block.ref_id) return;
      const owner = (state.analysisHistory || []).find(
        (analysis) => analysis.analysis_result_id === block.ref_id,
      );
      (owner?.chart_urls || []).forEach((url) => keys.add(reportChartKey(url)));
    });
    return keys;
  }

  function addReportChartBlock(url) {
    const alreadyPlaced = placedReportChartKeys().has(reportChartKey(url));
    addReportChartBlockWithDefaults(url, alreadyPlaced);
  }

  function addReportChartBlockWithDefaults(url, repeat) {
    const owner = (state.analysisHistory || []).find((analysis) =>
      (analysis.chart_urls || []).some((candidate) => reportChartKey(candidate) === reportChartKey(url)),
    );
    addReportBlock("chart", url, {
      repeat,
      title: owner ? toolLabel(owner.tool_name) : "",
      text: owner?.result?.data?.alt_text || "",
    });
  }

  function removeReportBlock(blockId) {
    const blocks = reportBlocks();
    const target = blocks.find((block) => block.block_id === blockId);
    if (!target) return;
    if (REQUIRED_REPORT_BLOCK_TYPES.includes(target.type)) {
      if (blocks.filter((block) => block.type === target.type).length <= 1) return;
    }
    updateReportLayoutBlocks((pageBlocks) => pageBlocks.filter((block) => block.block_id !== blockId));
    renderReportBuilder();
  }

  function patchReportBlock(blockId, changes) {
    updateReportLayoutBlocks((blocks) =>
      blocks.map((block) => (block.block_id === blockId ? { ...block, ...changes } : block)),
    );
  }

  function setReportBlockAccent(blockId, accent) {
    patchReportBlock(blockId, { accent });
    renderReportBuilder();
  }

  function setReportTheme(changes) {
    const layout = reportLayout();
    state = { ...state, reportLayout: { ...layout, theme: normalizeReportTheme({ ...layout.theme, ...changes }) } };
  }

  function setReportBlockTitle(blockId, title) {
    patchReportBlock(blockId, { title: title.slice(0, 80) });
  }

  function setReportBlockText(blockId, text) {
    patchReportBlock(blockId, { text: text.slice(0, 2000) });
  }

  function setReportTableCell(blockId, rowIndex, colIndex, value) {
    const block = reportBlocks().find((item) => item.block_id === blockId);
    if (!block) return;
    const rows = (block.rows || []).map((row) => [...row]);
    if (!rows[rowIndex]) return;
    rows[rowIndex][colIndex] = value.slice(0, 120);
    patchReportBlock(blockId, { rows });
  }

  function resizeReportTable(blockId, { rowDelta = 0, colDelta = 0 }) {
    const block = reportBlocks().find((item) => item.block_id === blockId);
    if (!block) return;
    let rows = (block.rows || []).map((row) => [...row]);
    const colCount = Math.max(1, ...rows.map((row) => row.length));
    if (colDelta > 0 && colCount < 8) rows = rows.map((row) => [...row, ""]);
    if (colDelta < 0 && colCount > 1) rows = rows.map((row) => row.slice(0, -1));
    if (rowDelta > 0 && rows.length < 12) rows.push(new Array(rows[0]?.length || 1).fill(""));
    if (rowDelta < 0 && rows.length > 1) rows.pop();
    patchReportBlock(blockId, { rows });
    renderReportBuilder();
  }

  function reportChartUrls() {
    const fromReport = Array.isArray(state.report?.chart_urls) ? state.report.chart_urls : [];
    const fromHistory = Array.isArray(state.analysisHistory)
      ? state.analysisHistory.flatMap((analysis) => analysis.chart_urls || [])
      : [];
    const seen = new Set();
    return [...fromReport, ...fromHistory]
      .map((url) => reportExportChartUrl(url))
      .filter((url) => {
        if (!url) return false;
        const key = reportChartKey(url);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  function reportExportChartUrl(url) {
    if (!url) return "";
    const cleanUrl = String(url);
    return cleanUrl.toLowerCase().endsWith(".svg") ? `${cleanUrl.slice(0, -4)}.png` : cleanUrl;
  }

  function reportChartKey(url) {
    const fileName = String(url).split("?")[0].split("/").pop() || url;
    return fileName.replace(/\.(png|jpe?g|svg)$/i, "");
  }

  function analysisForChartUrl(url) {
    const history = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    const key = reportChartKey(url);
    return history.find((analysis) =>
      (analysis.chart_urls || []).some((chartUrl) => reportChartKey(chartUrl) === key),
    );
  }

  function reportChartLabel(url, index) {
    const owner = analysisForChartUrl(url);
    if (!owner) return `그래프 ${index + 1}`;
    return `${index + 1}. ${toolLabel(owner.tool_name)} · ${owner.dataset_id}`;
  }

  function reportConclusionText() {
    const draft = state.reportConclusionDraft;
    return draft === undefined || draft === null ? state.report?.conclusion_text || "" : draft;
  }

  function interpretationsAsConclusionDraft() {
    return (Array.isArray(state.analysisHistory) ? state.analysisHistory : [])
      .map((analysis) => (analysis.interpretation || "").trim())
      .filter(Boolean)
      .join("\n\n");
  }

  function reportBlockHeadingHtml(block, fallback = "") {
    const heading = reportBlockHeading(block) || fallback;
    return heading ? `<h3>${escapeHtml(heading)}</h3>` : "";
  }

  function reportBlockCaptionHtml(block) {
    const text = String(block.text || "").trim();
    return text ? `<p class="report-block-caption">${escapeHtml(text)}</p>` : "";
  }

  function reportInterpretationHtml(analysis) {
    const text = analysis ? interpretationDraft(analysis).trim() : "";
    if (!text) return "";
    return `
      <div class="report-interpretation">
        <strong>내 해석</strong>
        <p>${escapeHtml(text)}</p>
      </div>
    `;
  }

  function reportItemContent(type, block) {
    const report = state.report;
    if (type === "heading") {
      const eyebrow = String(block.text || "").trim();
      return `
        ${eyebrow ? `<p class="report-heading-eyebrow">${escapeHtml(eyebrow)}</p>` : ""}
        <h2 class="report-heading-title">${escapeHtml(block.title || report.topic_title)}</h2>
      `;
    }
    if (type === "divider") return `<hr class="report-divider-line" />`;
    if (type === "highlight") {
      return `
        ${reportBlockHeadingHtml(block)}
        <p class="report-highlight-text">${escapeHtml(block.text || "")}</p>
      `;
    }
    if (type === "topic") {
      return `${reportBlockHeadingHtml(block)}<p>${escapeHtml(report.topic_title)}</p>${reportBlockCaptionHtml(block)}`;
    }
    if (type === "dataset_source") {
      const sources = Array.isArray(report.dataset_sources) && report.dataset_sources.length
        ? report.dataset_sources
        : (report.dataset_names?.length ? report.dataset_names : [report.dataset_name]).map((name) => ({ name }));
      return `
        ${reportBlockHeadingHtml(block)}
        <div class="report-source-list">
          ${sources
            .map(
              (source) => `
                <article class="report-source-item">
                  <strong>${escapeHtml(source.name || "자료")}</strong>
                  <dl>
                    <dt>출처</dt>
                    <dd>${escapeHtml(source.source || "출처 확인 필요")}</dd>
                    <dt>출처 메모</dt>
                    <dd>${escapeHtml(source.source_note || "자료 등록 또는 API 수집 정보를 확인해 주세요.")}</dd>
                    <dt>기간·범위</dt>
                    <dd>${escapeHtml([source.time_range, source.geographic_unit].filter(Boolean).join(" · ") || "확인 필요")}</dd>
                    <dt>자료 설명</dt>
                    <dd>${escapeHtml(source.description || "설명 없음")}</dd>
                  </dl>
                </article>
              `,
            )
            .join("")}
        </div>
        ${reportBlockCaptionHtml(block)}
      `;
    }
    if (type === "analysis") {
      const analyses = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
      if (block?.ref_id) {
        const owner = analyses.find((analysis) => analysis.analysis_result_id === block.ref_id);
        if (!owner) {
          return `${reportBlockHeadingHtml(block, "분석")}<p class="muted">분석 결과를 찾을 수 없습니다.</p>`;
        }
        const rowText = owner.row_selection?.row_count
          ? ` · 선택 행 ${formatNumber(owner.row_selection.row_count, false)}개`
          : "";
        return `
          ${reportBlockHeadingHtml(block, toolLabel(owner.tool_name))}
          <p class="muted">${escapeHtml(owner.dataset_id)}${rowText}</p>
          ${renderAnalysisData(owner.result || {})}
          ${reportBlockCaptionHtml(block)}
          ${reportInterpretationHtml(owner)}
        `;
      }
      return `
        ${reportBlockHeadingHtml(block, "분석")}
        <ul>
          ${
            analyses.length
              ? analyses
                  .map((analysis) => {
                    const rowText = analysis.row_selection?.row_count
                      ? ` · 선택 행 ${formatNumber(analysis.row_selection.row_count, false)}개`
                      : "";
                    return `<li>${toolLabel(analysis.tool_name)} · ${escapeHtml(analysis.dataset_id)}${rowText}</li>`;
                  })
                  .join("")
              : `<li>${toolLabel(state.analysis?.tool_name || "")}</li>`
          }
        </ul>
        ${reportBlockCaptionHtml(block)}
      `;
    }
    if (type === "chart") {
      const chartUrls = reportChartUrls();
      const index = Math.max(chartUrls.indexOf(block.ref_id), 0);
      const heading = reportBlockHeading(block);
      const caption = String(block.text || "").trim();
      return `
        <figure class="report-figure">
          ${heading && heading !== "그래프" ? `<h3>${escapeHtml(heading)}</h3>` : ""}
          <img class="analysis-image report-chart" src="${StatApi.chartUrl(block.ref_id)}" alt="${escapeHtml(caption || reportChartLabel(block.ref_id, index))}" />
          <figcaption>${escapeHtml(caption || reportChartLabel(block.ref_id, index))}</figcaption>
        </figure>
        ${reportInterpretationHtml(analysisForChartUrl(block.ref_id))}
      `;
    }
    if (type === "image") {
      if (!block.ref_id) {
        return `${reportBlockHeadingHtml(block)}<p class="muted">왼쪽에서 그림을 올리거나 주소를 넣어 주세요.</p>`;
      }
      const caption = String(block.text || "").trim();
      return `
        <figure class="report-figure report-figure-${escapeHtml(block.fit || "contain")}">
          ${reportBlockHeadingHtml(block)}
          <img class="report-image" src="${StatApi.chartUrl(block.ref_id)}" alt="${escapeHtml(block.alt_text || caption || "보고서 그림")}" />
          ${caption ? `<figcaption>${escapeHtml(caption)}</figcaption>` : ""}
        </figure>
      `;
    }
    if (type === "table") {
      const rows = Array.isArray(block.rows) ? block.rows : [];
      const hasHeader = block.has_header !== false;
      const bodyRows = hasHeader ? rows.slice(1) : rows;
      return `
        ${reportBlockHeadingHtml(block)}
        <table class="report-table">
          ${
            hasHeader && rows[0]
              ? `<thead><tr>${rows[0].map((cell) => `<th>${escapeHtml(cell)}</th>`).join("")}</tr></thead>`
              : ""
          }
          <tbody>
            ${bodyRows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
        ${reportBlockCaptionHtml(block)}
      `;
    }
    if (type === "text_note") {
      return `${reportBlockHeadingHtml(block)}<p>${escapeHtml(block.text || "")}</p>`;
    }
    if (type === "synthesis") {
      const history = Array.isArray(state.synthesisHistory) ? state.synthesisHistory : [];
      const owner = history.find((item) => item.synthesis_result_id === block.ref_id) || history[history.length - 1];
      if (!owner) {
        return `${reportBlockHeadingHtml(block)}<p class="muted">종합 비교 결과를 찾을 수 없습니다.</p>`;
      }
      const datasetLabels = (owner.dataset_ids || []).map((id) => synthesisDatasetLabel(id)).join(", ");
      return `
        ${reportBlockHeadingHtml(block)}
        <p class="muted">${escapeHtml(toolLabel(owner.tool_name))} · ${escapeHtml(datasetLabels)}</p>
        ${renderAnalysisData(owner.result || {})}
        ${reportBlockCaptionHtml(block)}
      `;
    }
    if (type === "conclusion") {
      const text = reportConclusionText().trim();
      return `
        ${reportBlockHeadingHtml(block)}
        <p${text ? "" : ' class="muted"'}>${escapeHtml(text || "아직 결론을 쓰지 않았습니다. 왼쪽 결론 칸에 적어 보세요.")}</p>
        ${reportBlockCaptionHtml(block)}
      `;
    }
    return "";
  }

  function reportBlockCardLabel(block) {
    if (block.type === "chart") {
      const chartUrls = reportChartUrls();
      return reportChartLabel(block.ref_id, Math.max(chartUrls.indexOf(block.ref_id), 0));
    }
    if (block.type === "analysis") {
      if (!block.ref_id) return "전체 분석 요약";
      const owner = (state.analysisHistory || []).find((analysis) => analysis.analysis_result_id === block.ref_id);
      return owner ? `${toolLabel(owner.tool_name)} · ${owner.dataset_id}` : "분석(참조 없음)";
    }
    if (block.type === "synthesis") {
      const owner = (state.synthesisHistory || []).find((item) => item.synthesis_result_id === block.ref_id);
      return owner ? `${toolLabel(owner.tool_name)} · 자료 종합 비교` : "자료 종합 비교";
    }
    return "";
  }

  function renderReportGridItem(block) {
    const accentStyle = block.accent === "custom" ? ` style="--report-accent: ${escapeHtml(block.custom_color)}"` : "";
    return `
      <div class="grid-stack-item" gs-id="${escapeHtml(block.block_id)}"
           gs-x="${block.x}" gs-y="${block.y}" gs-w="${block.w}" gs-h="${block.h}">
        <div class="grid-stack-item-content report-block report-block-${escapeHtml(block.type)} report-accent-${escapeHtml(block.accent || "none")}"${accentStyle}>
          ${reportItemContent(block.type, block)}
        </div>
      </div>
    `;
  }

  function renderReportPreview() {
    const layout = reportLayout();
    const theme = layout.theme;
    const pageStyle = [
      `width:${REPORT_GRID.pageWidthMm}mm`,
      `--report-page-height:${REPORT_GRID.pageHeightMm}mm`,
      `padding:${REPORT_GRID.marginMm}mm`,
      `--report-font:${theme.font ? REPORT_FONT_STACKS[theme.font] : REPORT_FONT_STACKS.gothic}`,
      `--report-primary:${theme.primary}`,
      `--report-theme-accent:${theme.accent}`,
      `--report-row-height:${REPORT_GRID.rowHeightMm}mm`,
    ].join(";");
    return `
      <div class="report-preview report-template-${escapeHtml(layout.template)}">
        ${layout.pages
          .map(
            (page, index) => `
              <div class="report-page-wrap">
                <div class="report-page-label no-print">
                  <span>${index + 1}쪽${(state.reportActivePage || 0) === index ? " · 새 카드가 여기 놓입니다" : ""}</span>
                  <span>
                    <button type="button" data-report-page-activate="${index}" ${(state.reportActivePage || 0) === index ? "disabled" : ""}>이 쪽에 추가</button>
                    <button type="button" class="danger" data-report-page-remove="${index}" ${layout.pages.length <= 1 ? "disabled" : ""}>이 쪽 삭제</button>
                  </span>
                </div>
                <div class="a4-page" style="${pageStyle}">
                  <div class="grid-stack report-grid" data-report-page-index="${index}">
                    ${page.blocks.map((block) => renderReportGridItem(block)).join("")}
                  </div>
                </div>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function mountReportGrids() {
    if (typeof GridStack === "undefined") return;
    reportGrids.forEach((grid) => {
      try {
        grid.destroy(false);
      } catch (error) {
      }
    });
    const grids = [];
    document.querySelectorAll(".report-grid").forEach((element) => {
      const pageIndex = Number(element.dataset.reportPageIndex);
      const grid = GridStack.init(
        {
          column: REPORT_GRID.cols,
          maxRow: REPORT_GRID.rows,
          cellHeight: `${REPORT_GRID.rowHeightMm}mm`,
          margin: `${REPORT_GRID.gapMm / 2}mm`,
          float: true,
          animate: false,
          disableOneColumnMode: true,
        },
        element,
      );
      grid.on("change", (event, items) => onReportGridChange(pageIndex, items));
      grids.push(grid);
    });
    reportGrids = grids;
  }

  function onReportGridChange(pageIndex, items) {
    if (!Array.isArray(items) || !items.length) return;
    updateReportPages((pages) => {
      const page = pages[pageIndex];
      if (!page) return pages;
      items.forEach((item) => {
        const block = page.blocks.find((candidate) => candidate.block_id === item.id);
        if (!block) return;
        block.x = item.x;
        block.y = item.y;
        block.w = item.w;
        block.h = item.h;
      });
      return pages;
    });
    StatState.setStudentState(state);
  }

  function reportBlockFieldLabels(type) {
    if (type === "heading") return { title: "포스터 제목", text: "작은 글씨(부제)" };
    if (type === "chart") return { title: "그래프 제목", text: "그래프 설명" };
    if (type === "text_note") return { title: "제목", text: "내용" };
    if (type === "highlight") return { title: "강조 제목", text: "강조 문장" };
    if (type === "analysis") return { title: "결과 제목(비우면 분석 이름)", text: "결과 설명" };
    return { title: "제목(비우면 기본 제목)", text: "설명" };
  }

  function reportBlockBodyEditor(block) {
    if ((block.type === "analysis" || block.type === "chart") && block.ref_id) {
      const owner =
        block.type === "chart"
          ? analysisForChartUrl(block.ref_id)
          : (state.analysisHistory || []).find(
              (analysis) => analysis.analysis_result_id === block.ref_id,
            );
      if (!owner) return "";
      const dirty = interpretationIsDirty(owner);
      return `
        <label class="analysis-field report-interpretation-field">
          <span>이 결과에 대한 내 해석</span>
          <textarea
            maxlength="1600"
            rows="3"
            placeholder="분석 단계에서 저장한 해석이 여기 들어옵니다. 보고서에 맞게 더 다듬어도 됩니다."
            data-report-interpretation="${escapeHtml(owner.analysis_result_id)}"
          >${escapeHtml(interpretationDraft(owner))}</textarea>
        </label>
        <p class="muted report-interpretation-note">
          ${dirty ? "고친 해석은 '구성 저장'을 누를 때 함께 저장됩니다." : "분석 단계에서 저장한 해석입니다."}
        </p>
      `;
    }
    if (block.type === "conclusion") {
      return `
        <label class="analysis-field">
          <span>탐구 전체 결론</span>
          <textarea
            maxlength="1600"
            rows="5"
            placeholder="결과별 해석을 이어서, 탐구 질문에 대한 답을 한 문단으로 정리해 보세요."
            id="report-conclusion-text"
          >${escapeHtml(reportConclusionText())}</textarea>
        </label>
        <div class="actions">
          <button type="button" id="report-conclusion-from-interpretations" ${
            interpretationsAsConclusionDraft() ? "" : "disabled"
          }>저장한 해석 불러오기</button>
          <span class="muted">불러온 내용은 초안일 뿐입니다. 자기 문장으로 다듬어 주세요.</span>
        </div>
      `;
    }
    return "";
  }

  function refreshReportPreview() {
    reportBlocks().forEach((block) => {
      const content = document.querySelector(
        `.grid-stack-item[gs-id="${block.block_id}"] > .grid-stack-item-content`,
      );
      if (content) content.innerHTML = reportItemContent(block.type, block);
    });
  }

  function renderReportImageEditor(block) {
    const id = escapeHtml(block.block_id);
    return `
      <div class="report-image-editor">
        <label class="analysis-field">
          <span>그림 파일 올리기</span>
          <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-report-image-file="${id}" />
        </label>
        <label class="analysis-field">
          <span>또는 그림 주소(https)</span>
          <input type="url" placeholder="https://..." data-report-image-url="${id}" />
        </label>
        <div class="report-block-add-row">
          <button type="button" data-report-image-link="${id}">주소로 넣기</button>
          <select data-report-image-fit="${id}" aria-label="그림 채우기">
            <option value="contain" ${block.fit !== "cover" ? "selected" : ""}>칸 안에 다 보이게</option>
            <option value="cover" ${block.fit === "cover" ? "selected" : ""}>칸을 꽉 채우게</option>
          </select>
        </div>
        <label class="analysis-field">
          <span>대체 텍스트(화면 낭독용)</span>
          <input type="text" maxlength="80" data-report-image-alt="${id}" value="${escapeHtml(block.alt_text || "")}" />
        </label>
      </div>
    `;
  }

  function renderReportTableEditor(block) {
    const id = escapeHtml(block.block_id);
    const rows = Array.isArray(block.rows) ? block.rows : [];
    return `
      <div class="report-table-editor">
        <label class="report-repeat-toggle">
          <input type="checkbox" data-report-table-header="${id}" ${block.has_header !== false ? "checked" : ""} />
          <span>첫 줄을 제목 줄로</span>
        </label>
        <div class="report-table-grid" style="grid-template-columns: repeat(${Math.max(1, rows[0]?.length || 1)}, minmax(0, 1fr))">
          ${rows
            .map((row, rowIndex) =>
              row
                .map(
                  (cell, colIndex) =>
                    `<input type="text" maxlength="120" aria-label="${rowIndex + 1}행 ${colIndex + 1}열"
                       data-report-table-cell="${id}" data-row="${rowIndex}" data-col="${colIndex}" value="${escapeHtml(cell)}" />`,
                )
                .join(""),
            )
            .join("")}
        </div>
        <div class="report-block-add-row">
          <button type="button" data-report-table-resize="${id}" data-row-delta="1">행 추가</button>
          <button type="button" data-report-table-resize="${id}" data-row-delta="-1">행 삭제</button>
          <button type="button" data-report-table-resize="${id}" data-col-delta="1">열 추가</button>
          <button type="button" data-report-table-resize="${id}" data-col-delta="-1">열 삭제</button>
        </div>
      </div>
    `;
  }

  function renderReportBlockCard(block, pageIndex, pageCount) {
    const label = reportBlockCardLabel(block);
    const sameTypeCount = reportBlocks().filter((candidate) => candidate.type === block.type).length;
    const canRemove = !REQUIRED_REPORT_BLOCK_TYPES.includes(block.type) || sameTypeCount > 1;
    const captionable = !UNCAPTIONED_REPORT_BLOCK_TYPES.includes(block.type);
    const fields = reportBlockFieldLabels(block.type);
    const id = escapeHtml(block.block_id);
    return `
      <article class="report-block-card" data-report-block-id="${id}">
        <header>
          <span class="report-block-type">${escapeHtml(REPORT_BLOCK_TYPE_LABELS[block.type] || block.type)}</span>
          ${label ? `<span class="report-block-label">${escapeHtml(label)}</span>` : ""}
          ${block.repeat ? `<span class="report-block-repeat">다시 넣은 그래프</span>` : ""}
          <span class="report-block-place">${block.w}×${block.h} 칸</span>
        </header>
        ${
          captionable
            ? `
              <label class="analysis-field">
                <span>${escapeHtml(fields.title)}</span>
                <input type="text" maxlength="80" data-report-block-title="${id}" value="${escapeHtml(block.title || "")}" />
              </label>
              <label class="analysis-field">
                <span>${escapeHtml(fields.text)}</span>
                <textarea maxlength="2000" rows="2" data-report-block-text="${id}">${escapeHtml(block.text || "")}</textarea>
              </label>
            `
            : ""
        }
        ${block.type === "image" ? renderReportImageEditor(block) : ""}
        ${block.type === "table" ? renderReportTableEditor(block) : ""}
        ${reportBlockBodyEditor(block)}
        <div class="report-block-controls">
          <button type="button" data-report-block-page="prev" data-report-block-target="${id}" ${pageIndex === 0 ? "disabled" : ""}>◀ 앞 쪽으로</button>
          <button type="button" data-report-block-page="next" data-report-block-target="${id}" ${pageIndex >= pageCount - 1 ? "disabled" : ""}>뒤 쪽으로 ▶</button>
          <select data-report-block-accent="${id}" aria-label="강조색">
            ${[...REPORT_ACCENTS, { value: "custom", label: "직접 고른 색" }]
              .map(
                (accent) =>
                  `<option value="${accent.value}" ${(block.accent || "none") === accent.value ? "selected" : ""}>${accent.label}</option>`,
              )
              .join("")}
          </select>
          ${
            block.accent === "custom"
              ? `<input type="color" data-report-block-color="${id}" value="${escapeHtml(block.custom_color)}" aria-label="강조색 직접 고르기" />`
              : ""
          }
          <button type="button" class="danger" data-report-block-remove="${id}" ${canRemove ? "" : "disabled"}>삭제</button>
        </div>
      </article>
    `;
  }

  function renderReportBlockAddControls() {
    const chartUrls = reportChartUrls();
    const placedChartKeys = placedReportChartKeys();
    const allowRepeat = Boolean(state.reportAllowChartRepeat);
    const selectableCharts = allowRepeat
      ? chartUrls
      : chartUrls.filter((url) => !placedChartKeys.has(reportChartKey(url)));
    const analyses = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    return `
      <fieldset class="report-block-add">
        <legend>블록 추가</legend>
        <div class="report-block-add-row">
          <button type="button" id="report-add-heading">제목 추가</button>
          <button type="button" id="report-add-highlight">강조 상자 추가</button>
          <button type="button" id="report-add-divider">구분선 추가</button>
          <button type="button" id="report-add-text-note">메모 추가</button>
          <button type="button" id="report-add-image">그림 추가</button>
          <button type="button" id="report-add-table">표 추가</button>
        </div>
        <div class="report-block-add-row">
          <select id="report-add-chart-select" ${selectableCharts.length ? "" : "disabled"}>
            ${
              selectableCharts.length
                ? selectableCharts
                    .map(
                      (url) =>
                        `<option value="${escapeHtml(url)}">${escapeHtml(reportChartLabel(url, chartUrls.indexOf(url)))}${placedChartKeys.has(reportChartKey(url)) ? " (이미 배치함)" : ""}</option>`,
                    )
                    .join("")
                : `<option value="">배치할 그래프가 없습니다</option>`
            }
          </select>
          <button type="button" id="report-add-chart" ${selectableCharts.length ? "" : "disabled"}>그래프 추가</button>
        </div>
        <div class="report-block-add-row">
          <label class="report-repeat-toggle">
            <input type="checkbox" id="report-allow-chart-repeat" ${allowRepeat ? "checked" : ""} />
            <span>이미 넣은 그래프도 한 번 더 넣기</span>
          </label>
        </div>
        <div class="report-block-add-row">
          <select id="report-add-analysis-select" ${analyses.length ? "" : "disabled"}>
            ${
              analyses.length
                ? analyses
                    .map(
                      (analysis) =>
                        `<option value="${escapeHtml(analysis.analysis_result_id)}">${escapeHtml(toolLabel(analysis.tool_name))} · ${escapeHtml(analysis.dataset_id)}</option>`,
                    )
                    .join("")
                : `<option value="">분석 결과가 없습니다</option>`
            }
          </select>
          <button type="button" id="report-add-analysis" ${analyses.length ? "" : "disabled"}>분석 추가</button>
        </div>
      </fieldset>
    `;
  }

  function renderReportBuilder() {
    if (!state.report) {
      view.innerHTML = `<p class="muted">먼저 결론을 제출하면 보고서를 구성할 수 있습니다.</p>`;
      return;
    }
    const layout = reportLayout();
    const theme = layout.theme;
    view.innerHTML = `
      <section class="report-builder">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">보고서</p>
            <h2>탐구 보고서 구성</h2>
          </div>
          <div class="actions">
            <button id="report-print">인쇄 / PDF로 저장</button>
            <button id="download-report-pdf">PDF 내려받기</button>
            <button id="download-report-pptx">PPTX 내려받기</button>
            <button class="primary" id="go-feedback-step">피드백 확인</button>
          </div>
        </div>
        <div class="report-editor-grid">
          <form id="report-layout-form" class="report-layout-form">
            <fieldset class="report-theme-panel">
              <legend>보고서 모양</legend>
              <label class="analysis-field">
                <span>레이아웃</span>
                <select id="report-template">
                  <option value="poster" ${layout.template === "poster" ? "selected" : ""}>통계 포스터형</option>
                  <option value="executive" ${layout.template === "executive" ? "selected" : ""}>전문 보고서형</option>
                  <option value="story" ${layout.template === "story" ? "selected" : ""}>탐구 이야기형</option>
                </select>
              </label>
              <label class="analysis-field">
                <span>글꼴</span>
                <select id="report-theme-font">
                  ${REPORT_FONT_OPTIONS.map(
                    (font) =>
                      `<option value="${font.value}" ${theme.font === font.value ? "selected" : ""}>${font.label}</option>`,
                  ).join("")}
                </select>
              </label>
              <div class="report-block-add-row">
                <label class="analysis-field">
                  <span>제목 색</span>
                  <input type="color" id="report-theme-primary" value="${escapeHtml(theme.primary)}" />
                </label>
                <label class="analysis-field">
                  <span>강조 색</span>
                  <input type="color" id="report-theme-accent" value="${escapeHtml(theme.accent)}" />
                </label>
              </div>
            </fieldset>
            <section class="report-block-list">
              <h3>구성 블록</h3>
              <p class="muted">
                오른쪽 A4 화면에서 카드를 끌어 옮기고 모서리를 잡아 크기를 바꿀 수 있습니다.
                결과 카드에는 분석 단계에서 저장한 해석이 함께 실리며, 같은 그래프는 직접 다시 넣기 전까지 한 번만 실립니다.
              </p>
              ${layout.pages
                .map(
                  (page, pageIndex) => `
                    <h4 class="report-page-heading">${pageIndex + 1}쪽</h4>
                    ${page.blocks
                      .map((block) => renderReportBlockCard(block, pageIndex, layout.pages.length))
                      .join("") || `<p class="muted">이 쪽은 비어 있습니다.</p>`}
                  `,
                )
                .join("")}
              <div class="report-block-add-row">
                <button type="button" id="report-add-page" ${layout.pages.length >= REPORT_GRID.maxPages ? "disabled" : ""}>쪽 추가</button>
                <span class="muted">새 카드는 ${Math.min((state.reportActivePage || 0) + 1, layout.pages.length)}쪽에 놓입니다.</span>
              </div>
            </section>
            ${renderReportBlockAddControls()}
            <button type="submit" class="primary">구성 저장</button>
          </form>
          ${renderReportPreview()}
        </div>
      </section>
    `;
    mountReportGrids();
    document.getElementById("report-layout-form").addEventListener("submit", saveReportLayout);
    document.getElementById("report-print").addEventListener("click", () => window.print());
    document.getElementById("go-feedback-step").addEventListener("click", () => navigateToStep(STEP.FEEDBACK));
    document.getElementById("download-report-pdf").addEventListener("click", () =>
      downloadReportExport("pdf").catch((error) => StatApi.toast(error.message)),
    );
    document.getElementById("download-report-pptx").addEventListener("click", () =>
      downloadReportExport("pptx").catch((error) => StatApi.toast(error.message)),
    );

    document.querySelectorAll("[data-report-block-page]").forEach((button) => {
      button.addEventListener("click", () =>
        moveReportBlockToPage(button.dataset.reportBlockTarget, button.dataset.reportBlockPage),
      );
    });
    document.querySelectorAll("[data-report-page-remove]").forEach((button) => {
      button.addEventListener("click", () => removeReportPage(Number(button.dataset.reportPageRemove)));
    });
    document.querySelectorAll("[data-report-page-activate]").forEach((button) => {
      button.addEventListener("click", () => setReportActivePage(Number(button.dataset.reportPageActivate)));
    });
    document.getElementById("report-add-page")?.addEventListener("click", addReportPage);
    document.querySelectorAll("[data-report-block-accent]").forEach((select) => {
      select.addEventListener("change", () => setReportBlockAccent(select.dataset.reportBlockAccent, select.value));
    });
    document.querySelectorAll("[data-report-block-color]").forEach((input) => {
      input.addEventListener("change", () => {
        patchReportBlock(input.dataset.reportBlockColor, { custom_color: input.value });
        renderReportBuilder();
      });
    });
    document.getElementById("report-theme-font")?.addEventListener("change", (event) => {
      setReportTheme({ font: event.target.value });
      renderReportBuilder();
    });
    document.getElementById("report-theme-primary")?.addEventListener("change", (event) => {
      setReportTheme({ primary: event.target.value });
      renderReportBuilder();
    });
    document.getElementById("report-theme-accent")?.addEventListener("change", (event) => {
      setReportTheme({ accent: event.target.value });
      renderReportBuilder();
    });
    bindReportImageControls();
    bindReportTableControls();
    document.querySelectorAll("[data-report-block-remove]").forEach((button) => {
      button.addEventListener("click", () => removeReportBlock(button.dataset.reportBlockRemove));
    });
    document.querySelectorAll("[data-report-block-title]").forEach((input) => {
      input.addEventListener("input", () => {
        setReportBlockTitle(input.dataset.reportBlockTitle, input.value);
        refreshReportPreview();
      });
    });
    document.querySelectorAll("[data-report-block-text]").forEach((textarea) => {
      textarea.addEventListener("input", () => {
        setReportBlockText(textarea.dataset.reportBlockText, textarea.value);
        refreshReportPreview();
      });
    });
    document.querySelectorAll("[data-report-interpretation]").forEach((textarea) => {
      textarea.addEventListener("input", () => {
        state.interpretationDrafts = {
          ...(state.interpretationDrafts || {}),
          [textarea.dataset.reportInterpretation]: textarea.value,
        };
        StatState.setStudentState(state);
        refreshReportPreview();
      });
    });
    const conclusionInput = document.getElementById("report-conclusion-text");
    if (conclusionInput) {
      conclusionInput.addEventListener("input", () => {
        state.reportConclusionDraft = conclusionInput.value;
        StatState.setStudentState(state);
        refreshReportPreview();
      });
    }
    document.getElementById("report-conclusion-from-interpretations")?.addEventListener("click", () => {
      state.reportConclusionDraft = interpretationsAsConclusionDraft();
      StatState.setStudentState(state);
      renderReportBuilder();
    });

    const addTextButton = document.getElementById("report-add-text-note");
    if (addTextButton) addTextButton.addEventListener("click", () => addReportBlock("text_note"));
    const addHeadingButton = document.getElementById("report-add-heading");
    if (addHeadingButton) {
      addHeadingButton.addEventListener("click", () =>
        addReportBlock("heading", "", { title: state.report?.topic_title || "", accent: "teal" }),
      );
    }
    const addHighlightButton = document.getElementById("report-add-highlight");
    if (addHighlightButton) {
      addHighlightButton.addEventListener("click", () => addReportBlock("highlight", "", { accent: "amber" }));
    }
    const addDividerButton = document.getElementById("report-add-divider");
    if (addDividerButton) addDividerButton.addEventListener("click", () => addReportBlock("divider"));
    document.getElementById("report-add-image")?.addEventListener("click", () => addReportBlock("image"));
    document.getElementById("report-add-table")?.addEventListener("click", () => addReportBlock("table"));
    const repeatToggle = document.getElementById("report-allow-chart-repeat");
    if (repeatToggle) {
      repeatToggle.addEventListener("change", () => {
        state = { ...state, reportAllowChartRepeat: repeatToggle.checked };
        renderReportBuilder();
      });
    }
    const addChartButton = document.getElementById("report-add-chart");
    if (addChartButton && !addChartButton.disabled) {
      addChartButton.addEventListener("click", () => {
        const select = document.getElementById("report-add-chart-select");
        if (select?.value) addReportChartBlock(select.value);
      });
    }
    const addAnalysisButton = document.getElementById("report-add-analysis");
    if (addAnalysisButton && !addAnalysisButton.disabled) {
      addAnalysisButton.addEventListener("click", () => {
        const select = document.getElementById("report-add-analysis-select");
        if (!select?.value) return;
        const owner = (state.analysisHistory || []).find(
          (analysis) => analysis.analysis_result_id === select.value,
        );
        addReportBlock("analysis", select.value, { title: owner ? toolLabel(owner.tool_name) : "" });
      });
    }
  }

  function bindReportImageControls() {
    document.querySelectorAll("[data-report-image-file]").forEach((input) => {
      input.addEventListener("change", async () => {
        const file = input.files?.[0];
        if (!file) return;
        const body = new FormData();
        body.append("file", file);
        try {
          const result = await StatApi.request(`/api/reports/${state.report.report_id}/images`, { method: "POST", body });
          patchReportBlock(input.dataset.reportImageFile, { ref_id: result.url, source_kind: "upload" });
          renderReportBuilder();
          StatApi.toast("그림을 넣었습니다. '구성 저장'을 눌러야 보고서에 남습니다.");
        } catch (error) {
          StatApi.toast(error.message);
        }
      });
    });
    document.querySelectorAll("[data-report-image-link]").forEach((button) => {
      button.addEventListener("click", async () => {
        const blockId = button.dataset.reportImageLink;
        const urlInput = document.querySelector(`[data-report-image-url="${blockId}"]`);
        if (!urlInput?.value.trim()) return;
        try {
          const result = await StatApi.request(`/api/reports/${state.report.report_id}/images/link`, {
            method: "POST",
            body: JSON.stringify({ external_url: urlInput.value.trim() }),
          });
          patchReportBlock(blockId, { ref_id: result.url, source_kind: "external" });
          renderReportBuilder();
          StatApi.toast("그림을 넣었습니다. '구성 저장'을 눌러야 보고서에 남습니다.");
        } catch (error) {
          StatApi.toast(error.message);
        }
      });
    });
    document.querySelectorAll("[data-report-image-fit]").forEach((select) => {
      select.addEventListener("change", () => {
        patchReportBlock(select.dataset.reportImageFit, { fit: select.value });
        refreshReportPreview();
      });
    });
    document.querySelectorAll("[data-report-image-alt]").forEach((input) => {
      input.addEventListener("input", () => {
        patchReportBlock(input.dataset.reportImageAlt, { alt_text: input.value.slice(0, 80) });
        refreshReportPreview();
      });
    });
  }

  function bindReportTableControls() {
    document.querySelectorAll("[data-report-table-cell]").forEach((input) => {
      input.addEventListener("input", () => {
        setReportTableCell(
          input.dataset.reportTableCell,
          Number(input.dataset.row),
          Number(input.dataset.col),
          input.value,
        );
        refreshReportPreview();
      });
    });
    document.querySelectorAll("[data-report-table-resize]").forEach((button) => {
      button.addEventListener("click", () =>
        resizeReportTable(button.dataset.reportTableResize, {
          rowDelta: Number(button.dataset.rowDelta || 0),
          colDelta: Number(button.dataset.colDelta || 0),
        }),
      );
    });
    document.querySelectorAll("[data-report-table-header]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        patchReportBlock(checkbox.dataset.reportTableHeader, { has_header: checkbox.checked });
        refreshReportPreview();
      });
    });
  }

  async function saveReportLayout(event) {
    event.preventDefault();
    await saveEditedInterpretations();
    const layout = reportLayout();
    const payload = {
      version: 3,
      template: inputValue("report-template"),
      paper: "a4",
      theme: layout.theme,
      pages: layout.pages,
    };
    let report = await StatApi.request(`/api/reports/${state.report.report_id}/layout`, {
      method: "PATCH",
      body: JSON.stringify({ layout: payload }),
    });
    const conclusion = reportConclusionText();
    if (conclusion !== (state.report.conclusion_text || "")) {
      report = await StatApi.request(`/api/projects/${state.project.project_id}/conclusion`, {
        method: "PATCH",
        body: JSON.stringify({ conclusion_text: conclusion }),
      });
    }
    if (isTutorialActive() && !tutorial.reportSaved) {
      tutorial.reportSaved = true;
      persistTutorialState();
    }
    state = { ...state, report, reportLayout: report.layout, reportConclusionDraft: undefined };
    save();
    renderReportBuilder();
    StatApi.toast("보고서 구성을 저장했습니다.");
  }

  async function saveEditedInterpretations() {
    const analyses = Array.isArray(state.analysisHistory) ? state.analysisHistory : [];
    for (const analysis of analyses.filter(interpretationIsDirty)) {
      const updated = await StatApi.request(
        `/api/projects/${state.project.project_id}/analyses/${analysis.analysis_result_id}/interpretation`,
        { method: "PUT", body: JSON.stringify({ interpretation_text: interpretationDraft(analysis) }) },
      );
      replaceAnalysisInState(updated);
    }
  }

  async function downloadReportExport(format) {
    await saveEditedInterpretations();
    await StatApi.download(
      `/api/reports/${state.report.report_id}/export.${format}`,
      `${state.report.report_id}.${format}`,
    );
  }

  function renderSubmitted() {
    const saved = state.report.student_reflection || {};
    view.innerHTML = `
      <h2>피드백</h2>
      <p>보고서 ID: ${state.report.report_id}</p>
      <p class="muted">보고서 단계에서 제출물 구성을 다시 조정할 수 있습니다.</p>
      ${
        state.report.feedback_text
          ? `<h3>교사 피드백</h3><p>${escapeHtml(state.report.feedback_text)}</p>`
          : `<p class="muted">아직 교사 피드백이 없습니다.</p>`
      }
      <hr>
      <h3>자기 성찰 (선택)</h3>
      <p class="muted">이번 탐구를 마치며 스스로 돌아봅니다. 저장하지 않아도 다음 단계로 넘어갈 수 있습니다.</p>
      <form id="reflection-form">
        <label class="analysis-field">
          <span>이번 탐구에서 가장 어려웠던 점은?</span>
          <textarea id="reflection-hard" maxlength="400">${escapeHtml(saved.hard || "")}</textarea>
        </label>
        <label class="analysis-field">
          <span>데이터로 확인한 것과 예상이 달랐던 점은?</span>
          <textarea id="reflection-surprise" maxlength="400">${escapeHtml(saved.surprise || "")}</textarea>
        </label>
        <label class="analysis-field">
          <span>다음에 더 알아보고 싶은 것은?</span>
          <textarea id="reflection-next" maxlength="400">${escapeHtml(saved.next || "")}</textarea>
        </label>
        <div class="actions">
          <button type="submit" id="save-reflection">성찰 저장</button>
        </div>
      </form>
      <div class="actions">
        <button id="back-report">보고서로 돌아가기</button>
        <button id="refresh-report">피드백 확인</button>
        <button class="primary" id="new-project">새 프로젝트</button>
      </div>
    `;
    document.getElementById("back-report").addEventListener("click", () => navigateToStep(STEP.REPORT));
    document.getElementById("refresh-report").addEventListener("click", refreshReport);
    document.getElementById("new-project").addEventListener("click", restart);
    document.getElementById("reflection-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const reflection = {
        hard: document.getElementById("reflection-hard").value.trim(),
        surprise: document.getElementById("reflection-surprise").value.trim(),
        next: document.getElementById("reflection-next").value.trim(),
      };
      try {
        const report = await StatApi.request(`/api/reports/${state.report.report_id}/reflection`, {
          method: "PATCH",
          body: JSON.stringify({ reflection }),
        });
        state = { ...state, report };
        save();
        StatApi.toast("성찰이 저장되었습니다.");
      } catch (error) {
        StatApi.toast(error.message);
      }
    });
  }

  async function refreshReport() {
    const report = await StatApi.request(`/api/reports/${state.report.report_id}`);
    state = { ...state, report };
    save();
    if (state.step === STEP.REPORT) {
      renderReportBuilder();
    } else {
      renderSubmitted();
    }
  }

  async function stopProject() {
    const project = await StatApi.request(`/api/projects/${state.project.project_id}/stop`, {
      method: "POST",
      body: "{}",
    });
    state = { ...state, project };
    save();
    view.innerHTML = `<h2>중단됨</h2><p class="muted">프로젝트 상태가 stopped로 저장되었습니다.</p>`;
  }

  function restart() {
    StatState.clearStudentState();
    state = {
      step: 0,
      project: null,
      projectManagerOpen: false,
      schoolLevel: null,
      startMode: null,
      topic: null,
      datasets: null,
      dataset: null,
      datasetMode: null,
      sharedArtifacts: null,
      datasetSummary: null,
      sheet: null,
      sheetEdits: {},
      sheetFilters: {},
      analysisRows: { mode: "all", selected: [] },
      customAnalysisFields: {},
      derivedSuggestions: null,
      uploadPlan: null,
      kosisPlan: null,
      statApiPlan: null,
      kosisQuestionDraft: "",
      kosisSearchDraft: "",
      statApiQuestionDraft: "",
      options: [],
      analysis: null,
      analysisHistory: [],
      synthesisPanel: defaultSynthesisPanel(),
      synthesisDatasetSchemas: {},
      synthesisHistory: [],
      synthesisResult: null,
      synthesisObservations: null,
      hints: null,
      report: null,
      reportLayout: null,
      coach: null,
      questionDraft: "",
      questionAdvice: null,
      decidedTopicDraft: "",
      interpretationDrafts: {},
      interpretationFeedback: {},
      analysisRunOpen: false,
    };
    resetTutorialProgress();
    tutorialLastTaskId = "";
    renderCurrentState();
  }

  function renderLoginWait() {
    const authError = StatAuth.getAuthError?.();
    if (authError) {
      view.innerHTML = `
        <h2>접근 권한이 없습니다</h2>
        <p class="muted">${escapeHtml(authError)}</p>
        <p class="muted">상단의 로그아웃 버튼을 누른 뒤 화이트리스트에 등록된 Google 계정으로 다시 로그인해 주세요.</p>
      `;
      return;
    }
    view.innerHTML = `
      <h2>Google 로그인이 필요합니다</h2>
      <p class="muted">상단의 Google 로그인 버튼으로 로그인하면 탐구 흐름을 시작할 수 있습니다.</p>
    `;
  }

  function renderCurrentState() {
    renderProgress();
    renderStepControls();
    renderSummary();
    renderStep()
      .then(() => renderTutorialOverlay())
      .catch((error) => StatApi.toast(error.message));
  }

  function renderMergeWizard(importedDatasets) {
    if (!importedDatasets || importedDatasets.length < 2) {
      return `
        <section class="dataset-section">
          <div class="section-title compact-title">
            <div>
              <p class="eyebrow">자료 결합</p>
              <h2>결합할 자료 부족</h2>
            </div>
          </div>
          <p class="muted">결합 기능을 사용하려면 '내 프로젝트에 연결된 가져온 자료'가 최소 2개 이상 있어야 합니다. 검색이나 CSV 업로드를 통해 자료를 먼저 추가해 주세요.</p>
        </section>
      `;
    }

    let content = "";
    if (mergeWizardState.step === 1) {
      content = `
        <div class="merge-step">
          <h3>1단계: 결합할 자료 선택</h3>
          <p class="muted">2개에서 최대 5개의 자료를 선택하세요.</p>
          <div class="project-list">
            ${importedDatasets.map(ds => `
              <label class="project-row-selectable project-row">
                <input type="checkbox" class="merge-ds-checkbox" value="${escapeHtml(ds.dataset_id)}" ${mergeWizardState.selectedDatasetIds.includes(ds.dataset_id) ? "checked" : ""}>
                <div class="project-row-main">
                  <strong>${escapeHtml(ds.name)}</strong>
                  <p class="muted">${escapeHtml(ds.source_note)}</p>
                </div>
              </label>
            `).join("")}
          </div>
          <div class="actions" style="margin-top: 1rem;">
            <button type="button" class="primary" id="merge-step-1-next">다음 단계</button>
          </div>
        </div>
      `;
    } else if (mergeWizardState.step === 2) {
      const p = mergeWizardState.previewResult;
      const feasible = p?.merge_feasible;
      content = `
        <div class="merge-step">
          <h3>2단계: 결합 기준 컬럼 설정 및 미리보기</h3>
          <p class="muted">지역 컬럼과 시점 컬럼을 모두 지정하면 <strong>지역 + 시점이 동시에 일치하는 행끼리만</strong> 결합됩니다. 시점을 지정하지 않으면 지역만 기준으로 삼아 같은 지역의 모든 시점이 교차 결합될 수 있습니다.</p>
          <div class="card-grid">
            ${mergeWizardState.selectedDatasetIds.map(did => {
              const ds = importedDatasets.find(d => d.dataset_id === did);
              return `
                <div class="topic-card">
                  <h4>${escapeHtml(ds.name)}</h4>
                  <label>
                    지역 기준 컬럼:
                    <select class="merge-key-select" data-did="${escapeHtml(did)}">
                      <option value="">-- 선택 --</option>
                      ${ds.columns.map(col => `<option value="${escapeHtml(col.name)}" ${mergeWizardState.keyMappings[did] === col.name ? "selected" : ""}>${escapeHtml(columnOptionLabel(col))}</option>`).join("")}
                    </select>
                  </label>
                  <label style="margin-top: 0.5rem; display: block;">
                    시점 컬럼 (결합 기준에 포함):
                    <select class="merge-time-select" data-did="${escapeHtml(did)}">
                      <option value="">-- 없음 (지역만 기준) --</option>
                      ${ds.columns.map(col => `<option value="${escapeHtml(col.name)}" ${mergeWizardState.timeMappings[did] === col.name ? "selected" : ""}>${escapeHtml(columnOptionLabel(col))}</option>`).join("")}
                    </select>
                  </label>
                </div>
              `;
            }).join("")}
          </div>
          <div class="actions" style="margin-top: 1rem;">
            <button type="button" id="merge-preview-btn">공통 결합 기준 분석</button>
          </div>
          ${p ? `
            <div style="margin-top: 1.5rem;" class="upload-panel">
              <h4>미리보기 결과</h4>
              ${p.warnings && p.warnings.length ? `<ul class="hint-list" style="color: #c0392b;">${p.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul>` : ""}
              <p>${p.composite_key ? "공통 결합 기준 (지역 × 시점)" : "공통 지역 키"}: <strong>${p.common_count}</strong>개</p>
              ${p.composite_key ? "" : p.fuzzy_suggestions && p.fuzzy_suggestions.length ? `
                <p class="muted" style="margin-top: 0.5rem;">지역 이름이 미묘하게 다를 수 있습니다 (예: 서울특별시 vs 서울). AI를 이용해 이름을 정규화해 보세요.</p>
                <button type="button" id="merge-ai-harmonize-btn" style="margin-top: 0.5rem;">AI 지역명 정규화 도우미</button>
              ` : ""}
              <div class="actions" style="margin-top: 1rem;">
                <button type="button" id="merge-step-2-back">뒤로</button>
                <button type="button" class="primary" id="merge-step-2-next" ${!feasible ? "disabled" : ""}>다음 단계 (시점 범위 선택)</button>
              </div>
            </div>
          ` : `
            <div class="actions" style="margin-top: 1rem;">
              <button type="button" id="merge-step-2-back">뒤로</button>
            </div>
          `}
        </div>
      `;
    } else if (mergeWizardState.step === 3) {
      const tp = mergeWizardState.timePoints;
      content = `
        <div class="merge-step">
          <h3>3단계: 포함할 시점 범위 선택 및 결합 실행</h3>
          ${tp && tp.union_count > 0 ? `
            <p>포함할 시점을 선택하세요. 선택하지 않으면 모든 시점을 대상으로 결합합니다.</p>
            <div class="project-list">
              ${tp.union.map(t => `
                <label class="project-row-selectable project-row" style="padding: 0.5rem;">
                  <input type="checkbox" class="merge-time-checkbox" value="${escapeHtml(t)}">
                  ${escapeHtml(t)}
                </label>
              `).join("")}
            </div>
          ` : `<p class="muted">지정된 시점 컬럼이 없거나 공통된 시점이 없습니다.</p>`}
          <div style="margin-top: 1rem;">
            <label>
              조인 방식:
              <select id="merge-join-type">
                <option value="inner">교집합 (Inner Join - 공통 키만)</option>
                <option value="outer">합집합 (Outer Join - 모든 키 포함)</option>
              </select>
            </label>
          </div>
          <div class="actions" style="margin-top: 1.5rem;">
            <button type="button" id="merge-step-3-back">뒤로</button>
            <button type="button" class="primary" id="merge-execute-btn">최종 병합 실행</button>
          </div>
        </div>
      `;
    }

    return `
      <section class="dataset-section">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">다중 자료 결합</p>
            <h2>자료 결합 도우미</h2>
          </div>
        </div>
        ${content}
      </section>
    `;
  }

  function attachMergeEvents(importedDatasets) {
    if (mergeWizardState.step === 1) {
      document.getElementById("merge-step-1-next")?.addEventListener("click", () => {
        const checked = Array.from(document.querySelectorAll(".merge-ds-checkbox:checked")).map(cb => cb.value);
        if (checked.length < 2 || checked.length > 5) {
          StatApi.toast("결합할 자료를 2개 이상 5개 이하로 선택해주세요.");
          return;
        }
        mergeWizardState.selectedDatasetIds = checked;
        checked.forEach(did => {
          if (!mergeWizardState.keyMappings[did]) {
            const ds = importedDatasets.find(d => d.dataset_id === did);
            const maybeRegion = ds?.columns.find(c => c.name.includes("region") || c.name.includes("지역") || c.name.includes("시도"));
            if (maybeRegion) mergeWizardState.keyMappings[did] = maybeRegion.name;
          }
        });
        mergeWizardState.step = 2;
        mergeWizardState.previewResult = null;
        renderCurrentState();
      });
    } else if (mergeWizardState.step === 2) {
      document.querySelectorAll(".merge-key-select").forEach(select => {
        select.addEventListener("change", (e) => {
          mergeWizardState.keyMappings[e.target.dataset.did] = e.target.value;
        });
      });
      document.querySelectorAll(".merge-time-select").forEach(select => {
        select.addEventListener("change", (e) => {
          mergeWizardState.timeMappings[e.target.dataset.did] = e.target.value;
        });
      });
      document.getElementById("merge-step-2-back")?.addEventListener("click", () => {
        mergeWizardState.step = 1;
        renderCurrentState();
      });
      document.getElementById("merge-preview-btn")?.addEventListener("click", async () => {
        const mappings = { ...mergeWizardState.keyMappings };
        for (const did of mergeWizardState.selectedDatasetIds) {
          if (!mappings[did]) {
            StatApi.toast("모든 자료의 지역 기준 컬럼을 선택해주세요.");
            return;
          }
        }
        try {
          setLoading("공통 키를 분석하는 중입니다...", { label: "결합", text: "미리보기" });
          mergeWizardState.previewResult = await StatApi.mergePreview(mergeWizardState.selectedDatasetIds, mappings, { ...mergeWizardState.timeMappings });
          renderCurrentState();
        } catch (e) {
          renderCurrentState();
        }
      });
      document.getElementById("merge-ai-harmonize-btn")?.addEventListener("click", async () => {
        try {
          setLoading("AI가 지역명을 분석하는 중입니다...", { label: "AI 조언", text: "정규화" });
          const res = await StatApi.mergeAiHarmonize(mergeWizardState.selectedDatasetIds, mergeWizardState.keyMappings);
          if (res && res.length > 0) {
            const renameMap = {};
            res.forEach(item => {
              if (item.value_a !== item.suggested_unified) renameMap[item.value_a] = item.suggested_unified;
            });
            if (Object.keys(renameMap).length > 0) {
              await StatApi.mergeHarmonize(mergeWizardState.selectedDatasetIds[0], mergeWizardState.keyMappings[mergeWizardState.selectedDatasetIds[0]], renameMap);
              StatApi.toast(Object.keys(renameMap).length + "개의 지역명을 정규화했습니다.");
              mergeWizardState.previewResult = await StatApi.mergePreview(mergeWizardState.selectedDatasetIds, mergeWizardState.keyMappings, { ...mergeWizardState.timeMappings });
            } else {
              StatApi.toast("수정할 키가 발견되지 않았습니다.");
            }
          } else {
             StatApi.toast("제안할 매핑이 없습니다.");
          }
          renderCurrentState();
        } catch (e) {
          renderCurrentState();
        }
      });
      document.getElementById("merge-step-2-next")?.addEventListener("click", async () => {
        try {
          setLoading("시점 정보를 가져오는 중입니다...", { label: "시점", text: "조회" });
          const tm = {};
          mergeWizardState.selectedDatasetIds.forEach(did => {
            if (mergeWizardState.timeMappings[did]) tm[did] = mergeWizardState.timeMappings[did];
          });
          if (Object.keys(tm).length > 0) {
            mergeWizardState.timePoints = await StatApi.mergeTimePoints(mergeWizardState.selectedDatasetIds, tm);
          } else {
            mergeWizardState.timePoints = null;
          }
          mergeWizardState.step = 3;
          renderCurrentState();
        } catch(e) {
          renderCurrentState();
        }
      });
    } else if (mergeWizardState.step === 3) {
      document.getElementById("merge-step-3-back")?.addEventListener("click", () => {
        mergeWizardState.step = 2;
        renderCurrentState();
      });
      document.getElementById("merge-execute-btn")?.addEventListener("click", async () => {
        const checkedTimes = Array.from(document.querySelectorAll(".merge-time-checkbox:checked")).map(cb => cb.value);
        const joinType = document.getElementById("merge-join-type").value;
        const tm = {};
        mergeWizardState.selectedDatasetIds.forEach(did => {
          if (mergeWizardState.timeMappings[did]) tm[did] = mergeWizardState.timeMappings[did];
        });
        const payload = {
          dataset_ids: mergeWizardState.selectedDatasetIds,
          key_column_mappings: mergeWizardState.keyMappings,
          join_type: joinType,
          time_column_mappings: tm,
          selected_time_points: checkedTimes,
          topic_id: state.project.topic_id
        };
        try {
          setLoading("자료를 병합하는 중입니다...", { label: "실행", text: "자료 병합" });
          const result = await StatApi.mergeExecute(payload);
          StatApi.toast("자료가 병합되었습니다!");
          mergeWizardState.step = 1;
          state.datasetMode = null;
          if (result.dataset && result.dataset.dataset_id) {
            await selectDataset(result.dataset.dataset_id);
          } else {
             renderCurrentState();
          }
        } catch(e) {
          renderCurrentState();
        }
      });
    }
  }

  async function bootstrap() {
    document.getElementById("restart-btn").addEventListener("click", restart);
    document.getElementById("project-manage-btn").addEventListener("click", openProjectManager);
    document.getElementById("tutorial-btn")?.addEventListener("click", () => {
      if (isTutorialActive()) {
        exitTutorial();
      } else {
        startTutorial();
      }
    });
    if (!StatAuth.isStudentPreview?.() && !StatAuth.getAdminActAsUserId?.()) {
      StatState.setRole("student");
    }
    await StatAuth.init();
    if (StatAuth.isFirebaseMode?.() && StatAuth.isSignedIn?.() && StatAuth.getEffectiveRole?.() !== "student") {
      StatAuth.redirectToRoleHome();
      return;
    }
    renderCurrentState();
  }

  window.addEventListener("stat-auth-changed", () => {
    if (StatAuth.isFirebaseMode?.() && StatAuth.isSignedIn?.() && StatAuth.getEffectiveRole?.() !== "student") {
      StatAuth.redirectToRoleHome();
      return;
    }
    renderCurrentState();
  });
  bootstrap().catch((error) => {
    StatApi.toast(error.message);
    renderLoginWait();
  });
})();
