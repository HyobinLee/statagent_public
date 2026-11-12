from app.core.errors import success_response
from app.core.time import now_utc
from app.dependencies import require_any_role, require_role
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.workflow_service import WorkflowService
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from lessons_app.services import career_fields, inquiry, tracks

router = APIRouter(prefix="/api/lessons/careers", tags=["lesson-careers"])


def _career_key(user_id: str) -> str:
    return inquiry.career_key(user_id)


@router.get("/fields")
def list_fields(track: str = "", user: User = Depends(require_role("student"))) -> dict:
    effective_track, _scenario = tracks.resolve(user, track)
    return success_response(career_fields.list_fields(effective_track))


class SaveCareerRequest(BaseModel):
    field_id: str
    topic_id: str
    project_id: str | None = None


@router.get("/me")
def get_my_career(user: User = Depends(require_role("student"))) -> dict:
    setting = get_repository().get_setting(_career_key(user.user_id))
    return success_response(setting.get("value") if setting else None)


@router.post("/me")
def save_my_career(
    payload: SaveCareerRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, _scenario = tracks.resolve(user)
    field = career_fields.get_field(payload.field_id, effective_track)
    topic = career_fields.get_topic(payload.field_id, payload.topic_id, effective_track)
    project = WorkflowService().get_project(payload.project_id, user) if payload.project_id else None
    value = {
        "field_id": field["field_id"],
        "field_name": field["field_name"],
        "topic_id": topic["topic_id"],
        "question": topic["question"],
        "saved_at": now_utc().isoformat(),
    }
    get_repository().upsert_setting(_career_key(user.user_id), value)
    if project:
        project = inquiry.apply_question(project, value["question"])
        value = {**value, "project_question": project.custom_topic_question}
    return success_response(value)


@router.delete("/me")
def delete_my_career(user: User = Depends(require_role("student"))) -> dict:
    get_repository().upsert_setting(_career_key(user.user_id), None)
    return success_response({"deleted": True})


@router.delete("/{user_id}")
def delete_career_for_user(
    user_id: str,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    get_repository().upsert_setting(_career_key(user_id), None)
    return success_response({"deleted": True, "user_id": user_id})
