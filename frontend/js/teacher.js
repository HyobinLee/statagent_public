(function () {
  const summary = document.getElementById("teacher-summary");
  const studentList = document.getElementById("student-list");
  const blockedList = document.getElementById("blocked-list");
  const hierarchyTarget = document.getElementById("teacher-hierarchy");
  const reportList = document.getElementById("report-list");
  const reportDetail = document.getElementById("report-detail");
  const shareRuleList = document.getElementById("share-rule-list");
  let dashboard = null;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  const TOOL_LABELS_KO = {
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

  function toolLabel(toolName) {
    return TOOL_LABELS_KO[toolName] || toolName || "분석";
  }

  function table(headers, rows) {
    if (!rows.length) return `<p class="muted">표시할 항목이 없습니다.</p>`;
    return `
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    `;
  }

  function stageLabel(stage) {
    return {
      topic: "주제",
      dataset: "자료",
      analysis: "분석",
      conclusion: "결론",
      report: "보고서",
    }[stage] || stage;
  }

  function modeLabel(mode) {
    return {
      all: "전체 공개",
      sample: "임의 일부 공개",
      teacher_selected: "교사 선택 공개",
      targeted: "대상 지정 공개",
    }[mode] || mode;
  }

  function splitIds(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function selectedBulkValues(group) {
    return [...document.querySelectorAll(`[data-bulk-item="${group}"]:checked:not(:disabled)`)].map((input) => input.value);
  }

  function updateBulkState(group) {
    const checkboxes = [...document.querySelectorAll(`[data-bulk-item="${group}"]:not(:disabled)`)];
    const checked = checkboxes.filter((input) => input.checked);
    const selectAll = document.querySelector(`[data-select-all="${group}"]`);
    if (selectAll) {
      selectAll.checked = Boolean(checkboxes.length) && checked.length === checkboxes.length;
      selectAll.indeterminate = checked.length > 0 && checked.length < checkboxes.length;
      selectAll.disabled = !checkboxes.length;
    }
    document.querySelectorAll(`[data-bulk-requires="${group}"]`).forEach((button) => {
      button.disabled = !checked.length;
    });
    const countTarget = document.querySelector(`[data-bulk-count="${group}"]`);
    if (countTarget) countTarget.textContent = `선택 ${checked.length}건`;
  }

  function attachBulkSelection(root, group) {
    root.querySelector(`[data-select-all="${group}"]`)?.addEventListener("change", (event) => {
      root.querySelectorAll(`[data-bulk-item="${group}"]:not(:disabled)`).forEach((checkbox) => {
        checkbox.checked = event.target.checked;
      });
      updateBulkState(group);
    });
    root.querySelectorAll(`[data-bulk-item="${group}"]`).forEach((checkbox) => {
      checkbox.addEventListener("change", () => updateBulkState(group));
    });
    updateBulkState(group);
  }

  function bulkToolbar(group, actions) {
    return `
      <div class="bulk-toolbar">
        <label class="inline-check">
          <input type="checkbox" data-select-all="${escapeHtml(group)}" />
          전체 선택
        </label>
        <span class="muted" data-bulk-count="${escapeHtml(group)}">선택 0건</span>
        <span class="bulk-spacer"></span>
        ${actions}
      </div>
    `;
  }

  function renderHierarchyRouter(data) {
    if (!hierarchyTarget) return;
    const teacher = data.viewer || {};
    const students = data.students || [];
    hierarchyTarget.innerHTML = `
      <form id="teacher-hierarchy-form" class="hierarchy-router-form">
        <div class="hierarchy-route-line">
          <span>학생</span>
          <span>→</span>
          <label class="analysis-field">
            <span>학급</span>
            <input id="teacher-route-class" list="teacher-route-class-options" maxlength="80" placeholder="예: 1학년 3반" required />
          </label>
          <datalist id="teacher-route-class-options">
            ${(data.classes || []).map((item) => `<option value="${escapeHtml(item.class_id)}"></option>`).join("")}
          </datalist>
          <span>→</span>
          <strong>${escapeHtml(teacher.display_name || "담당 교사")}</strong>
          <span>→ 관리자</span>
        </div>
        ${bulkToolbar(
          "teacher-hierarchy",
          `<button type="submit" class="primary" data-bulk-requires="teacher-hierarchy" disabled>선택 학생을 내 담당 학급으로 배치</button>`,
        )}
        <div class="table-wrap">
          ${table(
            ["", "학생", "현재 학급", "현재 교사", "모둠"],
            students.map(
              (student) => `
                <tr>
                  <td class="row-select-cell">
                    <input
                      type="checkbox"
                      data-bulk-item="teacher-hierarchy"
                      value="${escapeHtml(student.user_id)}"
                      aria-label="${escapeHtml(student.display_name)} 선택"
                    />
                  </td>
                  <td>${escapeHtml(student.display_name)}</td>
                  <td>${escapeHtml(student.class_id || "미배정")}</td>
                  <td>${escapeHtml(student.teacher_name || student.teacher_id || "-")}</td>
                  <td>${escapeHtml(student.group_id || "-")}</td>
                </tr>
              `,
            ),
          )}
        </div>
      </form>
    `;
    attachBulkSelection(hierarchyTarget, "teacher-hierarchy");
    document.getElementById("teacher-hierarchy-form")?.addEventListener("submit", (event) => {
      routeTeacherHierarchy(event).catch((error) => StatApi.toast(error.message));
    });
  }

  function render() {
    const data = dashboard;
    summary.innerHTML = `
      <div class="metric"><span>프로젝트</span><strong>${data.summary.project_count}</strong></div>
      <div class="metric"><span>제출 보고서</span><strong>${data.summary.submitted_report_count}</strong></div>
      <div class="metric"><span>차단 사용자</span><strong>${data.summary.blocked_user_count}</strong></div>
    `;
    renderHierarchyRouter(data);
    document.getElementById("school-level").value = data.school_level || "middle_high";
    studentList.innerHTML =
      bulkToolbar(
        "teacher-students",
        `<button type="button" data-bulk-class-students data-bulk-requires="teacher-students" disabled>선택 학급 지정</button>
        <button type="button" data-bulk-group-students data-bulk-requires="teacher-students" disabled>선택 모둠 지정</button>`,
      )
      + table(
      ["", "학생", "학급", "담당 교사", "모둠", "단계", "차단", ""],
      data.students.map(
        (student) =>
          `<tr>
            <td class="row-select-cell">
              <input
                type="checkbox"
                data-bulk-item="teacher-students"
                value="${escapeHtml(student.user_id)}"
                aria-label="${escapeHtml(student.display_name)} 선택"
              />
            </td>
            <td>${escapeHtml(student.display_name)}</td>
            <td>${escapeHtml(student.class_id || "-")}</td>
            <td>${escapeHtml(student.teacher_name || student.teacher_id || "-")}</td>
            <td>${escapeHtml(student.group_id || "-")}</td>
            <td>${escapeHtml(student.latest_project_status)}</td>
            <td>${student.is_blocked ? "예" : "아니오"}</td>
            <td>
              <button data-class-student="${escapeHtml(student.user_id)}">학급</button>
              <button data-group-student="${escapeHtml(student.user_id)}">모둠</button>
            </td>
          </tr>`,
      ),
    );
    attachBulkSelection(studentList, "teacher-students");
    studentList.querySelector("[data-bulk-class-students]")?.addEventListener("click", () =>
      assignClass(selectedBulkValues("teacher-students")).catch((error) => StatApi.toast(error.message)),
    );
    studentList.querySelector("[data-bulk-group-students]")?.addEventListener("click", () =>
      assignGroup(selectedBulkValues("teacher-students")).catch((error) => StatApi.toast(error.message)),
    );
    studentList.querySelectorAll("[data-class-student]").forEach((button) => {
      button.addEventListener("click", () => assignClass([button.dataset.classStudent]));
    });
    studentList.querySelectorAll("[data-group-student]").forEach((button) => {
      button.addEventListener("click", () => assignGroup([button.dataset.groupStudent]));
    });
    blockedList.innerHTML =
      bulkToolbar(
        "blocked-students",
        `<button type="button" data-bulk-unblock-students data-bulk-requires="blocked-students" disabled>선택 해제</button>`,
      )
      + table(
      ["", "사용자", "사유", ""],
      data.blocked_users.map(
        (user) =>
          `<tr>
            <td class="row-select-cell">
              <input
                type="checkbox"
                data-bulk-item="blocked-students"
                value="${escapeHtml(user.user_id)}"
                aria-label="${escapeHtml(user.display_name)} 선택"
              />
            </td>
            <td>${escapeHtml(user.display_name)}</td>
            <td>${escapeHtml(user.block_reason || "-")}</td>
            <td><button data-unblock="${escapeHtml(user.user_id)}">해제</button></td>
          </tr>`,
      ),
    );
    attachBulkSelection(blockedList, "blocked-students");
    blockedList.querySelector("[data-bulk-unblock-students]")?.addEventListener("click", () =>
      unblockMany(selectedBulkValues("blocked-students"), true).catch((error) => StatApi.toast(error.message)),
    );
    blockedList.querySelectorAll("[data-unblock]").forEach((button) => {
      button.addEventListener("click", () => unblockMany([button.dataset.unblock]));
    });
    reportList.innerHTML =
      data.reports
        .map(
          (report) => `
            <article class="report-item">
              <div>
                <strong>${escapeHtml(report.topic_title)}</strong>
                <p class="muted">${escapeHtml((report.dataset_names || [report.dataset_name]).join(", "))} · ${escapeHtml(report.status)}</p>
              </div>
              <button data-report="${escapeHtml(report.report_id)}">보기</button>
            </article>
          `,
        )
        .join("") || `<p class="muted">제출된 보고서가 없습니다.</p>`;
    reportList.querySelectorAll("[data-report]").forEach((button) => {
      button.addEventListener("click", () => showReport(button.dataset.report));
    });
    shareRuleList.innerHTML = table(
      ["단계", "방식", "대상"],
      (data.share_rules || []).map((rule) => {
        const targets = [
          ...(rule.target_user_ids || []),
          ...(rule.target_group_ids || []).map((groupId) => `모둠:${groupId}`),
        ];
        const sources = rule.source_user_ids?.length ? `공유 학생: ${rule.source_user_ids.join(", ")}` : "모든 산출물";
        return `<tr><td>${stageLabel(rule.stage)}</td><td>${modeLabel(rule.mode)}</td><td>${escapeHtml(`${sources} / ${targets.join(", ") || "기본 대상"}`)}</td></tr>`;
      }),
    );
  }

  async function load() {
    dashboard = await StatApi.request("/api/teacher/dashboard");
    render();
  }

  async function routeTeacherHierarchy(event) {
    event.preventDefault();
    const studentIds = selectedBulkValues("teacher-hierarchy");
    const classId = document.getElementById("teacher-route-class")?.value.trim();
    if (!studentIds.length) {
      StatApi.toast("배치할 학생을 선택해 주세요.");
      return;
    }
    if (!classId) {
      StatApi.toast("학급을 입력해 주세요.");
      return;
    }
    await StatApi.request("/api/teacher/hierarchy-route", {
      method: "POST",
      body: JSON.stringify({ class_id: classId, student_ids: studentIds }),
    });
    StatApi.toast(`학생 ${studentIds.length}명을 ${classId} 학급에 배치했습니다.`);
    await load();
  }

  async function unblockMany(userIds, askConfirmation = false) {
    const ids = [...new Set(userIds)].filter(Boolean);
    if (!ids.length) return;
    if (askConfirmation && !window.confirm(`선택한 학생 ${ids.length}명의 일시정지를 해제할까요?`)) return;
    for (const userId of ids) {
      await StatApi.request(`/api/teacher/students/${userId}/unblock`, { method: "POST", body: "{}" });
    }
    await load();
  }

  async function assignClass(userIds) {
    const ids = [...new Set(userIds)].filter(Boolean);
    if (!ids.length) return;
    const current = ids.length === 1 ? dashboard.students.find((student) => student.user_id === ids[0])?.class_id || "" : "";
    const classId = window.prompt("배정할 학급 이름을 입력하세요.", current);
    if (!classId) return;
    await StatApi.request("/api/teacher/classes", {
      method: "POST",
      body: JSON.stringify({ class_id: classId.trim(), student_ids: ids }),
    });
    await load();
  }

  async function assignGroup(userIds) {
    const ids = [...new Set(userIds)].filter(Boolean);
    if (!ids.length) return;
    const current = ids.length === 1 ? dashboard.students.find((student) => student.user_id === ids[0])?.group_id || "" : "";
    const groupId = window.prompt("배정할 모둠 이름을 입력하세요.", current);
    if (!groupId) return;
    await StatApi.request("/api/teacher/groups", {
      method: "POST",
      body: JSON.stringify({ group_id: groupId.trim(), student_ids: ids }),
    });
    await load();
  }

  async function saveSchoolLevel(event) {
    event.preventDefault();
    const schoolLevel = document.getElementById("school-level").value;
    await StatApi.request("/api/teacher/school-level", {
      method: "POST",
      body: JSON.stringify({ school_level: schoolLevel }),
    });
    StatApi.toast("학교급 설정을 저장했습니다.");
    await load();
  }

  async function saveTopicTemplate(event) {
    event.preventDefault();
    const title = document.getElementById("topic-template-title").value.trim();
    const question = document.getElementById("topic-template-question").value.trim();
    const level = document.getElementById("school-level").value;
    if (!title || !question) {
      StatApi.toast("예시 과제 제목과 탐구 질문을 입력해 주세요.");
      return;
    }
    await StatApi.request("/api/teacher/topic-templates", {
      method: "POST",
      body: JSON.stringify({ title, question, level, visible: true }),
    });
    document.getElementById("topic-template-title").value = "";
    document.getElementById("topic-template-question").value = "";
    StatApi.toast("예시 과제를 저장했습니다.");
    await load();
  }

  async function saveShareRule(event) {
    event.preventDefault();
    const stage = document.getElementById("share-stage").value;
    const mode = document.getElementById("share-mode").value;
    const sourceUserIds = splitIds(document.getElementById("share-source-users").value);
    const targetUserIds = splitIds(document.getElementById("share-target-users").value);
    const targetGroupIds = splitIds(document.getElementById("share-target-groups").value);
    await StatApi.request("/api/teacher/share-rules", {
      method: "POST",
      body: JSON.stringify({
        stage,
        mode,
        source_user_ids: sourceUserIds,
        target_user_ids: targetUserIds,
        target_group_ids: targetGroupIds,
      }),
    });
    document.getElementById("share-source-users").value = "";
    document.getElementById("share-target-users").value = "";
    document.getElementById("share-target-groups").value = "";
    StatApi.toast("공유 규칙을 저장했습니다.");
    await load();
  }

  async function showReport(reportId) {
    const report = await StatApi.request(`/api/reports/${reportId}`);
    const chart = report.chart_urls?.[0]
      ? `<img class="analysis-image" src="${StatApi.chartUrl(report.chart_urls[0])}" alt="제출 차트" />`
      : "";
    const analyses = await StatApi.request(`/api/projects/${report.project_id}/analyses`).catch(() => []);
    const interpretations = (analyses || []).filter((analysis) => (analysis.interpretation || "").trim());
    reportDetail.innerHTML = `
      <h3>${escapeHtml(report.topic_title)}</h3>
      <p class="muted">${escapeHtml((report.dataset_names || [report.dataset_name]).join(", "))}</p>
      ${chart}
      <h3>결과별 학생 해석</h3>
      ${
        interpretations.length
          ? interpretations
              .map(
                (analysis) => `
                  <article class="report-source-item">
                    <strong>${escapeHtml(toolLabel(analysis.tool_name))}</strong>
                    <p>${escapeHtml(analysis.interpretation)}</p>
                  </article>
                `,
              )
              .join("")
          : `<p class="muted">아직 저장한 해석이 없습니다.</p>`
      }
      <h3>학생 결론</h3>
      <p${report.conclusion_text ? "" : ' class="muted"'}>${escapeHtml(report.conclusion_text || "아직 결론을 쓰지 않았습니다.")}</p>
      <h3>피드백</h3>
      <textarea id="feedback-text">${escapeHtml(report.feedback_text || "")}</textarea>
      <button class="primary" id="save-feedback">저장</button>
    `;
    document.getElementById("save-feedback").addEventListener("click", async () => {
      const feedbackText = document.getElementById("feedback-text").value;
      await StatApi.request(`/api/reports/${report.report_id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback_text: feedbackText }),
      });
      await load();
      await showReport(report.report_id);
    });
  }

  function renderLoginWait() {
    const authError = StatAuth.getAuthError?.();
    reportList.innerHTML = authError
      ? `<p class="muted">${authError} 로그아웃 후 허용된 Google 계정으로 다시 로그인해 주세요.</p>`
      : `<p class="muted">Google 로그인 후 보고서를 불러옵니다.</p>`;
    studentList.innerHTML = "";
    blockedList.innerHTML = "";
    if (hierarchyTarget) hierarchyTarget.innerHTML = "";
    shareRuleList.innerHTML = "";
    summary.innerHTML = "";
    reportDetail.innerHTML = "";
  }

  async function bootstrap() {
    if (!StatAuth.getAdminActAsUserId?.()) {
      StatState.setRole("teacher");
    }
    await StatAuth.init();
    if (
      StatAuth.isFirebaseMode?.()
      && StatAuth.isSignedIn?.()
      && !["teacher", "admin"].includes(StatAuth.getEffectiveRole?.())
    ) {
      StatAuth.redirectToRoleHome();
      return;
    }
    document.getElementById("student-preview-btn").addEventListener("click", () => {
      StatAuth.startStudentPreview();
    });
    document.getElementById("refresh-btn").addEventListener("click", () => load().catch((error) => StatApi.toast(error.message)));
    document.getElementById("school-level-form").addEventListener("submit", (event) => saveSchoolLevel(event).catch((error) => StatApi.toast(error.message)));
    document.getElementById("topic-template-form").addEventListener("submit", (event) => saveTopicTemplate(event).catch((error) => StatApi.toast(error.message)));
    document.getElementById("share-rule-form").addEventListener("submit", (event) => saveShareRule(event).catch((error) => StatApi.toast(error.message)));
    if (StatAuth.isSignedIn()) {
      await load();
    } else {
      renderLoginWait();
    }
    window.setInterval(() => {
      if (StatAuth.isSignedIn()) {
        load().catch(() => undefined);
      }
    }, 10000);
  }

  window.addEventListener("stat-auth-changed", () => {
    if (StatAuth.isSignedIn()) {
      if (
        StatAuth.isFirebaseMode?.()
        && !["teacher", "admin"].includes(StatAuth.getEffectiveRole?.())
      ) {
        StatAuth.redirectToRoleHome();
        return;
      }
      load().catch((error) => StatApi.toast(error.message));
    } else {
      renderLoginWait();
    }
  });
  const lessonsEntry = document.getElementById("lessons-entry");
  if (lessonsEntry && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    lessonsEntry.href = `http://${window.location.hostname}:8001/`;
  }

  bootstrap().catch((error) => {
    StatApi.toast(error.message);
    renderLoginWait();
  });
})();
