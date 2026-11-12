(async function () {
  await StatAuth.init().catch((error) => LessonKit.showError(error.message));

  const navRole = StatAuth.getNavRole?.();
  if (navRole !== "teacher" && navRole !== "admin") {
    window.location.href = "./index.html";
    return;
  }

  StatApi.setStudentPreviewOverride(true);

  const params = new URLSearchParams(window.location.search);
  const LESSON_ID = params.get("lesson") || "lesson1";
  const TRACK = ["m1", "m3", "high", "gifted"].includes(params.get("track")) ? params.get("track") : "m3";
  const CLASS_PARAM = params.get("class") || "";
  const PREVIEW_ONLY = params.has("track") && !CLASS_PARAM;
  const SCENARIO = params.get("scenario") === "exp2" ? "exp2" : "full";
  const SCENARIO_QS = SCENARIO === "exp2" ? "exp2" : "";

  function openPresent(next) {
    const target = new URLSearchParams();
    target.set("lesson", next.lesson || LESSON_ID);
    target.set("track", next.track || TRACK);
    const scenario = next.scenario !== undefined ? next.scenario : SCENARIO;
    if (scenario === "exp2") target.set("scenario", "exp2");
    if (next.classId) target.set("class", next.classId);
    window.location.search = `?${target.toString()}`;
  }

  function openPinsModal(classId, code, data) {
    document.querySelector(".present-pins-overlay")?.remove();
    const overlay = document.createElement("div");
    overlay.className = "present-pins-overlay";
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) overlay.remove();
    });
    const panel = document.createElement("div");
    panel.className = "present-pins-panel";
    overlay.appendChild(panel);

    const heading = document.createElement("h2");
    heading.textContent = `${classId} 학생 PIN`;
    panel.appendChild(heading);
    const note = document.createElement("p");
    note.className = "lesson-note";
    note.textContent = data.pin_note || "";
    panel.appendChild(note);

    const table = document.createElement("table");
    table.className = "lesson-sheet";
    table.innerHTML = "<thead><tr><th>이름</th><th>PIN</th></tr></thead>";
    const tbody = document.createElement("tbody");
    data.students.forEach((student) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = student.display_name;
      const pin = document.createElement("td");
      pin.className = "teacher-pin-value";
      pin.appendChild(
        LessonKit.createPinToggle(student.pin, { hasPin: student.has_pin, name: student.display_name }),
      );
      tr.appendChild(name);
      tr.appendChild(pin);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    panel.appendChild(table);

    const actions = document.createElement("div");
    actions.className = "present-pins-actions";
    actions.appendChild(LessonKit.createPinShowAllButton(table));
    const printButton = document.createElement("button");
    printButton.type = "button";
    printButton.className = "lesson-next primary";
    printButton.textContent = "잘라 나눠주기 인쇄";
    printButton.addEventListener("click", () => LessonKit.printPinSlips(classId, code, data.students));
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "lesson-connector-fetch";
    closeButton.textContent = "닫기";
    closeButton.addEventListener("click", () => overlay.remove());
    actions.appendChild(printButton);
    actions.appendChild(closeButton);
    panel.appendChild(actions);

    document.body.appendChild(overlay);
  }

  function showChooserChrome(title, topic) {
    document.querySelector(".present-toolbar").hidden = true;
    document.getElementById("present-layout").hidden = true;
    document.getElementById("settings-pickers").hidden = true;
    const titleEl = document.querySelector(".lesson-title");
    const topicEl = document.querySelector(".lesson-topic");
    titleEl.hidden = false;
    topicEl.hidden = false;
    titleEl.textContent = title;
    topicEl.textContent = topic;
  }

  function mountChooserSection() {
    document.querySelector(".present-chooser")?.remove();
    const section = document.createElement("section");
    section.className = "lesson-step present-chooser";
    const main = document.querySelector("main");
    main.insertBefore(section, document.getElementById("guide-host"));
    return section;
  }

  async function renderLessonChooser({ track, scenario, classId }) {
    const courseLabel = classId ? `${classId} 학급` : "학급 없이 미리보기";
    showChooserChrome("차시 고르기", `${courseLabel}에서 진행할 차시를 고르세요.`);
    const section = mountChooserSection();
    section.textContent = "차시를 불러오는 중…";

    let lessons = [];
    try {
      const scenarioQs = scenario === "exp2" ? "exp2" : "";
      const catalog = await StatApi.request(
        `/api/lessons/catalog?track=${encodeURIComponent(track)}&scenario=${encodeURIComponent(scenarioQs)}`,
      );
      lessons = catalog.lessons || [];
    } catch (_error) {
      openPresent({ lesson: "lesson1", track, scenario, classId });
      return;
    }
    section.textContent = "";

    const list = document.createElement("div");
    list.className = "present-lesson-choices";
    lessons.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "present-lesson-choice";
      const number = document.createElement("span");
      number.className = "present-lesson-choice-no";
      number.textContent = `${index + 1}차시`;
      const title = document.createElement("span");
      title.textContent = item.title || item.lesson_id;
      button.appendChild(number);
      button.appendChild(title);
      if (item.mode === "self") {
        const mode = document.createElement("span");
        mode.className = "present-lesson-choice-mode";
        mode.textContent = "자기 진도";
        button.appendChild(mode);
      }
      button.addEventListener("click", () => openPresent({ lesson: item.lesson_id, track, scenario, classId }));
      list.appendChild(button);
    });
    section.appendChild(list);

    const footer = document.createElement("div");
    footer.className = "present-class-actions";
    const back = document.createElement("a");
    back.className = "lesson-connector-fetch";
    back.href = "./present.html";
    back.textContent = "학급 다시 고르기";
    footer.appendChild(back);
    section.appendChild(footer);
  }

  async function renderClassChooser() {
    showChooserChrome("학급 고르기", "수업을 열 학급을 고르세요. 그 학급의 과정(트랙) 내용으로 열립니다.");

    const section = mountChooserSection();
    section.textContent = "학급을 불러오는 중…";

    let classes = [];
    try {
      classes = (await StatApi.request("/api/lessons/roster")).classes || [];
    } catch (_error) {
    }
    section.textContent = "";

    if (!classes.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "아직 개설한 학급이 없습니다. 먼저 학급을 만들고 학생 PIN을 발급해 주세요.";
      section.appendChild(empty);
    } else {
      const table = document.createElement("table");
      table.className = "lesson-sheet";
      table.innerHTML = "<thead><tr><th>학급</th><th>과정</th><th>학생</th><th></th></tr></thead>";
      const tbody = document.createElement("tbody");
      classes.forEach((item) => {
        const tr = document.createElement("tr");
        const courseLabel = `${item.track_label}${item.scenario === "exp2" ? " · 실험수업" : ""}`;
        [item.class_id, courseLabel, `${item.student_count}명`].forEach((value) => {
          const td = document.createElement("td");
          td.textContent = value;
          tr.appendChild(td);
        });
        const action = document.createElement("td");
        action.className = "present-class-actions";

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "lesson-next primary";
        openButton.textContent = "수업 열기";
        openButton.addEventListener("click", () => renderLessonChooser({ track: item.track, scenario: item.scenario, classId: item.class_id }));
        action.appendChild(openButton);

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "lesson-connector-fetch";
        editButton.textContent = "수정";
        editButton.addEventListener("click", () => {
          window.location.href = `./roster.html?class=${encodeURIComponent(item.class_id)}`;
        });
        action.appendChild(editButton);

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "lesson-connector-fetch";
        closeButton.textContent = "폐쇄";
        closeButton.addEventListener("click", async () => {
          const sure = window.confirm(
            `"${item.class_id}" 학급을 폐쇄합니다.\n\n`
              + `학생 계정 ${item.student_count}개와 PIN, 진행 기록이 지워지고 되돌릴 수 없습니다. 계속할까요?`,
          );
          if (!sure) return;
          const typed = window.prompt(`정말 폐쇄하려면 학급 이름(${item.class_id})을 그대로 입력하세요.`);
          if (typed !== item.class_id) {
            if (typed !== null) StatApi.toast("입력한 이름이 달라 취소했습니다.");
            return;
          }
          try {
            await StatApi.request(`/api/lessons/roster/${encodeURIComponent(item.class_id)}`, { method: "DELETE" });
            StatApi.toast(`"${item.class_id}" 학급을 폐쇄했습니다.`);
            await renderClassChooser();
          } catch (error) {
            LessonKit.showError(error.message || "학급을 폐쇄하지 못했습니다.");
          }
        });
        action.appendChild(closeButton);

        tr.appendChild(action);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      section.appendChild(table);
    }

    const footer = document.createElement("div");
    footer.className = "present-class-actions";
    const createLink = document.createElement("a");
    createLink.className = "lesson-next primary";
    createLink.href = "./roster.html";
    createLink.textContent = "새 학급 만들기";
    footer.appendChild(createLink);
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "lesson-connector-fetch";
    previewButton.textContent = "학급 없이 미리보기";
    previewButton.addEventListener("click", () => renderLessonChooser({ track: "m3", scenario: "full", classId: "" }));
    footer.appendChild(previewButton);
    section.appendChild(footer);
  }

  if (!params.has("lesson")) {
    if (CLASS_PARAM) {
      let rosterItem = null;
      try {
        rosterItem = ((await StatApi.request("/api/lessons/roster")).classes || [])
          .find((item) => item.class_id === CLASS_PARAM) || null;
      } catch (_error) {
      }
      if (rosterItem) {
        await renderLessonChooser({ track: rosterItem.track, scenario: rosterItem.scenario, classId: CLASS_PARAM });
        return;
      }
    }
    await renderClassChooser();
    return;
  }

  const lessonSelect = document.getElementById("lesson-select");
  let catalogLessons = [];
  try {
    const catalog = await StatApi.request(`/api/lessons/catalog?track=${encodeURIComponent(TRACK)}&scenario=${encodeURIComponent(SCENARIO_QS)}`);
    catalogLessons = catalog.lessons || [];
  } catch (error) {
    catalogLessons = [{ lesson_id: LESSON_ID, title: "", mode: "" }];
  }
  const lessonNumber = (lessonId) => catalogLessons.findIndex((item) => item.lesson_id === lessonId) + 1;
  const guided = catalogLessons.filter((item) => item.mode !== "self");
  const selfLessons = catalogLessons.filter((item) => item.mode === "self");
  [["카드 진행 (학생 화면 안내 가능)", guided], ["자기 진도 (관찰 모드)", selfLessons]].forEach(
    ([label, items]) => {
      if (!items.length) return;
      const group = document.createElement("optgroup");
      group.label = label;
      items.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.lesson_id;
        option.textContent = `${lessonNumber(item.lesson_id)}차시 · ${item.title}`;
        group.appendChild(option);
      });
      lessonSelect.appendChild(group);
    },
  );
  if (catalogLessons.length && !catalogLessons.some((item) => item.lesson_id === LESSON_ID)) {
    openPresent({ lesson: catalogLessons[0].lesson_id, classId: CLASS_PARAM });
    return;
  }
  lessonSelect.value = LESSON_ID;
  lessonSelect.addEventListener("change", () => {
    openPresent({ lesson: lessonSelect.value, classId: classSelect.value });
  });

  const trackPicker = document.getElementById("track-picker");
  const trackSelect = document.getElementById("track-select");
  trackPicker.hidden = Boolean(CLASS_PARAM);
  trackSelect.value = TRACK;
  const scenarioPicker = document.getElementById("scenario-picker");
  const scenarioSelect = document.getElementById("scenario-select");
  scenarioPicker.hidden = Boolean(CLASS_PARAM);
  scenarioSelect.value = SCENARIO;
  scenarioSelect.addEventListener("change", () => {
    openPresent({ scenario: scenarioSelect.value, classId: "" });
  });
  trackSelect.addEventListener("change", () => {
    openPresent({ track: trackSelect.value, scenario: "full", classId: "" });
  });

  const classSelect = document.getElementById("class-select");
  const pushButton = document.getElementById("push-btn");
  const lockButton = document.getElementById("lock-btn");
  const followButton = document.getElementById("follow-btn");
  const rangeButton = document.getElementById("range-btn");
  const answersButton = document.getElementById("answers-btn");
  const joinButton = document.getElementById("join-btn");
  const progressButton = document.getElementById("progress-btn");
  const pinsButton = document.getElementById("pins-btn");
  const cardListEl = document.getElementById("card-list");
  const deckHost = document.getElementById("deck");
  const boardHost = document.getElementById("board-host");

  let lesson;
  try {
    lesson = await StatApi.request(`/api/lessons/${LESSON_ID}?track=${encodeURIComponent(TRACK)}&scenario=${encodeURIComponent(SCENARIO_QS)}`);
  } catch (error) {
    LessonKit.showError(error.message || "차시를 불러오지 못했습니다.");
    return;
  }

  const promptMetaById = {};
  try {
    const full = await StatApi.request(
      `/api/lessons/definitions/${encodeURIComponent(LESSON_ID)}?track=${encodeURIComponent(lesson.track || TRACK)}&scenario=${encodeURIComponent(SCENARIO_QS)}`,
    );
    (full.definition.steps || []).forEach((step) => {
      (step.cards && step.cards.length ? step.cards : [step]).forEach((card) => {
        (card.prompts || []).forEach((prompt) => {
          if (prompt.prompt_id) promptMetaById[prompt.prompt_id] = prompt;
        });
      });
    });
  } catch (error) {
  }

  const TRACK_LABELS = { m1: "중학교 1학년", m3: "중학교 3학년", high: "고등학교", gifted: "영재학교" };
  const settingsContext = document.getElementById("settings-context");
  function renderSettingsContext() {
    const classLabel = classSelect.value ? `${classSelect.value} 학급` : "학급 없음";
    const number = lessonNumber(LESSON_ID);
    const course = `${TRACK_LABELS[lesson.track] || lesson.track}${lesson.scenario === "exp2" ? ", 실험수업" : ""}`;
    settingsContext.textContent = `${classLabel}, ${number ? `${number}차시 ` : ""}${lesson.definition.title} (${course})`;
  }

  const ANSWERS_KEY = "present-show-answers";
  let showAnswers = localStorage.getItem(ANSWERS_KEY) === "true";
  function applyAnswersVisibility() {
    document.body.classList.toggle("present-answers-visible", showAnswers);
    answersButton.setAttribute("aria-pressed", String(showAnswers));
    answersButton.title = showAnswers
      ? "교사 화면의 정답과 관찰 가이드를 가립니다."
      : "교사 화면에 정답과 관찰 가이드를 보입니다. 화면을 투사 중이면 학생에게도 보입니다.";
  }
  answersButton.addEventListener("click", () => {
    showAnswers = !showAnswers;
    localStorage.setItem(ANSWERS_KEY, String(showAnswers));
    applyAnswersVisibility();
  });
  applyAnswersVisibility();

  const NAV_KEY = "present-nav-collapsed";
  const navToggle = document.getElementById("nav-toggle");
  const revealsTools = document.getElementById("reveals-tools");
  const revealsNote = document.getElementById("reveals-note");
  const revealsClearButton = document.getElementById("reveals-clear-btn");
  let navCollapsed = localStorage.getItem(NAV_KEY) === "true";
  function applyNavCollapsed() {
    document.body.classList.toggle("present-nav-collapsed", navCollapsed);
    navToggle.setAttribute("aria-expanded", String(!navCollapsed));
    navToggle.textContent = navCollapsed ? "▶" : "◀";
    navToggle.title = navCollapsed ? "진행바 펼치기" : "진행바 접기";
    relayoutAll();
  }
  navToggle.addEventListener("click", () => {
    navCollapsed = !navCollapsed;
    localStorage.setItem(NAV_KEY, String(navCollapsed));
    applyNavCollapsed();
  });
  applyNavCollapsed();

  let progress;
  try {
    progress = await StatApi.request("/api/lessons/teacher/progress");
  } catch (error) {
    LessonKit.showError(error.message || "담당 학급 정보를 불러오지 못했습니다.");
    progress = { students: [] };
  }

  const classIds = Array.from(
    new Set(progress.students.map((student) => student.class_id).filter(Boolean)),
  ).sort();

  if (!classIds.length) {
    const empty = document.createElement("p");
    empty.className = "lesson-note";
    empty.textContent = "담당 학급 학생이 아직 없습니다. 학생이 배정되면 여기서 화면을 안내할 수 있습니다.";
    deckHost.replaceWith(empty);
    classSelect.disabled = true;
    return;
  }

  if (classIds.length > 1 || PREVIEW_ONLY) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "학급을 고르세요";
    classSelect.appendChild(placeholder);
  }
  classIds.forEach((classId) => {
    const option = document.createElement("option");
    option.value = classId;
    option.textContent = classId;
    classSelect.appendChild(option);
  });
  if (CLASS_PARAM && classIds.includes(CLASS_PARAM)) {
    classSelect.value = CLASS_PARAM;
  }
  renderSettingsContext();

  const studentsByClass = new Map();
  progress.students.forEach((student) => {
    if (!student.class_id) return;
    if (!studentsByClass.has(student.class_id)) studentsByClass.set(student.class_id, []);
    studentsByClass.get(student.class_id).push(student);
  });

  const flatCards = LessonKit.flattenDeckSteps(lesson.definition.steps);

  let joinInfo = { code: "", joinUrl: "", className: "" };

  async function loadJoinInfo(classId) {
    joinInfo = { code: "", joinUrl: "", className: "" };
    if (!classId) return true;
    try {
      const roster = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}`);
      const rosterScenario = roster.scenario === "exp2" ? "exp2" : "full";
      if ((roster.track && roster.track !== TRACK) || rosterScenario !== SCENARIO) {
        openPresent({ track: roster.track, scenario: rosterScenario, classId });
        return false;
      }
      if (CLASS_PARAM !== classId) {
        const kept = new URLSearchParams(window.location.search);
        kept.set("lesson", LESSON_ID);
        kept.set("track", TRACK);
        if (SCENARIO === "exp2") kept.set("scenario", "exp2");
        kept.set("class", classId);
        window.history.replaceState(null, "", `?${kept.toString()}`);
      }
      joinInfo = { code: roster.code, joinUrl: roster.join_url || "", className: classId };
      joinButton.disabled = false;
    } catch (error) {
    }
    return true;
  }

  let deckApi = null;
  let unwatchSession = null;
  let currentSession = null;
  let refollowTried = false;
  let currentMeta = flatCards[0];
  let showNames = false;
  let largeFont = false;
  const foldedFirstPrompts = new Set();
  let rangeSelection = new Set();
  let lastRangeEditAt = 0;
  const discussUnwatchers = [];

  function stopDiscussWatchers() {
    discussUnwatchers.forEach((unwatch) => unwatch());
    discussUnwatchers.length = 0;
  }

  function highlightCardList() {
    cardListEl.querySelectorAll(".present-card-list-item").forEach((el) => {
      const isActive = Number(el.dataset.step) === currentMeta.stepIndex && Number(el.dataset.card) === currentMeta.cardIndex;
      el.classList.toggle("active", isActive);
    });
  }

  function cardKey(stepIndex, cardIndex) {
    return `${stepIndex}:${cardIndex}`;
  }

  function sessionRangeKeys() {
    const cards = currentSession?.range || [];
    if (!cards.length) return new Set();
    const owner = currentSession?.range_lesson_id;
    if (owner && owner !== lesson.lesson_id) return new Set();
    return new Set(cards.map((item) => cardKey(item.step, item.card)));
  }

  function renderRangeMarks() {
    const activeKeys = sessionRangeKeys();
    cardListEl.querySelectorAll(".present-card-list-item").forEach((row) => {
      const key = cardKey(Number(row.dataset.step), Number(row.dataset.card));
      const picked = rangeSelection.has(key);
      row.classList.toggle("picked", picked);
      row.classList.toggle("in-range", activeKeys.has(key));
      row.querySelector(".present-card-pick")?.setAttribute("aria-pressed", String(picked));
    });
  }

  async function toggleRangePick(meta) {
    const key = cardKey(meta.stepIndex, meta.cardIndex);
    if (rangeSelection.has(key)) rangeSelection.delete(key);
    else rangeSelection.add(key);
    lastRangeEditAt = Date.now();
    renderRangeMarks();
    updateToolbar();
    if (sessionRangeKeys().size) await sendRange(rangeSelection);
  }

  function renderCardList() {
    cardListEl.innerHTML = "";
    flatCards.forEach((meta, index) => {
      const row = document.createElement("div");
      row.className = "present-card-list-item";
      row.dataset.step = String(meta.stepIndex);
      row.dataset.card = String(meta.cardIndex);

      const label = `${index + 1}번 카드, ${meta.stepIndex + 1}단계 ${meta.card.title || meta.card.id}`;
      const pick = document.createElement("button");
      pick.type = "button";
      pick.className = "present-card-pick";
      pick.setAttribute("aria-pressed", "false");
      pick.setAttribute("aria-label", `${label} 학습 범위에 넣기`);
      pick.title = "학습 범위에 넣기";
      pick.addEventListener("click", () => toggleRangePick(meta));
      row.appendChild(pick);

      const open = document.createElement("button");
      open.type = "button";
      open.className = "present-card-open";
      open.title = label;
      const step = document.createElement("span");
      step.className = "present-card-step";
      const num = document.createElement("span");
      num.className = "present-card-num";
      num.textContent = String(index + 1);
      step.appendChild(num);
      step.appendChild(document.createTextNode(`${meta.stepIndex + 1}단계`));
      const title = document.createElement("span");
      title.className = "present-card-title";
      title.textContent = meta.card.title || meta.card.id;
      open.appendChild(step);
      open.appendChild(title);
      open.addEventListener("click", () => {
        deckApi?.goTo(meta.stepIndex, meta.cardIndex);
      });
      row.appendChild(open);

      cardListEl.appendChild(row);
    });
    highlightCardList();
    renderRangeMarks();
  }

  function setToggleState(button, on, title) {
    button.setAttribute("aria-pressed", String(on));
    button.title = title;
  }

  function updateToolbar() {
    const classId = classSelect.value;
    pushButton.disabled = !classId;
    lockButton.disabled = !classId;
    followButton.disabled = !classId;
    pinsButton.hidden = !classId;
    joinButton.disabled = !joinInfo.code;
    progressButton.disabled = !classId;
    const noClass = "먼저 설정에서 학급을 고르세요.";
    pushButton.title = classId ? "학생 화면을 지금 이 카드로 한 번 모읍니다." : noClass;
    progressButton.title = classId
      ? "학생이 어느 카드까지 왔고 무엇을 보냈는지 한눈에 봅니다."
      : noClass;
    joinButton.title = joinInfo.code
      ? `${joinInfo.className} 참여 코드 ${joinInfo.code}를 크게 띄웁니다.`
      : noClass;

    const holding = Boolean(currentSession?.lock);
    setToggleState(lockButton, holding, !classId
      ? noClass
      : holding
        ? "켜짐: 학생이 지금 카드에 머뭅니다. 누르면 풉니다."
        : "학생을 지금 카드에 묶어 둡니다.");

    const following = Boolean(currentSession?.follow);
    setToggleState(followButton, following, !classId
      ? noClass
      : following
        ? "켜짐: 선생님이 넘기면 학생 화면이 따라옵니다. 누르면 끕니다."
        : "선생님이 카드를 넘길 때마다 학생 화면이 따라오게 합니다. 켜면 범위는 꺼집니다.");

    const activeRange = sessionRangeKeys();
    const rangeOn = activeRange.size > 0;
    const picked = rangeSelection.size;
    const rangeCount = rangeOn ? activeRange.size : picked;
    rangeButton.textContent = rangeCount ? `범위 ${rangeCount}장` : "범위";
    rangeButton.disabled = !classId || (!rangeOn && picked === 0);
    setToggleState(rangeButton, rangeOn, !classId
      ? noClass
      : rangeOn
        ? "켜짐: 고른 카드 안에서만 오갑니다. 누르면 풉니다."
        : picked
          ? "고른 카드만 학생이 오갈 수 있게 합니다. 켜면 따라오기는 꺼집니다."
          : "왼쪽 진행바에서 카드를 먼저 고르세요.");
    renderSettingsContext();
    renderRangeMarks();
    renderRevealTools();
  }

  function lessonRevealKeys(definition) {
    const keys = new Set();
    (definition?.steps || []).forEach((step) => {
      (step.cards || [step]).forEach((card) => {
        (card.reveals || []).forEach((reveal) => {
          if (reveal.key) keys.add(reveal.key);
        });
      });
    });
    return keys;
  }

  function sessionOpenRevealKeys() {
    return Object.entries(currentSession?.reveals || {})
      .filter(([, value]) => value)
      .map(([key]) => key);
  }

  function renderRevealTools() {
    const classId = classSelect.value;
    revealsTools.hidden = !classId;
    if (!classId) return;
    const open = sessionOpenRevealKeys();
    const here = lessonRevealKeys(lesson?.definition);
    const inLesson = open.filter((key) => here.has(key)).length;
    revealsNote.textContent = open.length
      ? `이 학급에 켜진 공개 ${open.length}개(이 차시 ${inLesson}개). 새로 들어오는 학생 화면에 처음부터 펼쳐집니다.`
      : "이 학급에 켜진 공개가 없습니다.";
    revealsClearButton.disabled = open.length === 0;
  }

  async function clearReveals(keys = []) {
    const classId = classSelect.value;
    if (!classId) return;
    currentSession = await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/reveals/clear`, {
      method: "PUT",
      body: JSON.stringify({ keys }),
    });
    renderRevealTools();
  }

  revealsClearButton.addEventListener("click", async () => {
    try {
      await clearReveals();
      StatApi.toast("켜진 공개를 모두 껐습니다. 이미 열린 학생 화면은 그대로입니다.");
    } catch (error) {
      LessonKit.showError(error.message || "공개를 끄지 못했습니다.");
    }
  });

  function computeMissing(promptId, responses) {
    const classId = classSelect.value;
    const students = studentsByClass.get(classId) || [];
    const answered = new Set(responses.map((response) => response.user_id));
    return students.filter((student) => !answered.has(student.user_id));
  }

  function positionCard(el, board, container) {
    const width = container.clientWidth || 1;
    const height = container.clientHeight || 1;
    const x = Math.min(Math.max(board?.x ?? 0, 0), 1);
    const y = Math.min(Math.max(board?.y ?? 0, 0), 1);
    el.style.left = `${x * Math.max(width - 220, 0)}px`;
    el.style.top = `${y * Math.max(height - 80, 0)}px`;
  }

  function attachDrag(el, container, response) {
    let dragging = false;
    let moved = false;
    let startX = 0;
    let startY = 0;

    el.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".discuss-card-close") || event.target.closest(".discuss-card-feedback-btn")) return;
      dragging = true;
      moved = false;
      startX = event.clientX;
      startY = event.clientY;
      el.setPointerCapture(event.pointerId);
    });

    el.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      if (Math.abs(event.clientX - startX) > 4 || Math.abs(event.clientY - startY) > 4) moved = true;
      if (!moved) return;
      if (el.parentElement !== container) container.appendChild(el);
      const rect = container.getBoundingClientRect();
      const x = (event.clientX - rect.left) / Math.max(rect.width, 1);
      const y = (event.clientY - rect.top) / Math.max(rect.height, 1);
      el.style.left = `${Math.min(Math.max(x, 0), 1) * Math.max(rect.width - 220, 0)}px`;
      el.style.top = `${Math.min(Math.max(y, 0), 1) * Math.max(rect.height - 80, 0)}px`;
    });

    el.addEventListener("pointerup", async (event) => {
      if (!dragging) return;
      dragging = false;
      el.releasePointerCapture(event.pointerId);
      if (moved) {
        const rect = container.getBoundingClientRect();
        const x = Math.min(Math.max((event.clientX - rect.left) / Math.max(rect.width, 1), 0), 1);
        const y = Math.min(Math.max((event.clientY - rect.top) / Math.max(rect.height, 1), 0), 1);
        try {
          await StatApi.request(`/api/lessons/discuss/responses/${encodeURIComponent(response.response_id)}/board`, {
            method: "PATCH",
            body: JSON.stringify({ x, y }),
          });
        } catch (error) {
          LessonKit.showError(error.message || "카드 위치를 저장하지 못했습니다.");
        }
      } else {
        try {
          await StatApi.request(`/api/lessons/discuss/responses/${encodeURIComponent(response.response_id)}/board`, {
            method: "PATCH",
            body: JSON.stringify({ highlighted: !response.board?.highlighted }),
          });
        } catch (error) {
          LessonKit.showError(error.message || "강조 표시를 바꾸지 못했습니다.");
        }
      }
    });
  }

  function isPlaced(board) {
    if (!board) return false;
    if (board.placed === true) return true;
    return Boolean(board.x) || Boolean(board.y);
  }

  function hasNumber(text) {
    return /\d/.test(String(text || ""));
  }

  async function editFeedback(response) {
    const current = response.feedback || "";
    const next = window.prompt(
      "이 학생에게 보낼 한 줄 피드백입니다. 비우고 확인하면 피드백을 지웁니다.",
      current,
    );
    if (next === null || next.trim() === current.trim()) return;
    try {
      await StatApi.request(`/api/lessons/discuss/responses/${encodeURIComponent(response.response_id)}/feedback`, {
        method: "PATCH",
        body: JSON.stringify({ text: next.trim() }),
      });
      StatApi.toast(next.trim() ? "피드백을 보냈습니다." : "피드백을 지웠습니다.");
    } catch (error) {
      LessonKit.showError(error.message || "피드백을 저장하지 못했습니다.");
    }
  }

  function renderBoard(boardEl, responses) {
    boardEl.innerHTML = "";
    boardEl.classList.toggle("large-font", largeFont);
    boardEl._responses = responses;
    const meta = boardEl._promptMeta || {};

    const showHidden = Boolean(boardEl._showHidden);
    const visible = responses.filter((response) => showHidden || !response.board?.hidden);
    const flow = document.createElement("div");
    flow.className = "discuss-board-flow";
    boardEl.appendChild(flow);

    const sorted = visible.slice().sort((a, b) => {
      if (meta.type === "evidence") {
        const diff = Number(hasNumber(b.text)) - Number(hasNumber(a.text));
        if (diff) return diff;
      }
      return String(a.created_at || "").localeCompare(String(b.created_at || ""));
    });

    sorted
      .forEach((response) => {
        const card = document.createElement("div");
        card.className = "discuss-card";
        if (response.board?.highlighted) card.classList.add("highlighted");
        const isHidden = Boolean(response.board?.hidden);
        if (isHidden) card.classList.add("hidden-card");

        const placed = isPlaced(response.board);
        if (placed) {
          positionCard(card, response.board, boardEl);
        }

        if (showNames) {
          const author = document.createElement("div");
          author.className = "discuss-card-author";
          author.textContent = response.display_name || "이름 없음";
          card.appendChild(author);
        }

        if (response.choice || meta.type === "evidence" || response.after_reveal || response.edited_after_peers) {
          const chips = document.createElement("div");
          chips.className = "discuss-card-chips";
          if (response.choice) {
            const chip = document.createElement("span");
            chip.className = "discuss-chip";
            if (meta.answer && response.choice === meta.answer) chip.classList.add("correct");
            chip.textContent = response.choice;
            chips.appendChild(chip);
          }
          if (response.after_reveal) {
            const chip = document.createElement("span");
            chip.className = "discuss-chip warn";
            chip.textContent = "결과 본 뒤 보냄";
            chips.appendChild(chip);
          }
          if (response.edited_after_peers) {
            const chip = document.createElement("span");
            chip.className = "discuss-chip warn";
            chip.textContent = "친구 의견 본 뒤 고침";
            chips.appendChild(chip);
          }
          if (meta.type === "evidence" && !hasNumber(response.text)) {
            const chip = document.createElement("span");
            chip.className = "discuss-chip warn";
            chip.textContent = "수치 없음";
            chips.appendChild(chip);
          }
          if (chips.childNodes.length) card.appendChild(chips);
        }

        const text = document.createElement("div");
        text.textContent = response.text;
        card.appendChild(text);

        if (response.feedback) {
          const feedback = document.createElement("div");
          feedback.className = "discuss-card-feedback";
          feedback.textContent = `피드백: ${response.feedback}`;
          card.appendChild(feedback);
        }

        const feedbackButton = document.createElement("button");
        feedbackButton.type = "button";
        feedbackButton.className = "discuss-card-feedback-btn";
        feedbackButton.textContent = "피드백";
        feedbackButton.addEventListener("click", (event) => {
          event.stopPropagation();
          editFeedback(response);
        });
        card.appendChild(feedbackButton);

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "discuss-card-close";
        closeButton.textContent = isHidden ? "+" : "×";
        closeButton.title = isHidden ? "다시 보드에 보이기" : "보드에서 숨기기";
        closeButton.addEventListener("click", async (event) => {
          event.stopPropagation();
          try {
            await StatApi.request(`/api/lessons/discuss/responses/${encodeURIComponent(response.response_id)}/board`, {
              method: "PATCH",
              body: JSON.stringify({ hidden: !isHidden }),
            });
          } catch (error) {
            LessonKit.showError(error.message || (isHidden ? "다시 보이지 못했습니다." : "숨기지 못했습니다."));
          }
        });
        card.appendChild(closeButton);

        attachDrag(card, boardEl, response);
        (placed ? boardEl : flow).appendChild(card);
      });
  }

  function relayout(boardEl) {
    if (boardEl && boardEl._responses) renderBoard(boardEl, boardEl._responses);
  }

  function relayoutAll() {
    document.querySelectorAll(".discuss-board").forEach(relayout);
  }

  window.addEventListener("resize", relayoutAll);

  document.addEventListener("fullscreenchange", () => {
    if (document.fullscreenElement) return;
    document.querySelectorAll(".discuss-board-section.board-fullscreen").forEach((section) => {
      section.classList.remove("board-fullscreen");
      const toggle = section.querySelector(".discuss-fullscreen-toggle");
      if (toggle) toggle.textContent = "전체 화면";
    });
    relayoutAll();
  });

  const PROMPT_TYPE_LABELS = {
    predict: "예측",
    predict_pair: "예측(숫자)",
    hinge: "판별",
    evidence: "근거",
    exit: "출구",
  };

  function renderHingeDistribution(container, meta, responses) {
    container.innerHTML = "";
    const choices = meta.choices || [];
    if (!choices.length) return;
    const counted = responses.filter((response) => response.choice);
    const total = counted.length;
    const countByKey = {};
    counted.forEach((response) => {
      countByKey[response.choice] = (countByKey[response.choice] || 0) + 1;
    });

    choices.forEach((choice) => {
      const row = document.createElement("div");
      row.className = "hinge-dist-row";
      const count = countByKey[choice.key] || 0;
      const share = total ? count / total : 0;

      const label = document.createElement("span");
      label.className = "hinge-dist-label";
      const isAnswer = meta.answer && choice.key === meta.answer;
      label.textContent = choice.key;
      if (isAnswer) {
        label.classList.add("correct");
        const mark = document.createElement("span");
        mark.className = "answer-mark";
        mark.textContent = " ✓";
        label.appendChild(mark);
      }
      row.appendChild(label);

      const track = document.createElement("div");
      track.className = "hinge-dist-track";
      const fill = document.createElement("div");
      fill.className = "hinge-dist-fill";
      if (isAnswer) fill.classList.add("correct");
      fill.style.width = `${Math.round(share * 100)}%`;
      track.appendChild(fill);
      row.appendChild(track);

      const countEl = document.createElement("span");
      countEl.className = "hinge-dist-count";
      countEl.textContent = total ? `${count}명 (${Math.round(share * 100)}%)` : "0명";
      row.appendChild(countEl);

      container.appendChild(row);
    });

    if (total >= 3) {
      const heavyWrong = choices.find((choice) => {
        if (meta.answer && choice.key === meta.answer) return false;
        return (countByKey[choice.key] || 0) / total >= 0.3;
      });
      if (heavyWrong) {
        const signal = document.createElement("p");
        signal.className = "hinge-dist-signal";
        const share = Math.round(((countByKey[heavyWrong.key] || 0) / total) * 100);
        const targets = (heavyWrong.target || []).join(", ");
        signal.textContent = `개입 신호: ${heavyWrong.key} 선택이 ${share}%입니다.${targets ? ` (표적 오개념 ${targets})` : ""} 이유 카드를 함께 보며 다시 직면시켜 주세요.`;
        container.appendChild(signal);
      }
    }
  }

  function renderResubmitPairs(container, firstResponses, resubmitResponses) {
    container.innerHTML = "";
    if (!resubmitResponses.length) {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = "아직 재제출한 학생이 없습니다. 학생 화면에서 결과가 열린 뒤에 재제출 입력이 열립니다.";
      container.appendChild(note);
      return;
    }
    const firstByUser = {};
    firstResponses.forEach((response) => {
      firstByUser[response.user_id] = response;
    });
    resubmitResponses
      .slice()
      .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")))
      .forEach((resubmit) => {
        const pair = document.createElement("div");
        pair.className = "resubmit-pair";
        if (showNames) {
          const author = document.createElement("div");
          author.className = "discuss-card-author";
          author.textContent = resubmit.display_name || "이름 없음";
          pair.appendChild(author);
        }
        const first = document.createElement("div");
        first.className = "resubmit-first";
        first.textContent = `1차: ${firstByUser[resubmit.user_id]?.text || "(1차 응답 없음)"}`;
        pair.appendChild(first);
        const second = document.createElement("div");
        second.className = "resubmit-second";
        second.textContent = `재제출: ${resubmit.text}`;
        pair.appendChild(second);
        container.appendChild(pair);
      });
  }

  function renderBoardSection(prompt) {
    const meta = promptMetaById[prompt.prompt_id] || prompt;
    const section = document.createElement("section");
    section.className = "discuss-board-section";

    const heading = document.createElement("h3");
    if (meta.type && PROMPT_TYPE_LABELS[meta.type]) {
      const badge = document.createElement("span");
      badge.className = `prompt-type-badge prompt-type-${meta.type}`;
      badge.textContent = PROMPT_TYPE_LABELS[meta.type];
      heading.appendChild(badge);
    }
    heading.appendChild(document.createTextNode(prompt.question));
    section.appendChild(heading);

    if (meta.observe || meta.target?.length) {
      const guide = document.createElement("p");
      guide.className = "prompt-observe-guide";
      const targets = meta.target?.length ? ` [표적: ${meta.target.join(", ")}]` : "";
      guide.textContent = `관찰 가이드: ${meta.observe || "응답에서 표적 오개념의 흔적을 살펴보세요."}${targets}`;
      section.appendChild(guide);
    }

    const distEl = document.createElement("div");
    distEl.className = "hinge-dist";
    if (meta.type === "hinge") section.appendChild(distEl);

    const pairSummaryEl = document.createElement("div");
    pairSummaryEl.className = "pair-summary";
    const hasPairSummary = meta.type === "predict_pair" && typeof LessonKit.renderPredictPairSummary === "function";
    if (hasPairSummary) section.appendChild(pairSummaryEl);

    const toolbar = document.createElement("div");
    toolbar.className = "discuss-board-toolbar";

    const nameToggle = document.createElement("button");
    nameToggle.type = "button";
    nameToggle.textContent = showNames ? "이름 숨기기" : "이름 보기";
    nameToggle.addEventListener("click", () => {
      showNames = !showNames;
      renderCurrentCardBoards();
    });
    toolbar.appendChild(nameToggle);

    const fontToggle = document.createElement("button");
    fontToggle.type = "button";
    fontToggle.textContent = "글자 크게";
    fontToggle.addEventListener("click", () => {
      largeFont = !largeFont;
      renderCurrentCardBoards();
    });
    toolbar.appendChild(fontToggle);

    const missingButton = document.createElement("button");
    missingButton.type = "button";
    missingButton.textContent = "미제출 확인";
    toolbar.appendChild(missingButton);

    const hiddenToggle = document.createElement("button");
    hiddenToggle.type = "button";
    hiddenToggle.hidden = true;
    toolbar.appendChild(hiddenToggle);

    function updateHiddenToggle() {
      const hiddenCount = (boardEl._responses || []).filter((response) => response.board?.hidden).length;
      hiddenToggle.hidden = hiddenCount === 0 && !boardEl._showHidden;
      hiddenToggle.textContent = boardEl._showHidden
        ? "숨긴 응답 감추기"
        : `숨긴 응답 ${hiddenCount}개 보기`;
    }

    hiddenToggle.addEventListener("click", () => {
      boardEl._showHidden = !boardEl._showHidden;
      updateHiddenToggle();
      relayout(boardEl);
    });

    const fullscreenButton = document.createElement("button");
    fullscreenButton.type = "button";
    fullscreenButton.className = "discuss-fullscreen-toggle";
    fullscreenButton.textContent = "전체 화면";
    fullscreenButton.addEventListener("click", async () => {
      const opening = !section.classList.contains("board-fullscreen");
      section.classList.toggle("board-fullscreen", opening);
      fullscreenButton.textContent = opening ? "전체 화면 닫기" : "전체 화면";
      try {
        if (opening && section.requestFullscreen) {
          await section.requestFullscreen();
        } else if (!opening && document.fullscreenElement) {
          await document.exitFullscreen();
        }
      } catch (error) {
      }
      relayout(boardEl);
    });
    toolbar.appendChild(fullscreenButton);

    const missingList = document.createElement("p");
    missingList.className = "lesson-note discuss-missing-list";
    missingList.hidden = true;
    missingButton.addEventListener("click", () => {
      missingList.hidden = !missingList.hidden;
    });

    section.appendChild(toolbar);

    const boardEl = document.createElement("div");
    boardEl.className = "discuss-board";
    boardEl._promptMeta = meta;
    section.appendChild(boardEl);
    section.appendChild(missingList);

    let resubmitEl = null;
    let resubmitHeading = null;
    let latestFirst = [];
    let latestResubmits = [];
    if (meta.requires_resubmit) {
      resubmitHeading = document.createElement("h4");
      resubmitHeading.className = "resubmit-heading";
      resubmitHeading.textContent = "재제출 (생각의 변화)";
      section.appendChild(resubmitHeading);
      resubmitEl = document.createElement("div");
      resubmitEl.className = "resubmit-board";
      section.appendChild(resubmitEl);
    }

    const foldKey = `${LESSON_ID}:${prompt.prompt_id}`;
    const foldButton = document.createElement("button");
    foldButton.type = "button";
    foldButton.className = "discuss-fold-toggle";
    const foldedNote = document.createElement("p");
    foldedNote.className = "lesson-note discuss-folded-note";

    function applyFold() {
      const folded = foldedFirstPrompts.has(foldKey);
      section.classList.toggle("first-folded", folded);
      foldButton.textContent = folded ? `처음 의견 펼치기 (${latestFirst.length}개)` : "처음 의견 접기";
      foldButton.classList.toggle("is-active", folded);
      foldedNote.hidden = !folded;
      foldedNote.textContent = `처음 의견 ${latestFirst.length}개를 접어 두었습니다. 아래 재제출 비교에는 각 학생의 처음 의견이 함께 나옵니다.`;
    }

    function updateResubmitHeading() {
      if (!resubmitHeading) return;
      resubmitHeading.textContent = `재제출 (생각의 변화) ${latestResubmits.length}/${latestFirst.length}명`;
    }

    if (meta.requires_resubmit) {
      toolbar.insertBefore(foldButton, toolbar.firstChild);
      section.insertBefore(foldedNote, boardEl);
      foldButton.addEventListener("click", () => {
        if (foldedFirstPrompts.has(foldKey)) foldedFirstPrompts.delete(foldKey);
        else foldedFirstPrompts.add(foldKey);
        applyFold();
        if (!foldedFirstPrompts.has(foldKey)) relayout(boardEl);
      });
      applyFold();
    }

    const unwatch = LessonKit.watchDiscuss(
      LESSON_ID,
      prompt.prompt_id,
      (responses) => {
        latestFirst = responses || [];
        renderBoard(boardEl, latestFirst);
        if (meta.type === "hinge") renderHingeDistribution(distEl, meta, latestFirst);
        if (hasPairSummary) LessonKit.renderPredictPairSummary(pairSummaryEl, meta, latestFirst);
        if (resubmitEl) renderResubmitPairs(resubmitEl, latestFirst, latestResubmits);
        if (meta.requires_resubmit) {
          applyFold();
          updateResubmitHeading();
        }
        updateHiddenToggle();
        const missing = computeMissing(prompt.prompt_id, latestFirst);
        missingButton.textContent = `미제출 ${missing.length}명`;
        missingList.textContent = missing.length
          ? missing.map((student) => student.display_name).join(", ")
          : "모두 제출했습니다.";
      },
      classSelect.value,
    );
    discussUnwatchers.push(unwatch);

    if (meta.requires_resubmit) {
      const unwatchResubmit = LessonKit.watchDiscuss(
        LESSON_ID,
        `${prompt.prompt_id}${LessonKit.RESUBMIT_SUFFIX || "__r2"}`,
        (responses) => {
          latestResubmits = responses || [];
          if (resubmitEl) renderResubmitPairs(resubmitEl, latestFirst, latestResubmits);
          updateResubmitHeading();
        },
        classSelect.value,
      );
      discussUnwatchers.push(unwatchResubmit);
    }

    return section;
  }

  function renderCurrentCardBoards() {
    stopDiscussWatchers();
    boardHost.innerHTML = "";
    const card = currentMeta.card;
    if (!card.prompts?.length) {
      boardHost.hidden = true;
      return;
    }
    boardHost.hidden = false;
    if (!classSelect.value) {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = "오른쪽 위 설정에서 학급을 고르면 이 카드의 응답 보드가 열립니다.";
      boardHost.appendChild(note);
      return;
    }
    card.prompts.forEach((prompt) => {
      boardHost.appendChild(renderBoardSection(prompt));
    });
  }

  async function mountDeck() {
    const classId = classSelect.value;
    deckApi?.destroy();
    stopDiscussWatchers();
    if (unwatchSession) {
      unwatchSession();
      unwatchSession = null;
    }
    currentSession = null;
    refollowTried = false;

    const context = {
      lessonId: lesson.lesson_id,
      projectId: lesson.project_id,
      topicId: lesson.topic_id,
      datasetId: lesson.dataset_id,
      track: lesson.track,
      scenario: lesson.scenario || "",
      classId,
      role: "teacher",
      onCardChange: (card, meta) => {
        currentMeta = meta;
        highlightCardList();
        renderCurrentCardBoards();
        if (currentSession?.follow) pushFocus({ silent: true });
      },
      renderers: { ...LessonKit.RENDERERS },
    };

    const currentIndex = catalogLessons.findIndex((item) => item.lesson_id === LESSON_ID);
    const nextLesson = currentIndex >= 0 ? catalogLessons[currentIndex + 1] : null;
    if (nextLesson) {
      context.nextLessonLabel = `다음 차시로 (${currentIndex + 2}차시)`;
      context.onNextLesson = async () => {
        const keys = [...lessonRevealKeys(lesson.definition)];
        if (keys.length) await clearReveals(keys).catch(() => {});
        openPresent({ lesson: nextLesson.lesson_id, classId: classSelect.value });
      };
    }

    deckApi = await LessonKit.renderDeck(deckHost, lesson.definition, context);

    startTeacherHeartbeat(classId);
    if (classId) {
      let warnedOpenReveals = false;
      unwatchSession = LessonKit.watchSession(classId, (session) => {
        currentSession = session;
        if (!warnedOpenReveals) {
          warnedOpenReveals = true;
          const here = lessonRevealKeys(lesson.definition);
          const stale = sessionOpenRevealKeys().filter((key) => here.has(key)).length;
          if (stale) {
            StatApi.toast(`이 차시의 공개 ${stale}개가 이미 켜져 있습니다. 새 수업이면 설정에서 끄세요.`);
          }
        }
        if (session.follow && session.focus_lesson_id !== lesson.lesson_id && !refollowTried) {
          refollowTried = true;
          pushFocus({ silent: true });
        }
        const activeKeys = sessionRangeKeys();
        if (activeKeys.size && Date.now() - lastRangeEditAt > 3000) rangeSelection = activeKeys;
        updateToolbar();
      });
    }
    updateToolbar();
  }

  async function pushFocus(options = {}) {
    const classId = classSelect.value;
    if (!classId) return;
    try {
      currentSession = await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/focus`, {
        method: "PUT",
        body: JSON.stringify({
          lesson_id: lesson.lesson_id,
          level: lesson.level || null,
          step: currentMeta.stepIndex,
          card: currentMeta.cardIndex,
        }),
      });
      if (!options.silent) StatApi.toast("학생 화면을 이 카드로 안내했습니다.");
    } catch (error) {
      LessonKit.showError(error.message || "학생 화면을 안내하지 못했습니다.");
    }
  }

  pushButton.addEventListener("click", () => pushFocus());

  followButton.addEventListener("click", async () => {
    const classId = classSelect.value;
    if (!classId) return;
    const next = !currentSession?.follow;
    const hadRange = sessionRangeKeys().size > 0;
    try {
      currentSession = await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/follow`, {
        method: "PUT",
        body: JSON.stringify({ follow: next }),
      });
      updateToolbar();
      if (next) await pushFocus({ silent: true });
      StatApi.toast(
        next
          ? `${hadRange ? "학습 범위를 풀고, " : ""}학생 화면이 선생님 화면을 따라옵니다.`
          : "같은 화면 보기를 껐습니다.",
      );
    } catch (error) {
      LessonKit.showError(error.message || "같은 화면 보기를 바꾸지 못했습니다.");
    }
  });

  async function sendRange(selection) {
    const classId = classSelect.value;
    if (!classId) return;
    const cards = Array.from(selection || []).map((key) => {
      const [step, card] = key.split(":").map(Number);
      return { step, card };
    });
    const wasFollowing = Boolean(currentSession?.follow);
    try {
      currentSession = await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/range`, {
        method: "PUT",
        body: JSON.stringify({ cards, lesson_id: lesson.lesson_id }),
      });
      updateToolbar();
      StatApi.toast(
        cards.length
          ? `${wasFollowing ? "따라오기를 끄고, " : ""}학습 범위를 ${cards.length}장으로 정했습니다.`
          : "학습 범위를 풀었습니다.",
      );
    } catch (error) {
      LessonKit.showError(error.message || "학습 범위를 바꾸지 못했습니다.");
    }
  }

  rangeButton.addEventListener("click", async () => {
    if (sessionRangeKeys().size) {
      await sendRange(null);
      return;
    }
    if (!rangeSelection.size) return;
    await sendRange(rangeSelection);
  });

  progressButton.addEventListener("click", () => {
    const classId = classSelect.value;
    if (!classId) return;
    LessonKit.openProgressDashboard({
      lessonId: lesson.lesson_id,
      classId,
      track: lesson.track,
      scenario: lesson.scenario || "",
      onGoToCard: (card) => deckApi?.goTo(card.step, card.card),
    });
  });

  joinButton.addEventListener("click", () => {
    if (!joinInfo.code) {
      StatApi.toast("학급을 고르면 참여 코드가 나옵니다.");
      return;
    }
    LessonKit.openJoinModal({ code: joinInfo.code, joinUrl: joinInfo.joinUrl, className: joinInfo.className });
  });

  lockButton.addEventListener("click", async () => {
    const classId = classSelect.value;
    if (!classId) return;
    try {
      await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/lock`, {
        method: "PUT",
        body: JSON.stringify({ lock: !currentSession?.lock }),
      });
    } catch (error) {
      LessonKit.showError(error.message || "머무르기 상태를 바꾸지 못했습니다.");
    }
  });

  pinsButton.addEventListener("click", async () => {
    const classId = classSelect.value;
    if (!classId) return;
    try {
      const data = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}/pins`);
      openPinsModal(classId, joinInfo.code, data);
    } catch (error) {
      LessonKit.showError(error.message || "PIN을 불러오지 못했습니다.");
    }
  });

  const HEARTBEAT_MS = 45000;
  let heartbeatTimer = null;
  async function sendHeartbeat(classId) {
    try {
      await StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}/open`, {
        method: "PUT",
        body: JSON.stringify({ lesson_id: lesson.lesson_id, level: lesson.level || null }),
      });
    } catch (_error) {
    }
  }
  function startTeacherHeartbeat(classId) {
    if (heartbeatTimer) window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    if (!classId) return;
    sendHeartbeat(classId);
    heartbeatTimer = window.setInterval(() => sendHeartbeat(classId), HEARTBEAT_MS);
  }

  let hadClassSelected = Boolean(classSelect.value);
  classSelect.addEventListener("change", async () => {
    if (!(await loadJoinInfo(classSelect.value))) return;
    await mountDeck();
    if (!hadClassSelected && joinInfo.code) {
      hadClassSelected = true;
      LessonKit.openJoinModal({ code: joinInfo.code, joinUrl: joinInfo.joinUrl, className: joinInfo.className });
    }
  });

  renderCardList();
  if (!(await loadJoinInfo(classSelect.value))) return;
  await mountDeck();

  if (joinInfo.code) {
    LessonKit.openJoinModal({ code: joinInfo.code, joinUrl: joinInfo.joinUrl, className: joinInfo.className });
  }

})();
