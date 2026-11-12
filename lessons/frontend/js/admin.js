(async function () {
  await StatAuth.init().catch((error) => StatApi.toast(error.message));

  const classesContainer = document.getElementById("classes-container");
  const usersContainer = document.getElementById("users-container");
  const routeForm = document.getElementById("route-form");
  const routeClassInput = document.getElementById("route-class-id");
  const routeTeacherSelect = document.getElementById("route-teacher");
  const routeStudentsContainer = document.getElementById("route-students");
  const createUserForm = document.getElementById("create-user-form");

  let users = [];
  let classes = [];

  async function loadAll() {
    classesContainer.textContent = "불러오는 중…";
    usersContainer.textContent = "불러오는 중…";
    try {
      [classes, users] = await Promise.all([
        StatApi.request("/api/admin/classes"),
        StatApi.request("/api/admin/users"),
      ]);
    } catch (error) {
      classesContainer.textContent = "";
      usersContainer.textContent = "";
      StatApi.toast(error.message || "배정 정보를 불러오지 못했습니다.");
      return;
    }
    renderClasses();
    renderRouteForm();
    renderUsers();
  }

  function renderClasses() {
    classesContainer.innerHTML = "";
    if (!classes.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "아직 학급에 배정된 학생이 없습니다.";
      classesContainer.appendChild(empty);
      return;
    }
    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["학급 ID", "담당 교사", "인원"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    classes.forEach((row) => {
      const tr = document.createElement("tr");
      const idCell = document.createElement("td");
      idCell.textContent = row.class_id;
      tr.appendChild(idCell);
      const teacherCell = document.createElement("td");
      teacherCell.textContent = row.teacher_names.length ? row.teacher_names.join(", ") : "미배정";
      tr.appendChild(teacherCell);
      const countCell = document.createElement("td");
      countCell.textContent = String(row.member_count);
      tr.appendChild(countCell);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    classesContainer.appendChild(table);
  }

  function renderRouteForm() {
    const teachers = users.filter((user) => user.role === "teacher");
    routeTeacherSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "담당 교사 선택";
    routeTeacherSelect.appendChild(placeholder);
    teachers.forEach((teacher) => {
      const option = document.createElement("option");
      option.value = teacher.user_id;
      option.textContent = `${teacher.display_name} · ${teacher.email}`;
      routeTeacherSelect.appendChild(option);
    });

    const students = users.filter((user) => user.role === "student");
    routeStudentsContainer.innerHTML = "";
    if (!students.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "학생 계정이 아직 없습니다. 먼저 계정을 추가하세요.";
      routeStudentsContainer.appendChild(empty);
      return;
    }
    students.forEach((student) => {
      const label = document.createElement("label");
      label.className = "lesson-topic-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = student.user_id;
      checkbox.name = "route-student";
      const text = document.createElement("span");
      text.textContent = `${student.display_name} · ${student.email} (현재: ${student.class_id || "미배정"})`;
      label.appendChild(checkbox);
      label.appendChild(text);
      routeStudentsContainer.appendChild(label);
    });
  }

  function renderUsers() {
    usersContainer.innerHTML = "";
    if (!users.length) {
      const empty = document.createElement("p");
      empty.className = "lesson-note";
      empty.textContent = "계정이 없습니다.";
      usersContainer.appendChild(empty);
      return;
    }
    const table = document.createElement("table");
    table.className = "lesson-sheet";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    ["이름", "이메일", "역할", "학급", "담당 교사 ID", "관리"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    users.forEach((user) => {
      const tr = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = user.display_name;
      tr.appendChild(nameCell);

      const emailCell = document.createElement("td");
      emailCell.textContent = user.email;
      tr.appendChild(emailCell);

      const roleCell = document.createElement("td");
      const roleSelect = document.createElement("select");
      ["student", "teacher", "admin"].forEach((role) => {
        const option = document.createElement("option");
        option.value = role;
        option.textContent = { student: "학생", teacher: "교사", admin: "관리자" }[role];
        if (role === user.role) option.selected = true;
        roleSelect.appendChild(option);
      });
      roleCell.appendChild(roleSelect);
      tr.appendChild(roleCell);

      const classCell = document.createElement("td");
      const classInput = document.createElement("input");
      classInput.type = "text";
      classInput.value = user.class_id || "";
      classInput.placeholder = "학급 ID";
      classCell.appendChild(classInput);
      tr.appendChild(classCell);

      const teacherCell = document.createElement("td");
      const teacherInput = document.createElement("input");
      teacherInput.type = "text";
      teacherInput.value = user.teacher_id || "";
      teacherInput.placeholder = "교사 user_id";
      teacherCell.appendChild(teacherInput);
      tr.appendChild(teacherCell);

      const actionCell = document.createElement("td");
      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.textContent = "저장";
      saveButton.addEventListener("click", () => {
        updateUser(user.user_id, {
          role: roleSelect.value,
          class_id: classInput.value.trim() || null,
          teacher_id: teacherInput.value.trim() || null,
        }).catch((error) => StatApi.toast(error.message));
      });
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.textContent = "삭제";
      deleteButton.addEventListener("click", () => {
        deleteUser(user.user_id).catch((error) => StatApi.toast(error.message));
      });
      actionCell.appendChild(saveButton);
      actionCell.appendChild(deleteButton);
      tr.appendChild(actionCell);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    usersContainer.appendChild(table);
  }

  async function updateUser(userId, payload) {
    await StatApi.request(`/api/admin/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    await loadAll();
  }

  async function deleteUser(userId) {
    await StatApi.request(`/api/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
    await loadAll();
  }

  createUserForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const email = document.getElementById("new-user-email").value.trim();
    const displayName = document.getElementById("new-user-name").value.trim();
    const role = document.getElementById("new-user-role").value;
    StatApi.request("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({ email, display_name: displayName, role }),
    })
      .then(() => {
        createUserForm.reset();
        return loadAll();
      })
      .catch((error) => StatApi.toast(error.message));
  });

  routeForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const classId = routeClassInput.value.trim();
    const teacherId = routeTeacherSelect.value;
    const studentIds = Array.from(
      routeStudentsContainer.querySelectorAll('input[name="route-student"]:checked'),
    ).map((input) => input.value);
    if (!teacherId || !studentIds.length) {
      StatApi.toast("담당 교사와 배정할 학생을 최소 1명 골라 주세요.");
      return;
    }
    StatApi.request("/api/admin/hierarchy-route", {
      method: "POST",
      body: JSON.stringify({ class_id: classId, teacher_id: teacherId, student_ids: studentIds }),
    })
      .then(() => {
        routeForm.reset();
        return loadAll();
      })
      .catch((error) => StatApi.toast(error.message));
  });

  await loadAll();
})();
