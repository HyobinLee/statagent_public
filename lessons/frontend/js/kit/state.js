(function () {
  const TRACKS = ["m1", "m3", "high", "gifted"];

  function keyFor(lessonId, track) {
    const safe = TRACKS.includes(track) ? track : "m3";
    return `lesson-progress:${lessonId}:${safe}`;
  }

  function getPosition(lessonId, track) {
    const raw = localStorage.getItem(keyFor(lessonId, track));
    if (!raw) return { step: 0, card: 0 };
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && Number.isFinite(parsed.step)) {
        return {
          step: parsed.step >= 0 ? parsed.step : 0,
          card: Number.isFinite(parsed.card) && parsed.card >= 0 ? parsed.card : 0,
        };
      }
    } catch (error) {
    }
    const numeric = Number(raw);
    return { step: Number.isFinite(numeric) && numeric >= 0 ? numeric : 0, card: 0 };
  }

  function setPosition(lessonId, position, track) {
    localStorage.setItem(
      keyFor(lessonId, track),
      JSON.stringify({ step: position.step || 0, card: position.card || 0 }),
    );
  }

  function syncResetMarker(lessonId, resetAt) {
    if (!resetAt) return false;
    const key = `lesson-reset-seen:${lessonId}`;
    if (localStorage.getItem(key) === resetAt) return false;
    localStorage.setItem(key, resetAt);
    TRACKS.forEach((track) => localStorage.removeItem(keyFor(lessonId, track)));
    clearSelfReveals(lessonId);
    return true;
  }

  const SELF_REVEAL_PREFIX = "lesson-self-reveal:";

  function selfRevealKey(context) {
    const userId = window.StatAuth?.getProfile?.()?.user_id || "anon";
    return `${SELF_REVEAL_PREFIX}${context.lessonId}:${context.track || ""}:${userId}`;
  }

  function readSelfReveals(context) {
    try {
      const parsed = JSON.parse(localStorage.getItem(selfRevealKey(context)) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function getSelfReveals(context, cardId) {
    const keys = readSelfReveals(context)[cardId];
    return Array.isArray(keys) ? keys : [];
  }

  function addSelfReveal(context, cardId, revealKey) {
    try {
      const all = readSelfReveals(context);
      const keys = Array.isArray(all[cardId]) ? all[cardId] : [];
      if (keys.includes(revealKey)) return;
      all[cardId] = [...keys, revealKey];
      localStorage.setItem(selfRevealKey(context), JSON.stringify(all));
    } catch (_error) {
    }
  }

  function clearSelfReveals(lessonId) {
    try {
      const prefix = `${SELF_REVEAL_PREFIX}${lessonId}:`;
      const stale = [];
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key && key.startsWith(prefix)) stale.push(key);
      }
      stale.forEach((key) => localStorage.removeItem(key));
    } catch (_error) {
    }
  }

  const remoteTimers = {};
  function savePositionRemote(context, position) {
    if (!context || context.role !== "student" || !window.StatApi) return;
    const lessonId = context.lessonId;
    window.clearTimeout(remoteTimers[lessonId]);
    remoteTimers[lessonId] = window.setTimeout(() => {
      window.StatApi
        .request(
          `/api/lessons/${encodeURIComponent(lessonId)}/position?track=${encodeURIComponent(context.track || "")}`,
          {
            method: "PUT",
            body: JSON.stringify({ step: position.step || 0, card: position.card || 0 }),
          },
        )
        .catch(() => {});
    }, 800);
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.savePositionRemote = savePositionRemote;
  window.LessonKit.syncResetMarker = syncResetMarker;
  window.LessonKit.getPosition = getPosition;
  window.LessonKit.setPosition = setPosition;
  window.LessonKit.getSelfReveals = getSelfReveals;
  window.LessonKit.addSelfReveal = addSelfReveal;
})();
