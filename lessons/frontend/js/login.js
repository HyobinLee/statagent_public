(async function () {
  await StatAuth.init().catch((error) => LessonKit.showError(error.message));

  const stepCode = document.getElementById("step-code");
  const stepName = document.getElementById("step-name");
  const stepPin = document.getElementById("step-pin");
  const codeForm = document.getElementById("code-form");
  const codeInput = document.getElementById("class-code");
  const nameList = document.getElementById("name-list");
  const pinForm = document.getElementById("pin-form");
  const pinInput = document.getElementById("student-pin");
  const chosenName = document.getElementById("chosen-name");

  let currentCode = "";
  let chosenStudent = null;

  const query = new URLSearchParams(window.location.search);
  const nextTarget = LessonKit.safeNextTarget(query.get("next"));

  const REASON_MESSAGES = {
    expired: "수업에 들어가려면 먼저 로그인해야 합니다. 참여 코드와 PIN을 입력해 주세요.",
    retry: "로그인이 확인되지 않았습니다. 참여 코드와 PIN을 다시 입력해 주세요.",
    switch: "다른 학급으로 들어가려면 참여 코드를 새로 입력해 주세요.",
  };

  function showReason() {
    const message = REASON_MESSAGES[query.get("reason") || ""];
    if (!message) return;
    const notice = document.createElement("p");
    notice.className = "lesson-access-notice";
    notice.textContent = message;
    stepCode.parentElement.insertBefore(notice, stepCode);
  }

  function showStep(step) {
    [stepCode, stepName, stepPin].forEach((section) => {
      section.hidden = section !== step;
    });
  }

  codeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = codeInput.value.trim().toUpperCase();
    if (!code) return;
    const submitButton = codeForm.querySelector("button");
    submitButton.disabled = true;
    try {
      const roster = await StatApi.request(`/api/lessons/student-auth/class/${encodeURIComponent(code)}`);
      if (!roster.students.length) {
        LessonKit.showError("이 학급에 아직 등록된 학생이 없습니다. 선생님께 알려 주세요.");
        return;
      }
      currentCode = roster.code;
      nameList.innerHTML = "";
      roster.students.forEach((student) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "login-name-button";
        button.textContent = student.display_name;
        button.addEventListener("click", () => {
          chosenStudent = student;
          chosenName.textContent = student.display_name;
          pinInput.value = "";
          showStep(stepPin);
          pinInput.focus();
        });
        nameList.appendChild(button);
      });
      showStep(stepName);
    } catch (error) {
      LessonKit.forgetClassCode();
      LessonKit.showError(error.message || "학급 코드를 확인하지 못했습니다.");
    } finally {
      submitButton.disabled = false;
    }
  });

  pinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!chosenStudent) return;
    const pin = pinInput.value.trim();
    if (!pin) return;
    const submitButton = pinForm.querySelector("button");
    submitButton.disabled = true;
    submitButton.textContent = "들어가는 중…";
    try {
      const result = await StatApi.request("/api/lessons/student-auth/login", {
        method: "POST",
        body: JSON.stringify({ code: currentCode, user_id: chosenStudent.user_id, pin }),
      });
      await StatAuth.loginWithCustomToken(result.custom_token);
      LessonKit.rememberClassCode(currentCode);
      window.location.href = nextTarget ? `./${nextTarget}` : "./index.html";
    } catch (error) {
      pinInput.value = "";
      pinInput.focus();
      LessonKit.showError(error.message || "로그인하지 못했습니다.");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "들어가기";
    }
  });

  document.getElementById("back-to-code").addEventListener("click", () => showStep(stepCode));
  document.getElementById("back-to-name").addEventListener("click", () => showStep(stepName));

  showReason();

  const prefilledCode = query.get("code");
  if (prefilledCode) {
    codeInput.value = prefilledCode.trim().toUpperCase();
    codeForm.requestSubmit();
  }
})();
