from datetime import UTC, datetime

from app.core.time import now_utc

from lessons_app.services import lesson_store

COLLECTION = "classSessions"


def _default_session(class_id: str) -> dict:
    return {
        "class_id": class_id,
        "teacher_id": None,
        "lesson_id": None,
        "level": None,
        "focus": {"step": 0, "card": 0},
        "focus_lesson_id": None,
        "pushed_at": None,
        "lock": False,
        "teacher_active_at": None,
        "follow": False,
        "range": None,
        "range_lesson_id": None,
        "reveals": {},
        "updated_at": None,
    }


def read_session(class_id: str) -> dict:
    doc = lesson_store.get_doc(COLLECTION, class_id)
    return doc if doc is not None else _default_session(class_id)


def push_focus(class_id: str, teacher_id: str, lesson_id: str, level: str | None, step: int, card: int) -> dict:
    session = read_session(class_id)
    session.update(
        {
            "class_id": class_id,
            "teacher_id": teacher_id,
            "lesson_id": lesson_id,
            "level": level,
            "focus": {"step": step, "card": card},
            "focus_lesson_id": lesson_id,
            "pushed_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }
    )
    return lesson_store.set_doc(COLLECTION, class_id, session)


def set_lock(class_id: str, teacher_id: str, lock: bool) -> dict:
    session = read_session(class_id)
    session.update({"class_id": class_id, "teacher_id": teacher_id, "lock": lock, "updated_at": now_utc().isoformat()})
    return lesson_store.set_doc(COLLECTION, class_id, session)


TEACHER_ACTIVE_WINDOW_SECONDS = 150


def mark_teacher_open(class_id: str, teacher_id: str, lesson_id: str, level: str | None = None) -> dict:
    session = read_session(class_id)
    session.update(
        {
            "class_id": class_id,
            "teacher_id": teacher_id,
            "lesson_id": lesson_id,
            "level": level if level is not None else session.get("level"),
            "teacher_active_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }
    )
    return lesson_store.set_doc(COLLECTION, class_id, session)


def teacher_active(session: dict) -> bool:
    stamp = (session or {}).get("teacher_active_at")
    if not stamp:
        return False
    try:
        last = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return (now_utc() - last).total_seconds() <= TEACHER_ACTIVE_WINDOW_SECONDS


def set_follow(class_id: str, teacher_id: str, follow: bool) -> dict:
    session = read_session(class_id)
    update = {"class_id": class_id, "teacher_id": teacher_id, "follow": follow, "updated_at": now_utc().isoformat()}
    if follow:
        update.update({"range": None, "range_lesson_id": None})
    session.update(update)
    return lesson_store.set_doc(COLLECTION, class_id, session)


def normalize_range(cards: list[dict] | None) -> list[dict] | None:
    if not cards:
        return None
    seen = {(int(card["step"]), int(card["card"])) for card in cards}
    return [{"step": step, "card": card} for step, card in sorted(seen)]


def set_range(class_id: str, teacher_id: str, cards: list[dict] | None, lesson_id: str | None = None) -> dict:
    session = read_session(class_id)
    normalized = normalize_range(cards)
    update = {
        "class_id": class_id,
        "teacher_id": teacher_id,
        "range": normalized,
        "range_lesson_id": lesson_id if normalized else None,
        "updated_at": now_utc().isoformat(),
    }
    if normalized:
        update["follow"] = False
    session.update(update)
    return lesson_store.set_doc(COLLECTION, class_id, session)


def set_reveal(class_id: str, teacher_id: str, key: str, value: bool) -> dict:
    session = read_session(class_id)
    reveals = dict(session.get("reveals") or {})
    reveals[key] = value
    session.update(
        {
            "class_id": class_id,
            "teacher_id": teacher_id,
            "reveals": reveals,
            "updated_at": now_utc().isoformat(),
        }
    )
    return lesson_store.set_doc(COLLECTION, class_id, session)


def clear_reveals(class_id: str, teacher_id: str, keys: list[str] | None = None) -> dict:
    session = read_session(class_id)
    reveals = dict(session.get("reveals") or {})
    if keys:
        for key in keys:
            reveals.pop(key, None)
    else:
        reveals = {}
    session.update(
        {
            "class_id": class_id,
            "teacher_id": teacher_id,
            "reveals": reveals,
            "updated_at": now_utc().isoformat(),
        }
    )
    return lesson_store.set_doc(COLLECTION, class_id, session)
