(async function () {
  await StatAuth.init().catch((error) => StatApi.toast(error.message));

  document.getElementById("student-preview-btn")?.addEventListener("click", () => {
    StatAuth.startStudentPreview();
  });

  const container = document.getElementById("dashboard-container");
  const pinContainer = document.getElementById("pin-container");
  const pinClassInput = document.getElementById("pin-class-id");
  const pinLoadButton = document.getElementById("pin-load-btn");

  const LESSON_LABEL = (id) => `${id.replace("lesson", "")}차시`;

  function progressCellText(detail) {
    if (!detail?.started) return "-";
    const parts = [];
    if (detail.position && Number.isFinite(detail.position.step)) {
      parts.push(`${detail.position.step + 1}단계`);
    }
    if (detail.connectors) parts.push(`자료 ${detail.connectors}`);
    if (detail.responses) parts.push(`응답 ${detail.responses}`);
    if (detail.exit_submitted) parts.push("출구 ✓");
    return parts.length ? `시작함 · ${parts.join(" · ")}` : "시작함";
  }

  document.getElementById("csv-download-btn")?.addEventListener("click", async () => {
    const lessonId = document.getElementById("csv-lesson-select").value;
    const classId = document.getElementById("csv-class-id").value.trim();
    const query = new URLSearchParams();
    if (lessonId) query.set("lesson_id", lessonId);
    if (classId) query.set("class_id", classId);
    try {
      const result = await StatApi.request(`/api/lessons/teacher/responses-csv?${query.toString()}`);
      if (!result.count) {
        StatApi.toast("내려받을 응답이 없습니다.");
        return;
      }
      const blob = new Blob([`﻿${result.csv}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      StatApi.toast(`응답 ${result.count}건을 내려받았습니다.`);
    } catch (error) {
      StatApi.toast(error.message || "CSV를 내려받지 못했습니다.");
    }
  });

  async function resetStudent(student, lessonId, label) {
    const scope = lessonId ? `${LESSON_LABEL(lessonId)}를` : "모든 차시를";
    const linkedWarning = lessonId === "lesson5"
      ? "주의: 6차시와 7차시가 이 탐구를 이어받습니다. 5차시를 초기화하면 분석과 해석의 연결이 끊어져 탐구를 처음부터 다시 시작하게 됩니다.\n"
      : "";
    const confirmed = window.confirm(
      `${student.display_name} 학생의 ${scope} 처음 상태로 되돌립니다.\n\n`
        + linkedWarning
        + "불러온 자료와 제출한 응답이 지워지고, 학생은 처음 카드부터 다시 시작합니다.\n"
        + "실험수업 진단 응답도 지워집니다. 필요하면 먼저 진단 응답 CSV를 내려받으세요.\n"
        + "되돌릴 수 없습니다. 진행할까요?",
    );
    if (!confirmed) return;

    try {
      const result = await StatApi.request(
        `/api/lessons/teacher/students/${encodeURIComponent(student.user_id)}/reset`,
        { method: "POST", body: JSON.stringify({ lesson_id: lessonId || "" }) },
      );
      const cleared = result.lessons.reduce(
        (sum, lesson) => sum
          + lesson.cleared.projects
          + lesson.cleared.connector_datasets
          + lesson.cleared.responses
          + (lesson.cleared.diag_responses || 0),
        0,
      );
      StatApi.toast(`${student.display_name} · ${label} 초기화했습니다 (지운 항목 ${cleared}개).`);
      await loadProgress();
    } catch (error) {
      StatApi.toast(error.message || "초기화하지 못했습니다.");
    }
  }

  function renderProgress(data) {
    container.innerHTML = "";
    if (!data.students.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "담당 학생이 없거나, 아직 아무도 차시를 시작하지 않았습니다.";
      container.appendChild(empty);
      return;
    }

    const table = document.createElement("table");
    table.className = "lesson-sheet teacher-progress-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["학생", "학급", ...data.lessons.map(LESSON_LABEL), "초기화"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    data.students.forEach((student) => {
      const tr = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = student.display_name;
      tr.appendChild(nameCell);

      const classCell = document.createElement("td");
      classCell.textContent = student.class_id || "-";
      tr.appendChild(classCell);

      data.lessons.forEach((lessonId) => {
        const detail = student.detail?.[lessonId];
        const cell = document.createElement("td");
        cell.textContent = progressCellText(detail);
        if (detail?.started) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "teacher-reset-cell";
          button.title = `${LESSON_LABEL(lessonId)}만 초기화`;
          button.textContent = "초기화";
          button.addEventListener("click", () => resetStudent(student, lessonId, LESSON_LABEL(lessonId)));
          cell.appendChild(button);
        }
        tr.appendChild(cell);
      });

      const actionCell = document.createElement("td");
      const allButton = document.createElement("button");
      allButton.type = "button";
      allButton.className = "teacher-reset-all";
      allButton.textContent = "전체 초기화";
      allButton.addEventListener("click", () => resetStudent(student, "", "모든 차시"));
      actionCell.appendChild(allButton);
      tr.appendChild(actionCell);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  async function loadProgress() {
    container.textContent = "불러오는 중…";
    try {
      const data = await StatApi.request("/api/lessons/teacher/progress");
      renderProgress(data);
      return data;
    } catch (error) {
      container.textContent = "";
      StatApi.toast(error.message || "진행 현황을 불러오지 못했습니다.");
      return null;
    }
  }

  document.getElementById("diag-csv-btn")?.addEventListener("click", async () => {
    const classId = document.getElementById("csv-class-id").value.trim();
    try {
      const query = new URLSearchParams();
      if (classId) query.set("class_id", classId);
      const result = await StatApi.request(`/api/lessons/teacher/diag-export?${query.toString()}`);
      if (!result.count) {
        StatApi.toast("아직 저장된 진단 응답이 없습니다.");
        return;
      }
      const blob = new Blob([`﻿${result.csv}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      StatApi.toast(`진단 응답 ${result.count}건을 내려받았습니다.`);
    } catch (error) {
      StatApi.toast(error.message || "진단 CSV를 내려받지 못했습니다.");
    }
  });

  function renderIssuedPins(classId, issued) {
    pinContainer.innerHTML = "";

    const notice = document.createElement("p");
    notice.className = "lesson-note";
    notice.textContent =
      "방금 발급한 PIN입니다. 나눠주기 좋게 펼쳐 두었고, 나중에 발급 현황에서도 다시 볼 수 있습니다.";
    pinContainer.appendChild(notice);

    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>학생</th><th>PIN</th></tr>";
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    issued.forEach((student) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = student.display_name;
      const pin = document.createElement("td");
      pin.className = "teacher-pin-value";
      pin.appendChild(LessonKit.createPinToggle(student.pin, { shown: true, name: student.display_name }));
      tr.appendChild(name);
      tr.appendChild(pin);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    pinContainer.appendChild(table);

    const printButton = document.createElement("button");
    printButton.type = "button";
    printButton.className = "lesson-connector-fetch";
    printButton.textContent = "인쇄하기";
    printButton.addEventListener("click", () => window.print());
    pinContainer.appendChild(printButton);

    const backButton = document.createElement("button");
    backButton.type = "button";
    backButton.className = "lesson-connector-fetch";
    backButton.textContent = "발급 현황으로 돌아가기";
    backButton.addEventListener("click", () => loadPins(classId));
    pinContainer.appendChild(backButton);
  }

  async function reissue(classId, userIds, label) {
    const confirmed = window.confirm(
      `${label} PIN을 새로 발급합니다.\n\n`
        + "지금 쓰던 PIN은 즉시 못 쓰게 되고, 학생에게 새 PIN을 다시 알려 줘야 합니다.\n"
        + "되돌릴 수 없습니다. 진행할까요?",
    );
    if (!confirmed) return;
    try {
      const result = await StatApi.request(
        `/api/lessons/roster/${encodeURIComponent(classId)}/reissue-pins`,
        { method: "POST", body: JSON.stringify({ user_ids: userIds || [] }) },
      );
      renderIssuedPins(classId, result.students);
    } catch (error) {
      StatApi.toast(error.message || "PIN을 발급하지 못했습니다.");
    }
  }

  function renderPinStatus(classId, data) {
    pinContainer.innerHTML = "";

    const notice = document.createElement("p");
    notice.className = "lesson-note";
    notice.textContent = data.pin_note || data.pin_hidden_reason || "";
    pinContainer.appendChild(notice);

    if (!data.students.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "이 학급에 등록된 학생이 없습니다. 먼저 학급 명단을 만들어 주세요.";
      pinContainer.appendChild(empty);
      return;
    }

    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>학생</th><th>PIN</th><th>상태</th><th>마지막 발급</th><th></th></tr>";
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    data.students.forEach((student) => {
      const tr = document.createElement("tr");

      const name = document.createElement("td");
      name.textContent = student.display_name;
      tr.appendChild(name);

      const pinCell = document.createElement("td");
      pinCell.appendChild(
        LessonKit.createPinToggle(student.pin, { hasPin: student.has_pin, name: student.display_name }),
      );
      tr.appendChild(pinCell);

      const status = document.createElement("td");
      status.textContent = student.locked
        ? "잠김(PIN 5회 틀림)"
        : student.failed_count
          ? `실패 ${student.failed_count}회`
          : "정상";
      tr.appendChild(status);

      const issued = document.createElement("td");
      issued.textContent = student.issued_at ? student.issued_at.slice(0, 16).replace("T", " ") : "-";
      tr.appendChild(issued);

      const action = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "teacher-reset-cell";
      button.textContent = student.has_pin ? "재발급" : "발급";
      button.addEventListener("click", () => reissue(classId, [student.user_id], `${student.display_name} 학생의`));
      action.appendChild(button);
      tr.appendChild(action);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    pinContainer.appendChild(table);

    const showAll = LessonKit.createPinShowAllButton(table);
    pinContainer.appendChild(showAll);

    const allButton = document.createElement("button");
    allButton.type = "button";
    allButton.className = "lesson-connector-fetch";
    allButton.textContent = "학급 전체 PIN 새로 발급";
    allButton.addEventListener("click", () => reissue(classId, [], "학급 전체의"));
    pinContainer.appendChild(allButton);
  }

  async function loadPins(classId) {
    if (!classId) {
      StatApi.toast("학급 이름을 입력해 주세요.");
      return;
    }
    pinContainer.textContent = "불러오는 중…";
    try {
      const data = await StatApi.request(`/api/lessons/roster/${encodeURIComponent(classId)}/pins`);
      renderPinStatus(classId, data);
    } catch (error) {
      pinContainer.textContent = "";
      StatApi.toast(error.message || "PIN 현황을 불러오지 못했습니다.");
    }
  }

  pinLoadButton.addEventListener("click", () => loadPins(pinClassInput.value.trim()));
  pinClassInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadPins(pinClassInput.value.trim());
  });

  const progressData = await loadProgress();

  const classIds = Array.from(
    new Set((progressData?.students || []).map((student) => student.class_id).filter(Boolean)),
  );
  if (classIds.length === 1) {
    pinClassInput.value = classIds[0];
    await loadPins(classIds[0]);
  }
})();
