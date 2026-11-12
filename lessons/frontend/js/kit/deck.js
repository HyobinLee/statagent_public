(function () {

  const INHERITED_CARD_KEYS = ["side_panel", "sheet_limit", "sheet_columns", "dataset_from"];

  function inheritFromStep(step, card) {
    if (card === step) return card;
    const missing = INHERITED_CARD_KEYS.filter(
      (key) => step[key] !== undefined && card[key] === undefined,
    );
    if (!missing.length) return card;
    const merged = { ...card };
    missing.forEach((key) => {
      merged[key] = step[key];
    });
    return merged;
  }

  function flattenSteps(steps) {
    const flat = [];
    (steps || []).forEach((step, stepIndex) => {
      const cards = step.cards && step.cards.length ? step.cards : [step];
      cards.forEach((card, cardIndex) => {
        flat.push({ stepIndex, cardIndex, cardCount: cards.length, card: inheritFromStep(step, card) });
      });
    });
    return flat;
  }

  function findFlatIndex(flat, stepIndex, cardIndex) {
    const index = flat.findIndex((item) => item.stepIndex === stepIndex && item.cardIndex === cardIndex);
    return index >= 0 ? index : 0;
  }

  function parseHashPosition() {
    const match = /s=(\d+)&c=(\d+)/.exec(window.location.hash);
    if (!match) return null;
    return { step: Number(match[1]), card: Number(match[2]) };
  }

  function createCardShell(card) {
    const section = document.createElement("section");
    section.className = "deck-card";
    section.id = `deck-card-${card.id}`;
    section.hidden = true;

    let sidePanel = null;
    const body = document.createElement("div");
    body.className = "deck-card-main";

    if (card.side_panel === "sheet") {
      section.classList.add("deck-card-split");
      sidePanel = document.createElement("div");
      sidePanel.className = "deck-card-side";
      section.appendChild(sidePanel);
    }
    section.appendChild(body);

    return { section, body, sidePanel, rendered: false, revealsApi: null };
  }

  async function resolveSheetDatasetId(card, context) {
    if (!card.dataset_from) return context.datasetId;
    const [source, key] = String(card.dataset_from).split(":");
    if (source !== "connector" || !key) return context.datasetId;
    const state = await window.StatApi.request(
      `/api/lessons/connectors/state/${encodeURIComponent(context.lessonId)}?track=${encodeURIComponent(context.track || "")}`,
    );
    return state?.[key]?.dataset_id || null;
  }

  async function renderSidePanel(shell, card, context) {
    shell.sidePanel.innerHTML = "";
    let datasetId = null;
    try {
      datasetId = await resolveSheetDatasetId(card, context);
    } catch (_error) {
      datasetId = null;
    }
    if (!datasetId) {
      const note = document.createElement("p");
      note.className = "lesson-note";
      note.textContent = "앞 카드에서 자료를 먼저 불러온 뒤 이 카드를 다시 열어 주세요.";
      shell.sidePanel.appendChild(note);
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "lesson-connector-fetch";
      retry.textContent = "자료 다시 확인하기";
      retry.addEventListener("click", () => renderSidePanel(shell, card, context));
      shell.sidePanel.appendChild(retry);
      return;
    }
    await window.LessonKit.renderSheet(shell.sidePanel, datasetId, {
      limit: card.sheet_limit || 60,
      columns: card.sheet_columns,
    });
  }

  function setupRestartControl(context) {
    const links = document.querySelector("#lesson-topline .present-settings-links");
    if (!links || links.querySelector(".lesson-restart")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lesson-restart";
    button.textContent = "다시 시작하기";
    button.addEventListener("click", () => {
      const confirmed = window.confirm(
        "이 차시를 처음 카드부터 다시 볼까요? 카드 위치만 처음으로 돌아가고, 이미 보낸 의견과 불러온 자료는 그대로 남습니다."
      );
      if (!confirmed) return;
      window.LessonKit.setPosition(context.lessonId, { step: 0, card: 0 }, context.track);
      window.history.replaceState(null, "", "#");
      window.location.reload();
    });
    links.appendChild(button);
  }

  async function renderDeck(container, def, context) {
    container.innerHTML = "";
    const renderers = context.renderers || {};
    const flat = flattenSteps(def.steps || []);
    if (!flat.length) return { goTo: () => {} };

    const isTeacherRole = context.role === "teacher" || context.role === "admin";
    const revealDefsByKey = {};
    flat.forEach((meta) => {
      if (meta.card.kind === "analysis" && meta.card.id && meta.card.tool_name) {
        revealDefsByKey[meta.card.id] = meta.card;
      }
      (meta.card.reveals || []).forEach((reveal) => {
        if (reveal.key && reveal.tool_name) revealDefsByKey[reveal.key] = reveal;
      });
    });
    if (!isTeacherRole) {
      setupRestartControl(context);
      document
        .querySelectorAll('#lesson-topline a[href="./index.html"]')
        .forEach((link) => {
          link.href = "./index.html?list=1";
        });
    }

    const topbar = document.createElement("div");
    topbar.className = "deck-topbar";
    const position = document.createElement("div");
    position.className = "deck-position";
    const progressTrack = document.createElement("div");
    progressTrack.className = "deck-progress";
    const progressFill = document.createElement("div");
    progressFill.className = "deck-progress-fill";
    progressTrack.appendChild(progressFill);
    topbar.appendChild(position);
    topbar.appendChild(progressTrack);
    const topline = document.getElementById("lesson-topline");
    if (topline) {
      topline.querySelector(".deck-topbar")?.remove();
      topline.prepend(topbar);
    } else {
      container.appendChild(topbar);
    }

    const badges = document.createElement("div");
    badges.className = "deck-badges";
    container.appendChild(badges);

    function createBadge(className, text) {
      const badge = document.createElement("div");
      badge.className = `deck-lock-badge ${className}`;
      badge.textContent = text;
      badge.hidden = true;
      badges.appendChild(badge);
      return badge;
    }

    const followBadge = createBadge(
      "deck-follow-badge",
      "선생님 화면을 함께 보고 있습니다. 카드는 선생님이 넘깁니다.",
    );
    const lockBadge = createBadge("deck-hold-badge", "선생님이 이 카드에 머무르도록 했습니다.");
    const rangeBadge = createBadge("deck-range-badge", "");

    const cardHost = document.createElement("div");
    cardHost.className = "deck-card-host";
    container.appendChild(cardHost);

    const gateNote = document.createElement("p");
    gateNote.className = "deck-gate-note";
    gateNote.textContent = "이 카드의 답을 보내면 다음 카드로 넘어갈 수 있습니다.";
    gateNote.hidden = true;
    container.appendChild(gateNote);

    const nav = document.createElement("div");
    nav.className = "deck-nav";
    const prevButton = document.createElement("button");
    prevButton.type = "button";
    prevButton.className = "deck-prev";
    prevButton.textContent = "← 이전";
    const nextButton = document.createElement("button");
    nextButton.type = "button";
    nextButton.className = "deck-next primary";
    nextButton.textContent = "다음 →";
    const nextLessonLabel = context.nextLessonLabel || "다음 차시로";
    const tocButton = document.createElement("button");
    tocButton.type = "button";
    tocButton.className = "deck-next primary";
    tocButton.textContent = context.onNextLesson ? nextLessonLabel : "목차로";
    tocButton.hidden = true;
    tocButton.addEventListener("click", () => {
      if (context.onNextLesson) {
        context.onNextLesson();
        return;
      }
      window.location.href = isTeacherRole ? "./index.html" : "./index.html?list=1";
    });
    nav.appendChild(prevButton);
    nav.appendChild(nextButton);
    nav.appendChild(tocButton);
    container.appendChild(nav);

    const shells = flat.map((meta) => {
      const shell = createCardShell(meta.card);
      cardHost.appendChild(shell.section);
      return shell;
    });

    let currentIndex = 0;
    let locked = false;
    let following = false;
    let allowedIndices = null;
    let seenSession = false;
    let lastPushedAt = null;
    let latestSession = null;

    function applyRevealsToShell(shell, session) {
      if (!shell.revealsApi || !session?.reveals) return;
      Object.entries(session.reveals).forEach(([key, value]) => {
        if (value) shell.revealsApi.trigger(key);
      });
    }

    function applyRevealsEverywhere(session) {
      latestSession = session;
      shells.forEach((shell) => applyRevealsToShell(shell, session));
    }

    function updateTopbar() {
      const meta = flat[currentIndex];
      position.textContent = `${meta.stepIndex + 1}단계 ${meta.cardIndex + 1}/${meta.cardCount}`;
      progressFill.style.width = `${((currentIndex + 1) / flat.length) * 100}%`;
    }

    function sessionTargetsThisLesson(lessonId) {
      return !lessonId || lessonId === context.lessonId;
    }

    function allowedListFor(session) {
      const cards = Array.isArray(session?.range) ? session.range : null;
      if (!cards || !cards.length) return null;
      if (!sessionTargetsThisLesson(session.range_lesson_id)) return null;
      const indices = [];
      cards.forEach((item) => {
        const index = flat.findIndex(
          (meta) => meta.stepIndex === Number(item.step) && meta.cardIndex === Number(item.card),
        );
        if (index >= 0 && !indices.includes(index)) indices.push(index);
      });
      indices.sort((a, b) => a - b);
      return indices.length ? indices : null;
    }

    function neighborIndex(delta) {
      if (!allowedIndices) {
        const next = currentIndex + delta;
        return next >= 0 && next < flat.length ? next : -1;
      }
      const position = allowedIndices.indexOf(currentIndex);
      if (position < 0) return allowedIndices[0] ?? -1;
      const next = allowedIndices[position + delta];
      return next === undefined ? -1 : next;
    }

    function navBlocked() {
      return locked || following;
    }

    function promptGateBlocked() {
      const shell = shells[currentIndex];
      return [shell?.promptsApi, shell?.gateApi].some((api) => api && !api.isAllComplete());
    }

    function updateNavState() {
      const atEnd = neighborIndex(1) < 0;
      const gated = promptGateBlocked();
      gateNote.hidden = !gated;
      const showToc = atEnd && !allowedIndices;
      prevButton.disabled = navBlocked() || neighborIndex(-1) < 0;
      nextButton.hidden = showToc;
      nextButton.disabled = navBlocked() || atEnd || gated;
      tocButton.hidden = !showToc;
      tocButton.disabled = navBlocked() || gated;
    }

    function setLocked(value) {
      locked = value;
      lockBadge.hidden = !value;
      updateNavState();
    }

    function setFollowing(value) {
      following = value;
      followBadge.hidden = !value;
      shells.forEach((shell) => shell.revealsApi?.setFollowing?.(value));
      updateNavState();
    }

    function applyRange(session) {
      const next = allowedListFor(session);
      if (JSON.stringify(next) === JSON.stringify(allowedIndices)) return;
      allowedIndices = next;
      rangeBadge.hidden = !next;
      if (next) {
        rangeBadge.textContent = `선생님이 정한 학습 범위입니다. 이 ${next.length}장 안에서만 넘길 수 있습니다.`;
      }
      if (next && !next.includes(currentIndex)) {
        window.StatApi?.toast?.("선생님이 학습 범위를 정했습니다.");
        goToIndex(next[0], { force: true });
        return;
      }
      updateNavState();
    }

    async function renderCardIfNeeded(index) {
      const shell = shells[index];
      if (shell.rendered) return;
      shell.rendered = true;
      const card = flat[index].card;
      const renderer = renderers[card.kind];
      try {
        if (renderer) {
          const rendered = await renderer(shell.body, card, context);
          if (rendered && typeof rendered.isAllComplete === "function" && !isTeacherRole) {
            shell.gateApi = rendered;
            rendered.onChange?.(() => updateNavState());
          }
        } else {
          const notice = document.createElement("p");
          notice.textContent = `아직 지원하지 않는 카드 종류입니다: ${card.kind}`;
          shell.body.appendChild(notice);
        }

        if (card.figure && !shell.body.querySelector("img.lesson-figure")) {
          window.LessonKit.appendFigure(shell.body, card.figure, card.figure_alt || card.title);
        }

        if (card.side_panel === "sheet" && shell.sidePanel) {
          await renderSidePanel(shell, card, context);
        }

        if (card.questions?.length) {
          const list = document.createElement("ul");
          list.className = "lesson-questions";
          card.questions.forEach((question) => {
            const li = document.createElement("li");
            li.textContent = question;
            list.appendChild(li);
          });
          shell.body.appendChild(list);
        }

        if (card.context_reveals?.length) {
          const contextWrap = document.createElement("div");
          contextWrap.className = "lesson-context-results";
          const label = document.createElement("p");
          label.className = "lesson-note";
          label.textContent = "앞 카드에서 연 결과입니다.";
          contextWrap.appendChild(label);
          let tableHintShown = false;
          shell.body.appendChild(contextWrap);
          card.context_reveals.forEach(async (key) => {
            const ref = revealDefsByKey[key];
            if (!ref) return;
            const host = document.createElement("div");
            host.className = "lesson-result";
            host.textContent = "결과를 불러오는 중…";
            contextWrap.appendChild(host);
            try {
              const result = await window.LessonKit.runFixedAnalysis(
                context.projectId,
                ref.tool_name,
                ref.tool_args,
                { lessonId: context.lessonId, key, track: context.track, scenario: context.scenario },
              );
              host.innerHTML = "";
              window.LessonKit.renderResultCard(host, result, { countLabel: ref.count_label });
              if (!tableHintShown && host.querySelector("table")) {
                tableHintShown = true;
                label.textContent = "앞 카드에서 연 결과입니다. 표의 숫자를 누르면 아래 입력란에 들어갑니다.";
                (shell.promptsApi || shell.promptsPreview)?.setClickableNumbers(true);
              }
            } catch (error) {
              host.textContent = "앞 카드의 결과를 불러오지 못했습니다. 앞 카드에서 먼저 열어 주세요.";
            }
          });
        }

        const canClickNumbers = Boolean(
          (card.reveals || []).some((reveal) => reveal.tool_name)
            || card.side_panel === "sheet"
            || ["analysis", "evidence", "column_guess"].includes(card.kind),
        );

        let promptsApi = null;
        if (card.prompts?.length && !isTeacherRole) {
          promptsApi = window.LessonKit.renderDiscussInputs(shell.body, card.prompts, context, {
            canClickNumbers,
          });
          shell.promptsApi = promptsApi;
          promptsApi.onChange(() => updateNavState());
        }

        let previewEl = null;
        if (card.prompts?.length && isTeacherRole) {
          previewEl = document.createElement("div");
          previewEl.className = "lesson-discuss-preview-host";
          shell.promptsPreview = window.LessonKit.renderDiscussInputs(previewEl, card.prompts, context, {
            canClickNumbers,
            preview: true,
          });
        }

        let footerEl = null;
        if (card.footer?.length) {
          footerEl = document.createElement("div");
          footerEl.className = "deck-footer";
          card.footer.forEach((line) => {
            const p = document.createElement("p");
            window.LessonKit.fillInline(p, line);
            footerEl.appendChild(p);
          });
          if (card.footer_after) footerEl.hidden = true;
          shell.body.appendChild(footerEl);
        }

        if (card.reveals?.length) {
          const hasPredict = !isTeacherRole
            && (card.prompts || []).some((prompt) => window.LessonKit.isPredictType(prompt.type));
          const answerGate = Boolean(promptsApi);
          const selfReveal = context.scenario === "exp2"
            && (card.prompts || []).some((prompt) => prompt.requires_resubmit);
          shell.revealsApi = window.LessonKit.renderReveals(
            shell.body,
            card,
            context,
            (key) => {
              if (footerEl && card.footer_after === key) footerEl.hidden = false;
              if (footerEl && !footerEl.hidden) shell.body.appendChild(footerEl);
              if (previewEl) shell.body.appendChild(previewEl);
              promptsApi?.showResubmits();
              shell.promptsPreview?.showResubmits();
            },
            {
              answerGate,
              answered: promptsApi ? promptsApi.isAllComplete() : true,
              lockHintText: hasPredict
                ? "위의 예측을 먼저 보내면 결과를 열 수 있습니다."
                : "위의 답을 먼저 보내면 열 수 있습니다.",
              selfReveal,
              onSelfOpen: (key) => window.LessonKit.addSelfReveal?.(context, card.id, key),
            },
          );
          if (answerGate) {
            promptsApi.onChange(() => {
              if (promptsApi.isAllComplete()) shell.revealsApi.setEnabled(true);
            });
          }
          if (selfReveal && !isTeacherRole && promptsApi) {
            const reopenKeys = window.LessonKit.getSelfReveals?.(context, card.id) || [];
            let reopened = false;
            const reopen = () => {
              if (reopened || !reopenKeys.length || !promptsApi.isAllComplete()) return;
              reopened = true;
              reopenKeys.forEach((key) => shell.revealsApi.open(key));
            };
            promptsApi.onChange(reopen);
            reopen();
          }
          shell.revealsApi.setFollowing?.(following);
          if (latestSession) applyRevealsToShell(shell, latestSession);
        }

        if (previewEl) shell.body.appendChild(previewEl);
      } catch (error) {
        window.LessonKit.showError(error.message || "카드를 불러오지 못했습니다.");
      }
    }

    async function goToIndex(index, options = {}) {
      if (index < 0 || index >= flat.length) return;
      if (navBlocked() && !options.force) return;
      if (!options.force && allowedIndices && !allowedIndices.includes(index)) return;
      if (shells[currentIndex]) shells[currentIndex].section.hidden = true;
      currentIndex = index;
      const shell = shells[currentIndex];
      shell.section.hidden = false;
      await renderCardIfNeeded(currentIndex);
      updateTopbar();
      updateNavState();
      const meta = flat[currentIndex];
      window.LessonKit.setPosition(context.lessonId, { step: meta.stepIndex, card: meta.cardIndex }, context.track);
      window.LessonKit.savePositionRemote?.(context, { step: meta.stepIndex, card: meta.cardIndex });
      window.history.replaceState(null, "", `#s=${meta.stepIndex}&c=${meta.cardIndex}`);
      if (!options.silent) {
        shell.section.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      context.onCardChange?.(meta.card, meta);
    }

    prevButton.addEventListener("click", () => goToIndex(neighborIndex(-1)));
    nextButton.addEventListener("click", () => goToIndex(neighborIndex(1)));

    function handleKeydown(event) {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (navBlocked()) return;
      if (event.key === "ArrowRight") goToIndex(neighborIndex(1));
      if (event.key === "ArrowLeft") goToIndex(neighborIndex(-1));
    }
    document.addEventListener("keydown", handleKeydown);

    let unwatchSession = null;
    if (context.classId) {
      let leavingForTeacherLesson = false;
      unwatchSession = window.LessonKit.watchSession(context.classId, (session) => {
        if (leavingForTeacherLesson) return;
        applyRevealsEverywhere(session);
        if (!isTeacherRole) {
          const teacherLive = Boolean(session.teacher_active);
          const sameLesson = sessionTargetsThisLesson(session.lesson_id);
          setLocked(Boolean(session.lock) && teacherLive && sameLesson);
          setFollowing(Boolean(session.follow) && teacherLive && sameLesson);
          applyRange(session);
          if (session.follow && teacherLive && !sameLesson && session.lesson_id) {
            leavingForTeacherLesson = true;
            window.location.href = `./${encodeURIComponent(session.lesson_id)}.html`;
            return;
          }
        }
        const isFirstCallback = !seenSession;
        seenSession = true;
        const pushedChanged = session.pushed_at !== lastPushedAt;
        lastPushedAt = session.pushed_at;
        const focusLessonId = session.focus_lesson_id || session.lesson_id;
        const wantsSync = sessionTargetsThisLesson(focusLessonId) && (following
          ? Boolean(session.pushed_at)
          : pushedChanged && !isFirstCallback && Boolean(session.pushed_at));
        if (wantsSync && !isTeacherRole && session.focus) {
          const target = findFlatIndex(flat, session.focus.step, session.focus.card);
          if (target !== currentIndex) {
            goToIndex(target, { force: true });
            if (!following) window.StatApi?.toast?.("선생님이 이 카드로 안내했습니다.");
          }
        }
      });
    }

    const initialPos =
      parseHashPosition() || context.serverPosition || window.LessonKit.getPosition(context.lessonId, context.track);
    const initialIndex = findFlatIndex(flat, initialPos.step, initialPos.card);
    await goToIndex(initialIndex, { silent: true, force: true });

    return {
      goTo(stepIndex, cardIndex) {
        return goToIndex(findFlatIndex(flat, stepIndex, cardIndex), { force: true });
      },
      destroy() {
        document.removeEventListener("keydown", handleKeydown);
        if (unwatchSession) unwatchSession();
      },
    };
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.renderDeck = renderDeck;
  window.LessonKit.flattenDeckSteps = flattenSteps;
})();
