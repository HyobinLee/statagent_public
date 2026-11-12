(function () {
  const statusTarget = document.getElementById("admin-status");
  const usersTarget = document.getElementById("admin-users");
  const classesTarget = document.getElementById("admin-classes");
  const hierarchyTarget = document.getElementById("admin-hierarchy");
  const projectsTarget = document.getElementById("admin-projects");
  const usageTarget = document.getElementById("admin-usage");
  const readinessTarget = document.getElementById("admin-readiness");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function table(headers, rows, className = "") {
    return `
      <table class="${escapeHtml(className)}">
        <thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    `;
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

  function bulkToolbar(group, label, actions) {
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
      <p class="bulk-hint muted">${escapeHtml(label)}을 여러 건 처리할 때는 체크박스로 대상을 고른 뒤 일괄 작업을 실행합니다.</p>
    `;
  }

  async function runSequential(items, task) {
    for (const item of items) {
      await task(item);
    }
  }

  async function deleteUsers(userIds) {
    const ids = [...new Set(userIds)].filter(Boolean);
    if (!ids.length) return;
    const message =
      ids.length === 1
        ? "사용자와 해당 사용자의 프로젝트를 삭제할까요?"
        : `선택한 사용자 ${ids.length}명과 해당 사용자의 프로젝트를 삭제할까요?`;
    if (!window.confirm(message)) return;
    await runSequential(ids, (userId) => StatApi.request(`/api/admin/users/${userId}`, { method: "DELETE" }));
    StatApi.toast(`사용자 ${ids.length}명을 삭제했습니다.`);
    await load();
  }

  async function deleteProjects(projectIds) {
    const ids = [...new Set(projectIds)].filter(Boolean);
    if (!ids.length) return;
    const message =
      ids.length === 1
        ? "프로젝트와 연결된 분석/보고서를 삭제할까요?"
        : `선택한 프로젝트 ${ids.length}개와 연결된 분석/보고서를 삭제할까요?`;
    if (!window.confirm(message)) return;
    await runSequential(ids, (projectId) => StatApi.request(`/api/admin/projects/${projectId}`, { method: "DELETE" }));
    StatApi.toast(`프로젝트 ${ids.length}개를 삭제했습니다.`);
    await load();
  }

  async function setUsersBlocked(userIds, shouldBlock, askConfirmation = false) {
    const ids = [...new Set(userIds)].filter(Boolean);
    if (!ids.length) return;
    const label = shouldBlock ? "일시정지" : "해제";
    if (askConfirmation && !window.confirm(`선택한 사용자 ${ids.length}명을 ${label}할까요?`)) return;
    await runSequential(ids, (userId) =>
      StatApi.request(`/api/admin/users/${userId}/${shouldBlock ? "block" : "unblock"}`, {
        method: "POST",
        body: shouldBlock ? JSON.stringify({ reason: "관리자 일괄 일시정지" }) : "{}",
      }),
    );
    StatApi.toast(`사용자 ${ids.length}명을 ${label}했습니다.`);
    await load();
  }

  function teacherName(teachers, teacherId) {
    return teachers.find((teacher) => teacher.user_id === teacherId)?.display_name || teacherId || "-";
  }

  function keyStatusLabel(status) {
    const labels = {
      missing: "미설정",
      no_expiration: "무기한",
      valid: "정상",
      expiring_soon: "만료 임박",
      expired: "만료",
      invalid_expiry: "만료일 오류",
      untracked: "추적 필요",
    };
    return labels[status] || status || "-";
  }

  function renderStatApiKeyAlert(keyStatus) {
    if (!keyStatus) return "";
    const alerts = keyStatus.alerts || [];
    const hasBlocked = alerts.some((item) => item.severity === "blocked");
    const className = hasBlocked ? "blocked" : alerts.length ? "attention" : "ok";
    const headline = hasBlocked ? "만료된 API Key가 있습니다" : alerts.length ? "API Key 점검이 필요합니다" : "API Key 유효기간 정상";
    const detail = alerts.length
      ? alerts.slice(0, 3).map((item) => `<li>${escapeHtml(item.message)}</li>`).join("")
      : `<li>만료 임박 또는 경과한 통계 API Key가 없습니다.</li>`;
    return `
      <div class="metric admin-key-alert ${className}">
        <span>API Key 유효기간</span>
        <strong>${escapeHtml(headline)}</strong>
        <ul>${detail}</ul>
      </div>
    `;
  }

  function renderStatApiKeyManagement(keyStatus) {
    if (!keyStatus) return "";
    const rows = keyStatus.keys || [];
    const summary = keyStatus.summary || {};
    const secretLabel = keyStatus.secret_configured ? keyStatus.secret_name : "미설정";
    return `
      <section class="key-status-panel">
        <div class="section-title compact-title">
          <div>
            <p class="eyebrow">API Key 관리</p>
            <h2>Secret Manager 유효기간 점검</h2>
            <p class="muted">Secret: ${escapeHtml(secretLabel)} · 만료 임박 기준 ${escapeHtml(keyStatus.warning_days || 30)}일</p>
          </div>
        </div>
        <div class="meta-row">
          <span class="chip">등록 ${escapeHtml(summary.configured || 0)}개</span>
          <span class="chip">미설정 ${escapeHtml(summary.missing || 0)}개</span>
          <span class="chip">임박 ${escapeHtml(summary.expiring_soon || 0)}개</span>
          <span class="chip">만료 ${escapeHtml(summary.expired || 0)}개</span>
        </div>
        ${table(
          ["키", "상태", "만료일", "남은 기간", "사용처", "운영 조치"],
          rows.map((item) => {
            const days =
              typeof item.days_remaining === "number"
                ? item.days_remaining < 0
                  ? `${Math.abs(item.days_remaining)}일 경과`
                  : `${item.days_remaining}일`
                : "-";
            return `
              <tr class="key-status-row ${escapeHtml(item.severity || "")}">
                <td>${escapeHtml(item.key_name)}</td>
                <td>${escapeHtml(keyStatusLabel(item.expiry_status))}</td>
                <td>${escapeHtml(item.expires_at || item.expires_at_raw || "-")}</td>
                <td>${escapeHtml(days)}</td>
                <td>${escapeHtml((item.usages || []).join(", ") || "-")}</td>
                <td>${escapeHtml(item.action || "-")}</td>
              </tr>
            `;
          }),
          "admin-data-table key-status-table",
        )}
      </section>
    `;
  }

  function renderHierarchyRouter(users, classes) {
    if (!hierarchyTarget) return;
    const students = users.filter((user) => user.role === "student");
    const teachers = users.filter((user) => user.role === "teacher");
    hierarchyTarget.innerHTML = `
      <form id="admin-hierarchy-form" class="hierarchy-router-form">
        <div class="hierarchy-route-line">
          <span>학생</span>
          <span>→</span>
          <label class="analysis-field">
            <span>학급</span>
            <input id="admin-route-class" list="admin-route-class-options" maxlength="80" placeholder="예: 1학년 3반" required />
          </label>
          <datalist id="admin-route-class-options">
            ${classes.map((item) => `<option value="${escapeHtml(item.class_id)}"></option>`).join("")}
          </datalist>
          <span>→</span>
          <label class="analysis-field">
            <span>담당 교사</span>
            <select id="admin-route-teacher" required>
              <option value="">교사 선택</option>
              ${teachers
                .map(
                  (teacher) =>
                    `<option value="${escapeHtml(teacher.user_id)}">${escapeHtml(teacher.display_name)} · ${escapeHtml(
                      teacher.email,
                    )}</option>`,
                )
                .join("")}
            </select>
          </label>
          <span>→ 관리자</span>
        </div>
        ${bulkToolbar(
          "admin-hierarchy",
          "배치할 학생",
          `<button type="submit" class="primary" data-bulk-requires="admin-hierarchy" disabled>선택 학생 배치</button>`,
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
                      data-bulk-item="admin-hierarchy"
                      value="${escapeHtml(student.user_id)}"
                      aria-label="${escapeHtml(student.display_name || student.email)} 선택"
                    />
                  </td>
                  <td>${escapeHtml(student.display_name)}<br /><span class="subtle">${escapeHtml(student.email)}</span></td>
                  <td>${escapeHtml(student.class_id || "미배정")}</td>
                  <td>${escapeHtml(teacherName(teachers, student.teacher_id))}</td>
                  <td>${escapeHtml(student.group_id || "-")}</td>
                </tr>
              `,
            ),
            "admin-data-table",
          )}
        </div>
      </form>
    `;
    attachBulkSelection(hierarchyTarget, "admin-hierarchy");
    document.getElementById("admin-hierarchy-form")?.addEventListener("submit", (event) => {
      routeAdminHierarchy(event).catch((error) => StatApi.toast(error.message));
    });
  }

  async function routeAdminHierarchy(event) {
    event.preventDefault();
    const studentIds = selectedBulkValues("admin-hierarchy");
    const classId = document.getElementById("admin-route-class")?.value.trim();
    const teacherId = document.getElementById("admin-route-teacher")?.value;
    if (!studentIds.length) {
      StatApi.toast("배치할 학생을 선택해 주세요.");
      return;
    }
    if (!classId || !teacherId) {
      StatApi.toast("학급과 담당 교사를 모두 선택해 주세요.");
      return;
    }
    await StatApi.request("/api/admin/hierarchy-route", {
      method: "POST",
      body: JSON.stringify({ class_id: classId, teacher_id: teacherId, student_ids: studentIds }),
    });
    StatApi.toast(`학생 ${studentIds.length}명을 ${classId} 학급에 배치했습니다.`);
    await load();
  }

  async function load() {
    const [status, users, classes] = await Promise.all([
      StatApi.request("/api/admin/status"),
      StatApi.request("/api/admin/users"),
      StatApi.request("/api/admin/classes"),
    ]);
    statusTarget.innerHTML = `
      <div class="metric"><span>APP_ENV</span><strong>${status.app_env}</strong></div>
      <div class="metric"><span>Gemini</span><strong>${status.enable_gemini ? "on" : "off"}</strong></div>
      <div class="metric"><span>Firestore</span><strong>${status.enable_firestore ? "on" : "off"}</strong></div>
      <div class="metric"><span>Cloud Storage</span><strong>${status.enable_cloud_storage ? "on" : "off"}</strong></div>
      <div class="metric"><span>Secret Manager</span><strong>${status.enable_secret_manager ? "on" : "off"}</strong></div>
      <div class="metric"><span>로컬 개발 인증</span><strong>${status.dev_auth_enabled ? "on" : "off"}</strong></div>
      <div class="metric"><span>Firebase Web</span><strong>${status.firebase_web_configured ? "set" : "missing"}</strong></div>
      <div class="metric"><span>GCP Project</span><strong>${status.google_cloud_project || "-"}</strong></div>
      <div class="metric"><span>GCS Bucket</span><strong>${status.gcs_chart_bucket || "-"}</strong></div>
      <div class="metric"><span>Dataset Bucket</span><strong>${status.gcs_dataset_bucket || "-"}</strong></div>
      <div class="metric"><span>최소 연령</span><strong>만 ${status.min_student_age || 14}세</strong></div>
      ${renderStatApiKeyAlert(status.stat_api_key_status)}
    `;
    const readiness = status.deployment_readiness || {};
    const statusLabel = { completed: "완료", attention: "점검", blocked: "차단" };
    readinessTarget.innerHTML =
      table(
        ["항목", "상태", "내용", "운영 조치"],
        (readiness.checks || []).map(
          (item) => `
            <tr>
              <td>${escapeHtml(item.title)}</td>
              <td>${escapeHtml(statusLabel[item.status] || item.status)}</td>
              <td>${escapeHtml(item.detail)}</td>
              <td>${escapeHtml(item.action || "-")}</td>
            </tr>
          `,
        ),
      ) + renderStatApiKeyManagement(status.stat_api_key_status);
    const currentUserId = StatAuth.getProfile?.()?.user_id || "";
    usersTarget.innerHTML =
      bulkToolbar(
        "admin-users",
        "사용자",
        `<button type="button" class="danger" data-bulk-delete-users data-bulk-requires="admin-users" disabled>선택 삭제</button>`,
      )
      + table(
      ["", "이름", "이메일", "역할", "학급", "담당 교사", "차단", "접근/수정"],
      users.map(
        (user) => {
          const isCurrentUser = currentUserId && user.user_id === currentUserId;
          const viewButton =
            user.role === "teacher" || user.role === "student"
              ? `<button data-view-user="${escapeHtml(user.user_id)}">화면 보기</button>`
              : "";
          return `<tr>
            <td class="row-select-cell">
              <input
                type="checkbox"
                data-bulk-item="admin-users"
                value="${escapeHtml(user.user_id)}"
                aria-label="${escapeHtml(user.display_name || user.email)} 선택"
                ${isCurrentUser ? "disabled" : ""}
              />
            </td>
            <td>${escapeHtml(user.display_name)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>${escapeHtml(user.role)}</td>
            <td>${escapeHtml(user.class_id || "-")}</td>
            <td>${escapeHtml(user.teacher_id || "-")}</td>
            <td>${user.is_blocked ? "예" : "아니오"}</td>
            <td>
              ${viewButton}
              <button data-edit-user="${escapeHtml(user.user_id)}">수정</button>
              <button class="danger" data-delete-user="${escapeHtml(user.user_id)}" ${
                isCurrentUser ? "disabled" : ""
              }>삭제</button>
            </td>
          </tr>`;
        },
      ),
      "admin-data-table",
    );
    renderHierarchyRouter(users, classes);
    classesTarget.innerHTML = table(
      ["학급", "담당 교사", "인원"],
      classes.map(
        (item) =>
          `<tr><td>${escapeHtml(item.class_id)}</td><td>${escapeHtml((item.teacher_names || []).join(", ") || "-")}</td><td>${item.member_count}</td></tr>`,
      ),
    );
    const [projects, usage] = await Promise.all([
      StatApi.request("/api/admin/projects"),
      StatApi.request("/api/admin/usage"),
    ]);
    projectsTarget.innerHTML =
      bulkToolbar(
        "admin-projects",
        "프로젝트",
        `<button type="button" class="danger" data-bulk-delete-projects data-bulk-requires="admin-projects" disabled>선택 삭제</button>`,
      )
      + table(
      ["", "소유자", "주제", "상태", "자료", "분석", ""],
      projects.map(
        (project) => `
          <tr>
            <td class="row-select-cell">
              <input
                type="checkbox"
                data-bulk-item="admin-projects"
                value="${escapeHtml(project.project_id)}"
                aria-label="${escapeHtml(project.custom_topic_question || project.custom_topic_title || project.topic_id || "프로젝트")} 선택"
              />
            </td>
            <td>${escapeHtml(project.owner_name || project.owner_email)}</td>
            <td>${escapeHtml(project.custom_topic_question || project.custom_topic_title || project.topic_id || "-")}</td>
            <td>${escapeHtml(project.status)}</td>
            <td>${project.dataset_ids?.length || (project.dataset_id ? 1 : 0)}</td>
            <td>${project.analysis_result_ids?.length || (project.latest_analysis_result_id ? 1 : 0)}</td>
            <td><button class="danger" data-delete-project="${escapeHtml(project.project_id)}">삭제</button></td>
          </tr>
        `,
      ),
      "admin-data-table",
    );
    usageTarget.innerHTML =
      bulkToolbar(
        "admin-usage",
        "호출량 사용자",
        `<button type="button" data-bulk-block-users data-bulk-requires="admin-usage" disabled>선택 일시정지</button>
        <button type="button" data-bulk-unblock-users data-bulk-requires="admin-usage" disabled>선택 해제</button>`,
      )
      + table(
      ["", "사용자", "AI 호출", "도구 호출", "우회", "차단", ""],
      usage.map(
        (row) => `
          <tr>
            <td class="row-select-cell">
              <input
                type="checkbox"
                data-bulk-item="admin-usage"
                value="${escapeHtml(row.user_id)}"
                aria-label="${escapeHtml(row.display_name || row.email)} 선택"
              />
            </td>
            <td>${escapeHtml(row.display_name || row.email)}</td>
            <td>${row.ai_call_count}</td>
            <td>${row.tool_call_count}</td>
            <td>${row.workflow_bypass_count}</td>
            <td>${row.blocked_count}</td>
            <td>
              <button data-block-user="${escapeHtml(row.user_id)}">일시정지</button>
              <button data-unblock-user="${escapeHtml(row.user_id)}">해제</button>
            </td>
          </tr>
        `,
      ),
      "admin-data-table",
    );
    attachAdminActions(users);
  }

  function attachAdminActions(users) {
    attachBulkSelection(usersTarget, "admin-users");
    attachBulkSelection(projectsTarget, "admin-projects");
    attachBulkSelection(usageTarget, "admin-usage");
    usersTarget.querySelector("[data-bulk-delete-users]")?.addEventListener("click", () =>
      deleteUsers(selectedBulkValues("admin-users")).catch((error) => StatApi.toast(error.message)),
    );
    projectsTarget.querySelector("[data-bulk-delete-projects]")?.addEventListener("click", () =>
      deleteProjects(selectedBulkValues("admin-projects")).catch((error) => StatApi.toast(error.message)),
    );
    usageTarget.querySelector("[data-bulk-block-users]")?.addEventListener("click", () =>
      setUsersBlocked(selectedBulkValues("admin-usage"), true, true).catch((error) => StatApi.toast(error.message)),
    );
    usageTarget.querySelector("[data-bulk-unblock-users]")?.addEventListener("click", () =>
      setUsersBlocked(selectedBulkValues("admin-usage"), false, true).catch((error) => StatApi.toast(error.message)),
    );
    usersTarget.querySelectorAll("[data-view-user]").forEach((button) => {
      button.addEventListener("click", () => {
        const user = users.find((item) => item.user_id === button.dataset.viewUser);
        if (!user) return;
        StatAuth.setAdminActAs(user.user_id, user.role);
      });
    });
    usersTarget.querySelectorAll("[data-edit-user]").forEach((button) => {
      button.addEventListener("click", () => {
        const user = users.find((item) => item.user_id === button.dataset.editUser);
        if (!user) return;
        document.getElementById("admin-user-email").value = user.email;
        document.getElementById("admin-user-name").value = user.display_name;
        document.getElementById("admin-user-role").value = user.role;
        document.getElementById("admin-user-class").value = user.class_id || "";
        document.getElementById("admin-user-teacher").value = user.teacher_id || "";
        document.getElementById("admin-user-group").value = user.group_id || "";
      });
    });
    document.querySelectorAll("[data-delete-user]").forEach((button) => {
      button.addEventListener("click", async () => {
        await deleteUsers([button.dataset.deleteUser]);
      });
    });
    document.querySelectorAll("[data-delete-project]").forEach((button) => {
      button.addEventListener("click", async () => {
        await deleteProjects([button.dataset.deleteProject]);
      });
    });
    document.querySelectorAll("[data-block-user]").forEach((button) => {
      button.addEventListener("click", async () => {
        await setUsersBlocked([button.dataset.blockUser], true);
      });
    });
    document.querySelectorAll("[data-unblock-user]").forEach((button) => {
      button.addEventListener("click", async () => {
        await setUsersBlocked([button.dataset.unblockUser], false);
      });
    });
  }

  async function saveUser(event) {
    event.preventDefault();
    await StatApi.request("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("admin-user-email").value,
        display_name: document.getElementById("admin-user-name").value,
        role: document.getElementById("admin-user-role").value,
        class_id: document.getElementById("admin-user-class").value || null,
        teacher_id: document.getElementById("admin-user-teacher").value || null,
        group_id: document.getElementById("admin-user-group").value || null,
      }),
    });
    document.getElementById("admin-user-form").reset();
    await load();
  }

  function renderLoginWait() {
    const authError = StatAuth.getAuthError?.();
    statusTarget.innerHTML = authError
      ? `<p class="muted">${authError} 로그아웃 후 허용된 Google 계정으로 다시 로그인해 주세요.</p>`
      : `<p class="muted">Google 로그인 후 관리자 정보를 불러옵니다.</p>`;
    usersTarget.innerHTML = "";
    classesTarget.innerHTML = "";
    projectsTarget.innerHTML = "";
    usageTarget.innerHTML = "";
    readinessTarget.innerHTML = "";
    if (hierarchyTarget) hierarchyTarget.innerHTML = "";
  }

  async function bootstrap() {
    StatAuth.clearAdminActAs?.();
    StatAuth.clearStudentPreview?.();
    StatState.setRole("admin");
    await StatAuth.init();
    if (StatAuth.isFirebaseMode?.() && StatAuth.isSignedIn?.() && StatAuth.getEffectiveRole?.() !== "admin") {
      StatAuth.redirectToRoleHome();
      return;
    }
    document.getElementById("admin-refresh-btn").addEventListener("click", () => load().catch((error) => StatApi.toast(error.message)));
    document.getElementById("admin-user-form").addEventListener("submit", saveUser);
    if (StatAuth.isSignedIn()) {
      await load();
    } else {
      renderLoginWait();
    }
  }

  window.addEventListener("stat-auth-changed", () => {
    if (StatAuth.isSignedIn()) {
      if (StatAuth.isFirebaseMode?.() && StatAuth.getEffectiveRole?.() !== "admin") {
        StatAuth.redirectToRoleHome();
        return;
      }
      load().catch((error) => StatApi.toast(error.message));
    } else {
      renderLoginWait();
    }
  });
  bootstrap().catch((error) => {
    StatApi.toast(error.message);
    renderLoginWait();
  });
})();
