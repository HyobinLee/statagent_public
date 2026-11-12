import csv
import io
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError, success_response
from app.core.time import now_utc
from app.dependencies import require_any_role
from app.models.user import User
from app.repositories.factory import get_repository
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import discuss_store, progress, tracks
from lessons_app.services.lesson_defs import RESUBMIT_SUFFIX, get_lesson_def_for_track, iter_lesson_defs

router = APIRouter(prefix="/api/lessons/teacher", tags=["lesson-teacher"])

LESSON_IDS = progress.LESSON_IDS


def _iter_prompts(definition: dict):
    for step in definition.get("steps") or []:
        for card in step.get("cards") or [step]:
            yield from card.get("prompts") or []


def _exit_prompt_ids(lesson_id: str, track: str) -> list[str]:
    try:
        definition = get_lesson_def_for_track(lesson_id, track)
    except Exception:
        return []
    return [
        prompt["prompt_id"]
        for prompt in _iter_prompts(definition)
        if prompt.get("type") == "exit" and prompt.get("prompt_id")
    ]


def _prompt_type_map(lesson_id: str) -> dict[str, str]:
    types: dict[str, str] = {}
    try:
        variants = list(iter_lesson_defs(lesson_id))
    except Exception:
        return types
    for definition in variants:
        for prompt in _iter_prompts(definition):
            prompt_id = prompt.get("prompt_id")
            if not prompt_id:
                continue
            prompt_type = prompt.get("type") or ""
            if prompt_type or prompt_id not in types:
                types[prompt_id] = prompt_type
                types[f"{prompt_id}{RESUBMIT_SUFFIX}"] = f"{prompt_type or 'free'}_resubmit"
    return types


def _my_students(user: User) -> list[User]:
    students = [student for student in get_repository().list_users() if student.role == "student"]
    if user.role == "teacher":
        students = [student for student in students if student.teacher_id == user.user_id]
    return students


def _assert_can_manage(user: User, student_id: str) -> User:
    student = get_repository().get_user(student_id)
    if not student or student.role != "student":
        raise AppError(
            "STUDENT_NOT_FOUND",
            "학생을 찾을 수 없습니다.",
            "명단을 새로고침해 주세요.",
            404,
        )
    if user.role != "admin" and student.teacher_id != user.user_id:
        raise AppError(
            "STUDENT_NOT_MINE",
            "담당 학급 학생이 아닙니다.",
            "담당 학급인지 확인해 주세요.",
            403,
        )
    return student


