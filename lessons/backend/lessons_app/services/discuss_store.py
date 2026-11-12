from datetime import timedelta

from app.core.time import now_utc

from lessons_app.services import lesson_store

COLLECTION = "discussResponses"

DEFAULT_BOARD = {"x": 0.0, "y": 0.0, "highlighted": False, "hidden": False, "placed": False}


def response_id(lesson_id: str, prompt_id: str, user_id: str) -> str:
    return f"{lesson_id}:{prompt_id}:{user_id}"


def upsert_response(
    *,
    lesson_id: str,
    prompt_id: str,
    class_id: str | None,
    teacher_id: str | None,
    user_id: str,
    display_name: str,
    text: str,
    choice: str = "",
    after_reveal: bool = False,
    input_ms: int | None = None,
) -> dict:
    rid = response_id(lesson_id, prompt_id, user_id)
    existing = lesson_store.get_doc(COLLECTION, rid)
    now_dt = now_utc()
    now = now_dt.isoformat()
    if existing:
        input_started_at = existing.get("input_started_at") or ""
    elif input_ms is not None:
        input_started_at = (now_dt - timedelta(milliseconds=input_ms)).isoformat()
    else:
        input_started_at = ""
    changed = bool(existing) and (existing.get("text") != text or (existing.get("choice") or "") != choice)
    edited_after_peers = bool(
        (existing or {}).get("edited_after_peers") or (changed and (existing or {}).get("peers_viewed_at"))
    )
    payload = {
        "response_id": rid,
        "lesson_id": lesson_id,
        "prompt_id": prompt_id,
        "class_id": class_id,
        "teacher_id": teacher_id,
        "user_id": user_id,
        "display_name": display_name,
        "text": text,
        "choice": choice,
        "after_reveal": bool(after_reveal or (existing or {}).get("after_reveal")),
        "edited_after_peers": edited_after_peers,
        "input_started_at": input_started_at,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
        "board": existing["board"] if existing else dict(DEFAULT_BOARD),
    }
    if existing:
        for key in ("feedback", "feedback_at", "feedback_by", "peers_viewed_at"):
            if existing.get(key):
                payload[key] = existing[key]
    return lesson_store.set_doc(COLLECTION, rid, payload)


def set_feedback(rid: str, text: str, teacher_user_id: str) -> dict | None:
    existing = get_response(rid)
    if existing is None:
        return None
    patch = {
        "feedback": text,
        "feedback_at": now_utc().isoformat() if text else "",
        "feedback_by": teacher_user_id if text else "",
    }
    return lesson_store.update_doc(COLLECTION, rid, patch)


def mark_peers_viewed(rid: str) -> None:
    existing = get_response(rid)
    if existing is None or existing.get("peers_viewed_at"):
        return
    lesson_store.update_doc(COLLECTION, rid, {"peers_viewed_at": now_utc().isoformat()})


def get_response(rid: str) -> dict | None:
    return lesson_store.get_doc(COLLECTION, rid)


def list_for_prompt(
    lesson_id: str,
    prompt_id: str,
    teacher_id: str | None = None,
    class_id: str | None = None,
) -> list[dict]:
    filters: dict[str, object] = {"lesson_id": lesson_id, "prompt_id": prompt_id}
    if teacher_id is not None:
        filters["teacher_id"] = teacher_id
    if class_id is not None:
        filters["class_id"] = class_id
    return lesson_store.list_docs(COLLECTION, **filters)


def list_for_lesson(
    lesson_id: str,
    teacher_id: str | None = None,
    class_id: str | None = None,
) -> list[dict]:
    filters: dict[str, object] = {"lesson_id": lesson_id}
    if teacher_id is not None:
        filters["teacher_id"] = teacher_id
    if class_id is not None:
        filters["class_id"] = class_id
    return lesson_store.list_docs(COLLECTION, **filters)


def patch_board(rid: str, patch: dict) -> dict | None:
    existing = get_response(rid)
    if existing is None:
        return None
    board = dict(existing.get("board") or DEFAULT_BOARD)
    board.update(patch)
    return lesson_store.update_doc(COLLECTION, rid, {"board": board})


def delete_response(rid: str) -> None:
    lesson_store.delete_doc(COLLECTION, rid)
