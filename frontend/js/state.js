(function () {
  const users = {
    student: {
      email: "student1@example.com",
      role: "student",
      label: "학생 개발 계정",
    },
    teacher: {
      email: "teacher@example.com",
      role: "teacher",
      label: "교사 개발 계정",
    },
    admin: {
      email: "admin@example.com",
      role: "admin",
      label: "관리자",
    },
  };

  function getRole() {
    return localStorage.getItem("stat-agent-role") || "student";
  }

  function setRole(role) {
    if (users[role]) {
      localStorage.setItem("stat-agent-role", role);
    }
  }

  function getUser() {
    return users[getRole()] || users.student;
  }

  function setStudentState(nextState) {
    localStorage.setItem("stat-agent-student-state", JSON.stringify(nextState));
  }

  function getStudentState() {
    try {
      return JSON.parse(localStorage.getItem("stat-agent-student-state") || "{}");
    } catch (_error) {
      return {};
    }
  }

  function clearStudentState() {
    localStorage.removeItem("stat-agent-student-state");
  }

  window.StatState = {
    users,
    getRole,
    setRole,
    getUser,
    setStudentState,
    getStudentState,
    clearStudentState,
  };
})();
