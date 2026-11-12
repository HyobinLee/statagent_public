(function () {
  function fillInline(element, text) {
    element.textContent = "";
    String(text ?? "").split(/\*\*([^*]+)\*\*/g).forEach((part, index) => {
      if (!part) return;
      if (index % 2 === 1) {
        const term = document.createElement("strong");
        term.className = "lesson-term";
        term.textContent = part;
        element.appendChild(term);
      } else {
        element.appendChild(document.createTextNode(part));
      }
    });
  }

  function renderExplain(container, block) {
    container.innerHTML = "";
    const heading = document.createElement("h3");
    heading.className = "lesson-step-heading";
    const iconMarkup = window.LessonKit.getStepIcon ? window.LessonKit.getStepIcon(block) : "";
    if (iconMarkup) {
      const icon = document.createElement("span");
      icon.className = "lesson-step-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.innerHTML = iconMarkup;
      heading.appendChild(icon);
    }
    const titleText = document.createElement("span");
    titleText.textContent = block.title || "";
    heading.appendChild(titleText);
    container.appendChild(heading);
    (block.body || []).forEach((paragraph) => {
      const p = document.createElement("p");
      fillInline(p, paragraph);
      container.appendChild(p);
    });
    if (block.sample?.length) {
      const pre = document.createElement("pre");
      pre.className = "lesson-sample";
      pre.textContent = block.sample.join("\n");
      container.appendChild(pre);
    }
    if (block.checklist?.length) {
      const list = document.createElement("ol");
      list.className = "lesson-checklist";
      block.checklist.forEach((item) => {
        const li = document.createElement("li");
        const text = document.createElement("strong");
        text.textContent = typeof item === "string" ? item : item.text || "";
        li.appendChild(text);
        const why = typeof item === "string" ? "" : item.why || "";
        if (why) {
          const span = document.createElement("span");
          span.className = "lesson-checklist-why";
          span.textContent = why;
          li.appendChild(span);
        }
        list.appendChild(li);
      });
      container.appendChild(list);
    }
    if (block.figure) appendFigure(container, block.figure, block.figure_alt || block.title);
  }

  function appendFigure(container, src, alt) {
    const img = document.createElement("img");
    img.className = "lesson-figure";
    img.src = src;
    img.alt = alt || "";
    img.loading = "lazy";
    container.appendChild(img);
    return img;
  }

  async function renderColumnMeaningAsk(body, card, ctx) {
    renderExplain(body, card);
    const askButton = document.createElement("button");
    askButton.type = "button";
    askButton.className = "lesson-connector-fetch";
    askButton.textContent = card.button_label || "에이전트에게 물어보기";
    body.appendChild(askButton);
    askButton.addEventListener("click", async () => {
      askButton.disabled = true;
      askButton.textContent = "에이전트가 답하는 중…";
      try {
        const meanings = await window.StatApi.request(
          `/api/projects/${encodeURIComponent(ctx.projectId)}/column-meaning-suggestions`,
        );
        askButton.remove();
        renderColumnMeanings(body, meanings);
      } catch (error) {
        askButton.disabled = false;
        askButton.textContent = card.button_label || "에이전트에게 물어보기";
        window.LessonKit.showError(error.message || "항목 설명을 불러오지 못했습니다.");
      }
    });
  }

  function renderColumnMeanings(container, meanings) {
    const list = document.createElement("dl");
    list.className = "lesson-column-meanings";
    (meanings || []).forEach((meaning) => {
      const term = document.createElement("dt");
      term.textContent = `${meaning.display_name || meaning.name} (${meaning.name})`;
      const description = document.createElement("dd");
      description.textContent = meaning.description || "";
      list.appendChild(term);
      list.appendChild(description);
    });
    container.appendChild(list);
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.fillInline = fillInline;
  window.LessonKit.appendFigure = appendFigure;
  window.LessonKit.renderExplain = renderExplain;
  window.LessonKit.renderColumnMeaningAsk = renderColumnMeaningAsk;
  window.LessonKit.renderColumnMeanings = renderColumnMeanings;
})();
