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
    return localStorage.getItem("lesson-role") || "student";
  }

  function setRole(role) {
    if (users[role]) {
      localStorage.setItem("lesson-role", role);
    }
  }

  function getUser() {
    return users[getRole()] || users.student;
  }

  window.StatState = {
    users,
    getRole,
    setRole,
    getUser,
  };
})();
