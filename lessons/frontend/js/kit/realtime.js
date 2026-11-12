(function () {
  const POLL_INTERVAL_MS = 2000;

  const CLASS_SESSIONS_COLLECTION = "lesson_classSessions";
  const DISCUSS_RESPONSES_COLLECTION = "lesson_discussResponses";

  function isFirebaseMode() {
    return !!window.StatAuth?.isFirebaseMode?.();
  }

  function startPolling(fetchFn, onChange) {
    let stopped = false;
    let timer = null;

    async function tick() {
      if (stopped) return;
      try {
        const data = await fetchFn();
        if (!stopped) onChange(data);
      } catch (error) {
        console.warn("[lessons] 실시간 폴링 갱신 실패", error);
      }
      if (!stopped) {
        timer = window.setTimeout(tick, POLL_INTERVAL_MS);
      }
    }

    tick();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }

  function emptySession(classId) {
    return {
      class_id: classId,
      teacher_id: null,
      lesson_id: null,
      level: null,
      focus: { step: 0, card: 0 },
      pushed_at: null,
      lock: false,
      follow: false,
      range: null,
      range_lesson_id: null,
      reveals: {},
      updated_at: null,
    };
  }

  function parseServerTime(value) {
    if (!value) return NaN;
    return Date.parse(String(value).replace(/(\.\d{3})\d+/, "$1"));
  }

  function trackTeacherPresence(onChange) {
    let clockOffsetMs = 0;
    let windowMs = 150 * 1000;
    let expiryTimer = null;
    let stopped = false;

    function deliver(session) {
      if (expiryTimer) window.clearTimeout(expiryTimer);
      expiryTimer = null;
      if (stopped) return;
      if (!session) {
        onChange(session);
        return;
      }
      let result = session;
      if (typeof session.teacher_active === "boolean") {
        const serverNow = parseServerTime(session.server_time);
        if (Number.isFinite(serverNow)) clockOffsetMs = serverNow - Date.now();
        if (session.teacher_active_window_seconds) windowMs = session.teacher_active_window_seconds * 1000;
      } else {
        const lastSignal = parseServerTime(session.teacher_active_at);
        result = {
          ...session,
          teacher_active: Number.isFinite(lastSignal) && Date.now() + clockOffsetMs - lastSignal <= windowMs,
        };
      }
      if (result.teacher_active) {
        const lastSignal = parseServerTime(result.teacher_active_at);
        if (Number.isFinite(lastSignal)) {
          const remaining = lastSignal + windowMs - (Date.now() + clockOffsetMs);
          const { teacher_active: _drop, ...raw } = session;
          expiryTimer = window.setTimeout(() => deliver(raw), Math.max(remaining, 0) + 1000);
        }
      }
      onChange(result);
    }

    deliver.stop = () => {
      stopped = true;
      if (expiryTimer) window.clearTimeout(expiryTimer);
    };
    return deliver;
  }

  function watchSession(classId, onSessionChange) {
    const onChange = trackTeacherPresence(onSessionChange);
    const restFetch = () =>
      window.StatApi.request(`/api/lessons/sessions/${encodeURIComponent(classId)}`);

    let stopped = false;
    let stopPolling = null;
    let unsubscribeFirestore = null;

    function fallbackToPolling(reason) {
      if (stopped || stopPolling) return;
      console.warn("[lessons] 세션 실시간 연결 실패, 폴링으로 전환합니다.", reason);
      stopPolling = startPolling(restFetch, onChange);
    }

    if (isFirebaseMode() && window.StatAuth?.watchFirestoreDoc) {
      restFetch()
        .then((data) => {
          if (!stopped) onChange(data);
        })
        .catch(() => {});

      window.StatAuth
        .watchFirestoreDoc(
          CLASS_SESSIONS_COLLECTION,
          classId,
          (data) => {
            if (!stopped) onChange(data || emptySession(classId));
          },
          (error) => fallbackToPolling(error),
        )
        .then((unsub) => {
          if (stopped) {
            unsub();
            return;
          }
          unsubscribeFirestore = unsub;
        });
    } else {
      stopPolling = startPolling(restFetch, onChange);
    }

    return () => {
      stopped = true;
      onChange.stop();
      if (stopPolling) stopPolling();
      if (unsubscribeFirestore) unsubscribeFirestore();
    };
  }

  function watchDiscuss(lessonId, promptId, onChange, classId) {
    const classQuery = classId ? `?class_id=${encodeURIComponent(classId)}` : "";
    const restFetch = () =>
      window.StatApi.request(
        `/api/lessons/discuss/${encodeURIComponent(lessonId)}/prompts/${encodeURIComponent(promptId)}/responses${classQuery}`,
      );

    let stopped = false;
    let stopPolling = null;
    let unsubscribeFirestore = null;

    function fallbackToPolling(reason) {
      if (stopped || stopPolling) return;
      console.warn("[lessons] 응답 보드 실시간 연결 실패, 폴링으로 전환합니다.", reason);
      stopPolling = startPolling(restFetch, onChange);
    }

    if (isFirebaseMode() && window.StatAuth?.watchFirestoreQuery) {
      restFetch()
        .then((data) => {
          if (!stopped) onChange(data);
        })
        .catch(() => {});

      const conditions = [
        ["lesson_id", "==", lessonId],
        ["prompt_id", "==", promptId],
      ];
      if (classId) conditions.push(["class_id", "==", classId]);
      window.StatAuth
        .watchFirestoreQuery(
          DISCUSS_RESPONSES_COLLECTION,
          conditions,
          (docs) => {
            if (!stopped) onChange(docs);
          },
          (error) => fallbackToPolling(error),
        )
        .then((unsub) => {
          if (stopped) {
            unsub();
            return;
          }
          unsubscribeFirestore = unsub;
        });
    } else {
      stopPolling = startPolling(restFetch, onChange);
    }

    return () => {
      stopped = true;
      if (stopPolling) stopPolling();
      if (unsubscribeFirestore) unsubscribeFirestore();
    };
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.watchSession = watchSession;
  window.LessonKit.watchDiscuss = watchDiscuss;
})();
