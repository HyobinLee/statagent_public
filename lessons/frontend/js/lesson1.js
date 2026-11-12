(async function () {
  const deckHost = document.getElementById("deck") || document.getElementById("steps");

  try {
    await StatAuth.init();
  } catch (error) {
    LessonKit.handleLessonAccessError(deckHost, error);
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const track = params.get("track") || "";

  let lesson;
  try {
    lesson = await StatApi.request(`/api/lessons/lesson1?track=${encodeURIComponent(track)}`);
  } catch (error) {
    LessonKit.handleLessonAccessError(deckHost, error);
    return;
  }

  LessonKit.clearAccessRedirectGuard();
  if (LessonKit.syncResetMarker(lesson.lesson_id, lesson.reset_at)) {
    LessonKit.showError("선생님이 이 차시를 처음부터 다시 하도록 되돌렸습니다.");
  }
  document.getElementById("lesson-title").textContent = `1차시 · ${lesson.definition.title}`;
  document.getElementById("lesson-topic").textContent = lesson.definition.topic_sentence;

  const profile = StatAuth.getProfile?.();

  const context = {
    lessonId: lesson.lesson_id,
    projectId: lesson.project_id,
    datasetId: lesson.dataset_id,
    track: lesson.track,
    scenario: lesson.scenario || "",
    classId: profile?.class_id || null,
    serverPosition: lesson.progress || null,
    role: StatAuth.getEffectiveRole?.() || "student",
    renderers: { ...LessonKit.RENDERERS },
  };

  await LessonKit.renderDeck(document.getElementById("deck"), lesson.definition, context);
})();