@router.get("/progress")
def teacher_progress(user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    settings_by_key = {setting.get("key"): setting for setting in get_repository().list_settings()}

    rows = []
    for student in _my_students(user):
        detail = progress.summarize(student.user_id, settings_by_key)
        student_track, _scenario = tracks.resolve(student)
        for lesson_id in LESSON_IDS:
            detail[lesson_id]["exit_submitted"] = any(
                discuss_store.get_response(discuss_store.response_id(lesson_id, prompt_id, student.user_id))
                for prompt_id in _exit_prompt_ids(lesson_id, student_track)
            )
        rows.append(
            {
                "user_id": student.user_id,
                "display_name": student.display_name,
                "class_id": student.class_id,
                "progress": {lesson_id: detail[lesson_id]["started"] for lesson_id in LESSON_IDS},
                "detail": detail,
            }
        )
    rows.sort(key=lambda row: (row["class_id"] or "", row["display_name"]))
    return success_response({"lessons": list(LESSON_IDS), "students": rows})


def _flatten_cards(definition: dict) -> list[dict]:
    cards = []
    for step_index, step in enumerate(definition.get("steps") or []):
        step_cards = step.get("cards") or [step]
        for card_index, card in enumerate(step_cards):
            prompts = [prompt.get("prompt_id") for prompt in card.get("prompts") or [] if prompt.get("prompt_id")]
            resubmit_prompts = [
                prompt.get("prompt_id")
                for prompt in card.get("prompts") or []
                if prompt.get("prompt_id") and prompt.get("requires_resubmit")
            ]
            cards.append(
                {
                    "index": len(cards),
                    "step": step_index,
                    "card": card_index,
                    "step_title": step.get("title") or "",
                    "title": card.get("title") or card.get("id") or "",
                    "kind": card.get("kind") or "",
                    "prompt_ids": prompts,
                    "resubmit_ids": resubmit_prompts,
                }
            )
    return cards


@router.get("/card-progress")
def card_progress(
    lesson_id: str,
    class_id: str = "",
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    if lesson_id not in LESSON_IDS:
        raise AppError(
            "LESSON_NOT_FOUND",
            f"그런 차시가 없습니다: {lesson_id}",
            "차시 번호를 확인해 주세요.",
            404,
        )

    from_class = tracks.class_track_scenario(class_id) if class_id else None
    if from_class:
        effective_track, effective_scenario = from_class
    else:
        effective_track = tracks.normalize_track(track)
        effective_scenario = tracks.normalize_scenario(scenario)

    definition = get_lesson_def_for_track(lesson_id, effective_track, effective_scenario)
    cards = _flatten_cards(definition)

    students = _my_students(user)
    if class_id:
        students = [student for student in students if student.class_id == class_id]
    students.sort(key=lambda student: student.display_name)

    teacher_filter = user.user_id if user.role == "teacher" else None
    answered_by_user: dict[str, set[str]] = {}
    resubmitted_by_user: dict[str, set[str]] = {}
    for response in discuss_store.list_for_lesson(lesson_id, teacher_id=teacher_filter, class_id=class_id or None):
        prompt_id = response.get("prompt_id") or ""
        user_key = response.get("user_id") or ""
        if prompt_id.endswith(RESUBMIT_SUFFIX):
            original_id = prompt_id[: -len(RESUBMIT_SUFFIX)]
            resubmitted_by_user.setdefault(user_key, set()).add(original_id)
            continue
        answered_by_user.setdefault(user_key, set()).add(prompt_id)

    rows = []
    for student in students:
        position = progress.get_position(student.user_id, effective_track, effective_scenario, lesson_id)
        visited = set(position.get("visited") or []) if position else set()
        here = progress.card_marker(position["step"], position["card"]) if position else ""
        answered_prompts = answered_by_user.get(student.user_id, set())
        resubmitted_prompts = resubmitted_by_user.get(student.user_id, set())

        cells = []
        for card in cards:
            marker = progress.card_marker(card["step"], card["card"])
            answered = [pid for pid in card["prompt_ids"] if pid in answered_prompts]
            seen = marker in visited or bool(answered)
            if card["prompt_ids"] and answered:
                state = "answered" if len(answered) == len(card["prompt_ids"]) else "partial"
            elif seen:
                state = "seen"
            else:
                state = "none"
            resubmitted = [pid for pid in card["resubmit_ids"] if pid in resubmitted_prompts]
            cells.append(
                {
                    "state": state,
                    "current": marker == here,
                    "answered": len(answered),
                    "prompts": len(card["prompt_ids"]),
                    "resubmitted": len(resubmitted),
                    "resubmits": len(card["resubmit_ids"]),
                }
            )

        rows.append(
            {
                "user_id": student.user_id,
                "display_name": student.display_name,
                "class_id": student.class_id,
                "position_index": next(
                    (card["index"] for card in cards if progress.card_marker(card["step"], card["card"]) == here),
                    None,
                ),
                "started": bool(position),
                "updated_at": (position or {}).get("updated_at", ""),
                "cells": cells,
            }
        )

    for index, card in enumerate(cards):
        card["seen_count"] = sum(1 for row in rows if row["cells"][index]["state"] != "none")
        card["answered_count"] = sum(1 for row in rows if row["cells"][index]["state"] == "answered")
        card["resubmit_count"] = sum(
            1
            for row in rows
            if card["resubmit_ids"] and row["cells"][index]["resubmitted"] == len(card["resubmit_ids"])
        )

    return success_response(
        {
            "lesson_id": lesson_id,
            "class_id": class_id,
            "track": effective_track,
            "scenario": effective_scenario,
            "title": definition.get("title", ""),
            "cards": cards,
            "students": rows,
            "generated_at": now_utc().isoformat(),
        }
    )


@router.get("/card-responses")
def card_responses(
    lesson_id: str,
    user_id: str,
    step: int,
    card: int,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    if lesson_id not in LESSON_IDS:
        raise AppError(
            "LESSON_NOT_FOUND",
            f"그런 차시가 없습니다: {lesson_id}",
            "차시 번호를 확인해 주세요.",
            404,
        )
    student = _assert_can_manage(user, user_id)

    from_class = tracks.class_track_scenario(student.class_id)
    if from_class:
        effective_track, effective_scenario = from_class
    else:
        effective_track = tracks.normalize_track(track)
        effective_scenario = tracks.normalize_scenario(scenario)

    definition = get_lesson_def_for_track(lesson_id, effective_track, effective_scenario)
    target = next(
        (item for item in _flatten_cards(definition) if item["step"] == step and item["card"] == card),
        None,
    )
    if target is None:
        raise AppError(
            "CARD_NOT_FOUND",
            "그런 카드가 없습니다.",
            "진행 현황을 새로고침한 뒤 다시 눌러 주세요.",
            404,
        )

    prompt_by_id = {prompt.get("prompt_id"): prompt for prompt in _iter_prompts(definition) if prompt.get("prompt_id")}

    def _read(prompt_id: str) -> dict | None:
        response = discuss_store.get_response(discuss_store.response_id(lesson_id, prompt_id, user_id))
        if not response:
            return None
        return {
            "text": response.get("text", ""),
            "choice": response.get("choice") or "",
            "after_reveal": bool(response.get("after_reveal")),
            "edited_after_peers": bool(response.get("edited_after_peers")),
            "feedback": response.get("feedback") or "",
            "input_started_at": response.get("input_started_at", ""),
            "created_at": response.get("created_at", ""),
            "updated_at": response.get("updated_at", ""),
        }

    prompts = []
    for prompt_id in target["prompt_ids"]:
        definition_prompt = prompt_by_id.get(prompt_id, {})
        prompts.append(
            {
                "prompt_id": prompt_id,
                "question": definition_prompt.get("question", ""),
                "type": definition_prompt.get("type", ""),
                "observe": definition_prompt.get("observe", ""),
                "answer": definition_prompt.get("answer", ""),
                "response": _read(prompt_id),
                "resubmit": _read(f"{prompt_id}{RESUBMIT_SUFFIX}")
                if definition_prompt.get("requires_resubmit")
                else None,
            }
        )

    return success_response(
        {
            "lesson_id": lesson_id,
            "user_id": user_id,
            "display_name": student.display_name,
            "step": step,
            "card": card,
            "card_title": target["title"],
            "step_title": target["step_title"],
            "prompts": prompts,
        }
    )


KST = timezone(timedelta(hours=9), "KST")


def _kst(stamp: str | None) -> str:
    if not stamp:
        return ""
    try:
        return datetime.fromisoformat(stamp).astimezone(KST).isoformat(timespec="seconds")
    except ValueError:
        return stamp


@router.get("/responses-csv")
def responses_csv(
    lesson_id: str = "",
    class_id: str = "",
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    lesson_ids = [lesson_id] if lesson_id else list(LESSON_IDS)
    unknown = [item for item in lesson_ids if item not in LESSON_IDS]
    if unknown:
        raise AppError(
            "LESSON_NOT_FOUND",
            f"그런 차시가 없습니다: {', '.join(unknown)}",
            "차시 번호를 확인해 주세요.",
            404,
        )

    teacher_filter = user.user_id if user.role == "teacher" else None
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "lesson_id",
            "prompt_id",
            "prompt_type",
            "class_id",
            "user_id",
            "display_name",
            "choice",
            "text",
            "feedback",
            "input_started_at",
            "created_at",
            "updated_at",
            "after_reveal",
            "edited_after_peers",
        ]
    )
    count = 0
    for current_lesson in lesson_ids:
        type_map = _prompt_type_map(current_lesson)
        responses = discuss_store.list_for_lesson(current_lesson, teacher_id=teacher_filter, class_id=class_id or None)
        responses.sort(
            key=lambda response: (
                response.get("class_id") or "",
                response.get("display_name") or "",
                response.get("prompt_id") or "",
            )
        )
        for response in responses:
            writer.writerow(
                [
                    current_lesson,
                    response.get("prompt_id", ""),
                    type_map.get(response.get("prompt_id", ""), ""),
                    response.get("class_id") or "",
                    response.get("user_id", ""),
                    response.get("display_name", ""),
                    response.get("choice") or "",
                    response.get("text", ""),
                    response.get("feedback") or "",
                    _kst(response.get("input_started_at")),
                    _kst(response.get("created_at")),
                    _kst(response.get("updated_at")),
                    "1" if response.get("after_reveal") else "",
                    "1" if response.get("edited_after_peers") else "",
                ]
            )
            count += 1

    scope = lesson_id or "all"
    suffix = f"_{class_id}" if class_id else ""
    return success_response(
        {
            "filename": f"responses_{scope}{suffix}.csv",
            "csv": buffer.getvalue(),
            "count": count,
        }
    )


class ResetRequest(BaseModel):
    lesson_id: str = Field(default="", max_length=40)


@router.post("/students/{student_id}/reset")
def reset_student_progress(
    student_id: str,
    payload: ResetRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    student = _assert_can_manage(user, student_id)

    lesson_ids = [payload.lesson_id] if payload.lesson_id else list(LESSON_IDS)
    unknown = [lesson_id for lesson_id in lesson_ids if lesson_id not in LESSON_IDS]
    if unknown:
        raise AppError(
            "LESSON_NOT_FOUND",
            f"그런 차시가 없습니다: {', '.join(unknown)}",
            "차시 번호를 확인해 주세요.",
            404,
        )

    results = [progress.reset_lesson(student_id, lesson_id) for lesson_id in lesson_ids]
    return success_response(
        {
            "user_id": student_id,
            "display_name": student.display_name,
            "lessons": results,
            "detail": progress.summarize(student_id),
        }
    )
