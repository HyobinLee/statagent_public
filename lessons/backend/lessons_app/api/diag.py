from datetime import datetime

from app.core.errors import AppError, success_response
from app.core.time import now_utc
from app.dependencies import require_any_role, require_role
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import lesson_store, progress, student_accounts, tracks
from lessons_app.services.lesson_defs import get_lesson_def_for_track

router = APIRouter(prefix="/api/lessons", tags=["lesson-diag"])

DIAG_COLLECTION = progress.DIAG_COLLECTION


class DiagResponseRequest(BaseModel):
    choice: str = Field(..., min_length=1, max_length=8)
    reason_choice: str = Field(default="", max_length=8)
    reason_text: str = Field(default="", max_length=2000)
    confidence: int = Field(..., ge=1, le=4)


def _find_diag_item(lesson_def: dict, item_id: str) -> dict | None:
    for step in lesson_def.get("steps", []):
        for card in step.get("cards") or [step]:
            item = card.get("item")
            if card.get("kind") == "diag" and item and item.get("item_id") == item_id:
                return item
    return None


def _doc_id(user_id: str, track: str, scenario: str, item_id: str) -> str:
    return f"{user_id}:{track}:{scenario}:{item_id}"


@router.post("/diag/{lesson_id}/items/{item_id}/response")
def save_diag_response(
    lesson_id: str,
    item_id: str,
    payload: DiagResponseRequest,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, effective_scenario = tracks.resolve(user, track, scenario)
    lesson_def = get_lesson_def_for_track(lesson_id, effective_track, effective_scenario)
    item = _find_diag_item(lesson_def, item_id)
    if not item:
        raise AppError(
            "DIAG_ITEM_NOT_FOUND",
            "이 차시에 그런 진단 문항이 없습니다.",
            "화면을 새로고침한 뒤 다시 시도해 주세요.",
            404,
        )
    valid_choices = {choice["key"] for choice in item.get("choices") or []}
    if payload.choice not in valid_choices:
        raise AppError(
            "DIAG_CHOICE_INVALID",
            "선택지 값이 올바르지 않습니다.",
            "보기 중 하나를 골라 주세요.",
            400,
        )
    if not payload.reason_choice and not payload.reason_text.strip():
        raise AppError(
            "DIAG_REASON_REQUIRED",
            "이유를 고르거나 직접 적어 주세요.",
            "이유 없이 저장하면 채점(2단)이 되지 않습니다.",
            400,
        )

    record = {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "class_id": user.class_id or "",
        "track": effective_track,
        "scenario": effective_scenario,
        "lesson_id": lesson_id,
        "phase": item.get("phase", ""),
        "item_id": item_id,
        "choice": payload.choice,
        "correct": payload.choice == item.get("answer"),
        "reason_choice": payload.reason_choice,
        "reason_correct": (
            payload.reason_choice == item.get("reason_answer")
            if payload.reason_choice and item.get("reason_answer")
            else None
        ),
        "reason_text": payload.reason_text.strip(),
        "confidence": payload.confidence,
        "updated_at": now_utc().isoformat(),
    }
    doc_id = _doc_id(user.user_id, effective_track, effective_scenario, item_id)
    existing = lesson_store.get_doc(DIAG_COLLECTION, doc_id)
    record["created_at"] = (existing or {}).get("created_at") or record["updated_at"]
    lesson_store.set_doc(DIAG_COLLECTION, doc_id, record)
    return success_response({"item_id": item_id, "saved": True})


@router.get("/diag/{lesson_id}/items/{item_id}/response")
def get_my_diag_response(
    lesson_id: str,
    item_id: str,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, effective_scenario = tracks.resolve(user, track, scenario)
    record = lesson_store.get_doc(DIAG_COLLECTION, _doc_id(user.user_id, effective_track, effective_scenario, item_id))
    if not record:
        return success_response(None)
    return success_response(
        {
            "choice": record.get("choice", ""),
            "reason_choice": record.get("reason_choice", ""),
            "reason_text": record.get("reason_text", ""),
            "confidence": record.get("confidence"),
        }
    )


@router.get("/teacher/diag-export")
def export_diag_responses(
    class_id: str = "",
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    import csv
    import io

    records = lesson_store.list_docs(DIAG_COLLECTION)
    if user.role != "admin":
        my_student_ids = {
            student.user_id
            for record in lesson_store.list_docs(student_accounts.CLASS_CODES)
            if record.get("teacher_id") == user.user_id
            for student in student_accounts.list_class_students(record["class_id"])
        }
        records = [record for record in records if record.get("user_id") in my_student_ids]
    if class_id:
        records = [record for record in records if record.get("class_id") == class_id]

    def _sort_key(record: dict):
        return (
            record.get("class_id", ""),
            record.get("display_name", ""),
            record.get("phase", ""),
            record.get("item_id", ""),
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "class_id",
            "user_id",
            "display_name",
            "track",
            "scenario",
            "phase",
            "item_id",
            "choice",
            "correct",
            "reason_choice",
            "reason_correct",
            "reason_text",
            "confidence",
            "created_at",
            "updated_at",
        ]
    )
    for record in sorted(records, key=_sort_key):
        writer.writerow(
            [
                record.get("class_id", ""),
                record.get("user_id", ""),
                record.get("display_name", ""),
                record.get("track", ""),
                record.get("scenario", ""),
                record.get("phase", ""),
                record.get("item_id", ""),
                record.get("choice", ""),
                record.get("correct", ""),
                record.get("reason_choice", ""),
                record.get("reason_correct", ""),
                record.get("reason_text", ""),
                record.get("confidence", ""),
                record.get("created_at", ""),
                record.get("updated_at", ""),
            ]
        )
    suffix = f"_{class_id}" if class_id else ""
    stamp = datetime.now().strftime("%y%m%d")
    return success_response(
        {"filename": f"diag_responses{suffix}_{stamp}.csv", "csv": buffer.getvalue(), "count": len(records)}
    )
