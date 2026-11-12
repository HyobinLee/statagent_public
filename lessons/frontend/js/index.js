(function () {

  const POLL_MS = 5000;

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name) || "";
  }

  function showListOnly() {
    document.getElementById("waitroom")?.remove();
    document.getElementById("lesson-list").hidden = false;
    document.querySelector(".lesson-title").hidden = false;
    document.querySelector(".lesson-topic").hidden = false;
  }

  function buildWaitroom() {
    const main = document.querySelector("main");
    const section = document.createElement("section");
    section.className = "waitroom";
    section.id = "waitroom";
    section.innerHTML = `
      <h1 class="waitroom-title">수업을 기다리는 중입니다</h1>
      <p class="waitroom-note">선생님이 수업을 열면 이 화면이 저절로 그 차시로 넘어갑니다. 그대로 두세요.</p>
      <div class="waitroom-dots" aria-hidden="true"><span></span><span></span><span></span></div>
      <p class="waitroom-meta"></p>
      <button type="button" class="waitroom-list">차시 목록 보기</button>`;
    main.insertBefore(section, document.getElementById("lesson-list"));
    document.getElementById("lesson-list").hidden = true;
    document.querySelector(".lesson-title").hidden = true;
    document.querySelector(".lesson-topic").hidden = true;
    return section;
  }

  function returnWhileFollowing() {
    async function tick() {
      try {
        const session = await window.StatApi.request("/api/lessons/sessions/me/current");
        if (session?.follow && session?.teacher_active && session?.lesson_id) {
          window.location.href = `./${session.lesson_id}.html`;
          return;
        }
      } catch (error) {
        if (error.code === "CLASS_NOT_ASSIGNED") return;
      }
      window.setTimeout(tick, POLL_MS);
    }
    tick();
  }

  async function run() {
    await (window.__authReady || Promise.resolve());
    if (!window.StatAuth?.isSignedIn?.()) return;
    if (window.StatAuth.getNavRole?.() !== "student") return;
    if (qs("list") === "1") {
      returnWhileFollowing();
      return;
    }

    const waitroom = buildWaitroom();
    const meta = waitroom.querySelector(".waitroom-meta");
    const profile = window.StatAuth.getProfile?.() || {};
    meta.textContent = [profile.class_id, profile.display_name].filter(Boolean).join(" ");
    waitroom.querySelector(".waitroom-list").addEventListener("click", () => {
      window.location.href = "./index.html?list=1";
    });

    let stopped = false;
    async function poll() {
      if (stopped) return;
      try {
        const session = await window.StatApi.request("/api/lessons/sessions/me/current");
        if (session?.teacher_active && session?.lesson_id) {
          stopped = true;
          waitroom.querySelector(".waitroom-title").textContent = "수업에 들어갑니다";
          waitroom.querySelector(".waitroom-note").textContent = "선생님이 연 차시로 이동합니다.";
          window.location.href = `./${session.lesson_id}.html`;
          return;
        }
      } catch (error) {
        if (error.code === "CLASS_NOT_ASSIGNED") {
          stopped = true;
          showListOnly();
          return;
        }
      }
      window.setTimeout(poll, POLL_MS);
    }
    poll();
  }

  run();
})();
