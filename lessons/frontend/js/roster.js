(async function () {
  await StatAuth.init().catch((error) => LessonKit.showError(error.message));

  const navRole = StatAuth.getNavRole?.();
  if (navRole !== "teacher" && navRole !== "admin") {
    window.location.href = "./index.html";
    return;
  }

  const classForm = document.getElementById("class-form");
  const classInput = document.getElementById("class-id");
  const codeBox = document.getElementById("class-code-box");
  const codeValue = document.getElementById("class-code-value");
  const addSection = document.getElementById("add-section");
  const namesInput = document.getElementById("names-input");
  const issuedSection = document.getElementById("issued-section");
  const issuedList = document.getElementById("issued-list");
  const rosterSection = document.getElementById("roster-section");
  const rosterList = document.getElementById("roster-list");

  const joinUrlBox = document.getElementById("join-url-box");
  const joinUrlInput = document.getElementById("join-url");
  const joinUrlDefault = document.getElementById("join-url-default");
  const trackBox = document.getElementById("track-box");
  const trackSelect = document.getElementById("class-track");
  const scenarioSelect = document.getElementById("class-scenario");

  let classId = "";
  let joinUrl = "";
  let issuedRows = [];

  const classTableBox = document.getElementById("class-table-box");
  async function loadClassTable() {
    let classes = [];
    try {
      classes = (await StatApi.request("/api/lessons/roster")).classes || [];
    } catch (_error) {
      classTableBox.innerHTML = "";
      return;
    }
    classTableBox.innerHTML = "";
    if (!classes.length) {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = "아직 개설한 학급이 없습니다. 아래에서 새 학급을 만들어 주세요.";
      classTableBox.appendChild(note);
      return;
    }
    const table = document.createElement("table");
    table.className = "lesson-sheet";
    table.innerHTML = "<thead><tr><th>학급</th><th>과정</th><th>학생</th><th>코드</th><th></th></tr></thead>";
    const tbody = document.createElement("tbody");
    classes.forEach((item) => {
      const tr = document.createElement("tr");
      [item.class_id, item.track_label, `${item.student_count}명`, item.code].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      const action = document.createElement("td");
      const openButton = document.createElement("button");
      openButton.type = "button";
      openButton.className = "lesson-connector-fetch";
      openButton.textContent = "열기";
      openButton.addEventListener("click", async () => {
        classId = item.class_id;
        classInput.value = "";
        try {
          await loadRoster();
          codeBox.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error) {
          LessonKit.showError(error.message || "학급을 열지 못했습니다.");
        }
      });
      action.appendChild(openButton);
      tr.appendChild(action);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    classTableBox.appendChild(table);
  }

  function renderCredentialTable(container, rows) {
    if (container === issuedList) issuedRows = rows;
    container.innerHTML = "";
    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["이름", "학급 코드", "PIN"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      [row.display_name, codeValue.textContent].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      const pinCell = document.createElement("td");
      pinCell.appendChild(LessonKit.createPinToggle(row.pin, { shown: true, name: row.display_name }));
      tr.appendChild(pinCell);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  async function loadRoster() {
    const data = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}`);
    codeValue.textContent = data.code;
    joinUrl = data.join_url || "";
    joinUrlInput.value = joinUrl;
    joinUrlDefault.textContent = `이 주소를 단축하면 코드까지 자동으로 입력됩니다 — ${LessonKit.joinLink(data.code, "")}`;
    savedTrack = data.track || "m3";
    trackSelect.value = savedTrack;
    savedScenario = data.scenario || "full";
    scenarioSelect.value = savedScenario;
    codeBox.hidden = false;
    trackBox.hidden = false;
    joinUrlBox.hidden = false;
    addSection.hidden = false;
    rosterSection.hidden = false;

    rosterList.innerHTML = "";
    if (!data.students.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "아직 학생이 없습니다. 아래에 명단을 붙여넣어 만들어 주세요.";
      rosterList.appendChild(empty);
      return;
    }

    const showAll = LessonKit.createPinShowAllButton(rosterList);
    rosterList.appendChild(showAll);
    const printAll = document.createElement("button");
    printAll.type = "button";
    printAll.className = "lesson-connector-fetch roster-print-all";
    printAll.textContent = "잘라 나눠주기 인쇄";
    printAll.addEventListener("click", () => LessonKit.printPinSlips(classId, data.code, data.students));
    rosterList.appendChild(printAll);

    data.students.forEach((student) => {
      const row = document.createElement("div");
      row.className = "lesson-group-dataset-row roster-student-row";
      const name = document.createElement("span");
      name.className = "roster-student-name";
      name.textContent = student.display_name;
      row.appendChild(name);

      const pinWrap = document.createElement("span");
      pinWrap.className = "roster-student-pin";
      pinWrap.appendChild(
        LessonKit.createPinToggle(student.pin, { hasPin: student.has_pin, name: student.display_name }),
      );
      row.appendChild(pinWrap);

      const renameButton = document.createElement("button");
      renameButton.type = "button";
      renameButton.className = "lesson-connector-fetch";
      renameButton.textContent = "이름 수정";
      renameButton.addEventListener("click", async () => {
        const next = window.prompt("새 이름을 입력하세요.", student.display_name);
        if (next === null) return;
        const trimmed = next.trim();
        if (!trimmed || trimmed === student.display_name) return;
        renameButton.disabled = true;
        try {
          await StatApi.request(
            `/api/lessons/roster/${encodeURIComponent(classId)}/students/${encodeURIComponent(student.user_id)}`,
            { method: "PATCH", body: JSON.stringify({ display_name: trimmed }) },
          );
          StatApi.toast(`이름을 "${trimmed}"(으)로 고쳤습니다. PIN과 진행 기록은 그대로입니다.`);
          await loadRoster();
        } catch (error) {
          LessonKit.showError(error.message || "이름을 고치지 못했습니다.");
        } finally {
          renameButton.disabled = false;
        }
      });
      row.appendChild(renameButton);

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "lesson-connector-fetch";
      removeButton.textContent = "명단에서 빼기";
      removeButton.addEventListener("click", async () => {
        const confirmed = window.confirm(
          `${student.display_name} 학생을 명단에서 뺍니다.\n\n`
            + "계정과 PIN, 그동안의 응답과 진행 기록이 지워지고 되돌릴 수 없습니다.\n"
            + "전학이나 잘못 만든 계정일 때만 쓰세요. 계속할까요?",
        );
        if (!confirmed) return;
        removeButton.disabled = true;
        try {
          await StatApi.request(
            `/api/lessons/roster/${encodeURIComponent(classId)}/students/${encodeURIComponent(student.user_id)}`,
            { method: "DELETE" },
          );
          StatApi.toast(`${student.display_name} 학생을 명단에서 뺐습니다.`);
          await loadRoster();
          await loadClassTable();
        } catch (error) {
          LessonKit.showError(error.message || "학생을 빼지 못했습니다.");
          removeButton.disabled = false;
        }
      });
      row.appendChild(removeButton);

      const resetButton = document.createElement("button");
      resetButton.type = "button";
      resetButton.className = "lesson-connector-fetch";
      resetButton.textContent = "PIN 재발급";
      resetButton.addEventListener("click", async () => {
        const confirmed = window.confirm(
          `${student.display_name} 학생의 PIN을 새로 발급합니다.\n\n`
            + "지금 쓰던 PIN은 즉시 못 쓰게 되고, 학생에게 새 PIN을 다시 알려 줘야 합니다.\n"
            + "되돌릴 수 없습니다. 진행할까요?",
        );
        if (!confirmed) return;
        resetButton.disabled = true;
        try {
          const result = await StatApi.request(
            `/api/lessons/roster/${encodeURIComponent(classId)}/students/${encodeURIComponent(student.user_id)}/reset-pin`,
            { method: "POST" },
          );
          issuedSection.hidden = false;
          renderCredentialTable(issuedList, [result]);
          await loadRoster();
          issuedSection.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error) {
          LessonKit.showError(error.message || "PIN을 재발급하지 못했습니다.");
        } finally {
          resetButton.disabled = false;
        }
      });
      row.appendChild(resetButton);
      rosterList.appendChild(row);
    });
  }

  classForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    classId = classInput.value.trim();
    if (!classId) return;
    try {
      await loadRoster();
      await loadClassTable();
    } catch (error) {
      LessonKit.showError(error.message || "학급을 열지 못했습니다.");
    }
  });

  await loadClassTable();
  const requestedClass = new URLSearchParams(window.location.search).get("class") || "";
  if (requestedClass) {
    classId = requestedClass;
    loadRoster().catch((error) => LessonKit.showError(error.message || "학급을 열지 못했습니다."));
  }

  let savedTrack = "";
  let savedScenario = "full";
  scenarioSelect.addEventListener("change", async () => {
    const label = scenarioSelect.options[scenarioSelect.selectedIndex].textContent;
    const confirmed = window.confirm(
      `이 학급의 시나리오를 "${label}"(으)로 바꿉니다.

`
        + "진행 기록은 시나리오별로 따로 저장되어, 바꾸면 이전 시나리오의 진행은 보이지 않게 됩니다. 계속할까요?",
    );
    if (!confirmed) {
      scenarioSelect.value = savedScenario;
      return;
    }
    try {
      const result = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}/track`, {
        method: "PUT",
        body: JSON.stringify({ scenario: scenarioSelect.value }),
      });
      savedScenario = result.scenario;
      scenarioSelect.value = result.scenario;
      StatApi.toast(`이 학급의 시나리오를 ${result.scenario_label}(으)로 저장했습니다.`);
    } catch (error) {
      scenarioSelect.value = savedScenario;
      LessonKit.showError(error.message || "시나리오를 저장하지 못했습니다.");
    }
  });
  trackSelect.addEventListener("change", async () => {
    const label = trackSelect.options[trackSelect.selectedIndex].textContent;
    const confirmed = window.confirm(
      `이 학급의 과정을 "${label}"(으)로 바꿉니다.\n\n`
        + "이미 수업을 시작했다면 학생들이 보던 진행과 프로젝트는 트랙별로 따로 저장되어, "
        + "이전 트랙의 진행은 보이지 않게 됩니다. 계속할까요?",
    );
    if (!confirmed) {
      trackSelect.value = savedTrack || "m3";
      return;
    }
    try {
      const result = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}/track`, {
        method: "PUT",
        body: JSON.stringify({ track: trackSelect.value }),
      });
      savedTrack = result.track;
      trackSelect.value = result.track;
      StatApi.toast(`이 학급의 과정을 ${result.track_label}(으)로 저장했습니다.`);
    } catch (error) {
      trackSelect.value = savedTrack || "m3";
      LessonKit.showError(error.message || "과정을 저장하지 못했습니다.");
    }
  });

  document.getElementById("rotate-code").addEventListener("click", async () => {
    if (!window.confirm("코드를 새로 발급하면 이전 코드로는 들어올 수 없습니다. 계속할까요?")) return;
    try {
      const result = await StatApi.request(
        `/api/lessons/roster/${encodeURIComponent(classId)}/rotate-code`,
        { method: "POST" },
      );
      codeValue.textContent = result.code;
      StatApi.toast("새 학급 코드를 발급했습니다.");
    } catch (error) {
      LessonKit.showError(error.message || "코드를 새로 발급하지 못했습니다.");
    }
  });

  document.getElementById("create-students").addEventListener("click", async () => {
    const names = namesInput.value.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!names.length) {
      LessonKit.showError("한 줄에 한 명씩 이름을 붙여넣어 주세요.");
      return;
    }
    const button = document.getElementById("create-students");
    button.disabled = true;
    button.textContent = "만드는 중…";
    try {
      const result = await StatApi.request("/api/lessons/roster", {
        method: "POST",
        body: JSON.stringify({ class_id: classId, names }),
      });
      codeValue.textContent = result.code;
      const skipped = result.skipped || [];
      if (result.students.length) {
        issuedSection.hidden = false;
        renderCredentialTable(issuedList, result.students);
      }
      const summary = skipped.length
        ? `신규 ${result.students.length}명을 만들었습니다. 이미 있는 이름 ${skipped.length}명(${skipped.join(", ")})은 건너뛰어 기존 PIN이 유지됩니다.`
        : `신규 ${result.students.length}명을 만들고 PIN을 발급했습니다.`;
      StatApi.toast(summary);
      namesInput.value = "";
      await loadRoster();
      if (result.students.length) {
        issuedSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      LessonKit.showError(error.message || "계정을 만들지 못했습니다.");
    } finally {
      button.disabled = false;
      button.textContent = "계정 만들고 PIN 발급";
    }
  });

  document.getElementById("save-join-url").addEventListener("click", async () => {
    try {
      const result = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}/join-url`, {
        method: "PUT",
        body: JSON.stringify({ join_url: joinUrlInput.value.trim() }),
      });
      joinUrl = result.join_url || "";
      joinUrlInput.value = joinUrl;
      StatApi.toast(joinUrl ? "학생 접속 주소를 저장했습니다." : "기본 주소를 쓰도록 되돌렸습니다.");
    } catch (error) {
      LessonKit.showError(error.message || "주소를 저장하지 못했습니다.");
    }
  });

  document.getElementById("open-join-modal").addEventListener("click", () => {
    LessonKit.openJoinModal({ code: codeValue.textContent, joinUrl, className: classId });
  });

  document.getElementById("print-issued").addEventListener("click", () => {
    if (!issuedRows.length) return;
    LessonKit.printPinSlips(classId, codeValue.textContent, issuedRows);
  });
})();
