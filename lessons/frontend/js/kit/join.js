(function () {

  function loginBaseUrl() {
    return new URL("./login.html", window.location.href).href;
  }

  function joinLink(code, joinUrl) {
    if (joinUrl) return joinUrl;
    return `${loginBaseUrl()}?code=${encodeURIComponent(code)}`;
  }

  function displayLink(code, joinUrl) {
    const link = joinUrl || loginBaseUrl();
    return link.replace(/^https?:\/\//, "");
  }

  function renderCodeBoxes(container, code) {
    container.innerHTML = "";
    (code.match(/.{1,2}/g) || [code]).forEach((chunk) => {
      const box = document.createElement("div");
      box.className = "join-code-box";
      box.textContent = chunk;
      container.appendChild(box);
    });
  }

  function qrPayload(text) {
    try {
      return new URL(text).href;
    } catch (error) {
      return text;
    }
  }

  function renderQr(container, text) {
    container.innerHTML = "";
    if (typeof window.qrcode !== "function") {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = "QR 코드를 만들 수 없습니다. 위 주소와 코드를 알려 주세요.";
      container.appendChild(note);
      return;
    }
    const qr = window.qrcode(0, "M");
    qr.addData(qrPayload(text));
    qr.make();
    container.innerHTML = qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
  }

  function buildModal() {
    const overlay = document.createElement("div");
    overlay.className = "join-overlay";
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="join-modal" role="dialog" aria-modal="true" aria-labelledby="join-modal-title">
        <button type="button" class="join-close" aria-label="닫기">×</button>
        <h2 class="join-title" id="join-modal-title">학생 여러분 안녕하세요!</h2>
        <p class="join-link-line">다음 링크를 열고: <a class="join-link" target="_blank" rel="noopener"></a></p>
        <p class="join-code-label">다음 코드를 입력하세요</p>
        <div class="join-code-boxes"></div>
        <div class="join-share">
          <div class="join-qr" aria-label="참여 주소 QR 코드"></div>
          <div class="join-share-side">
            <p class="join-code-label join-qr-caption"></p>
            <div class="join-invite">
              <span class="join-invite-url"></span>
              <button type="button" class="join-copy">복사</button>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const close = () => {
      overlay.hidden = true;
    };
    overlay.querySelector(".join-close").addEventListener("click", close);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !overlay.hidden) close();
    });

    return overlay;
  }

  let overlayEl = null;

  function openJoinModal({ code, joinUrl, className }) {
    if (!code) return;
    if (!overlayEl) overlayEl = buildModal();

    overlayEl.querySelector(".join-title").textContent = className
      ? `${className} 학생 여러분 안녕하세요!`
      : "학생 여러분 안녕하세요!";

    const invite = joinLink(code, joinUrl);
    const linkEl = overlayEl.querySelector(".join-link");
    linkEl.textContent = displayLink(code, joinUrl);
    linkEl.href = joinUrl || loginBaseUrl();

    renderCodeBoxes(overlayEl.querySelector(".join-code-boxes"), code);
    renderQr(overlayEl.querySelector(".join-qr"), invite);

    overlayEl.querySelector(".join-qr-caption").textContent = joinUrl
      ? "휴대폰으로 QR을 찍으면 접속 주소가 열립니다."
      : "휴대폰으로 QR을 찍으면 코드까지 자동으로 입력됩니다.";

    overlayEl.querySelector(".join-invite-url").textContent = invite;
    const copyButton = overlayEl.querySelector(".join-copy");
    copyButton.textContent = "복사";
    copyButton.onclick = async () => {
      try {
        await navigator.clipboard.writeText(invite);
        copyButton.textContent = "복사됨";
      } catch (error) {
        copyButton.textContent = "복사 실패";
      }
    };

    overlayEl.hidden = false;
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.openJoinModal = openJoinModal;
  window.LessonKit.joinLink = joinLink;
})();
