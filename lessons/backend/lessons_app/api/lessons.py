from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import inquiry, progress, tracks
from lessons_app.services.lesson_defs import (
    get_lesson_def_for_track,
    list_lessons_for_track,
    strip_teacher_only,
)
from lessons_app.services.provisioning import ensure_lesson_project, record_lesson_visit

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


class PositionRequest(BaseModel):
    step: int = Field(ge=0, le=500)
    card: int = Field(ge=0, le=500)


@router.put("/{lesson_id}/position")
def save_position(
    lesson_id: str,
    payload: PositionRequest,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, scenario = tracks.resolve(user, track, scenario)
    get_lesson_def_for_track(lesson_id, effective_track, scenario)
    saved = progress.save_position(user.user_id, effective_track, scenario, lesson_id, payload.step, payload.card)
    return success_response(saved)


@router.get("/definitions/{lesson_id}")
def get_lesson_definition(
    lesson_id: str,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    effective_track = tracks.normalize_track(track)
    effective_scenario = tracks.normalize_scenario(scenario)
    return success_response(
        {
            "lesson_id": lesson_id,
            "track": effective_track,
            "scenario": effective_scenario,
            "level": tracks.track_level(effective_track),
            "definition": get_lesson_def_for_track(lesson_id, effective_track, effective_scenario),
        }
    )


@router.get("/catalog")
def get_catalog(
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    effective_track, effective_scenario = tracks.resolve(user, track, scenario)
    return success_response(
        {
            "track": effective_track,
            "scenario": effective_scenario,
            "scenario_label": tracks.SCENARIO_LABELS.get(effective_scenario, effective_scenario),
            "track_label": tracks.TRACK_LABELS.get(effective_track, effective_track),
            "lessons": list_lessons_for_track(effective_track, effective_scenario),
        }
    )


@router.get("/{lesson_id}")
def get_lesson(
    lesson_id: str,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, scenario = tracks.resolve(user, track, scenario)
    level = tracks.track_level(effective_track)
    lesson_def = get_lesson_def_for_track(lesson_id, effective_track, scenario)
    project_lesson_id = lesson_def.get("project_lesson_id", lesson_id)
    provisioning_def = (
        lesson_def
        if project_lesson_id == lesson_id
        else get_lesson_def_for_track(project_lesson_id, effective_track, scenario)
    )
    project = ensure_lesson_project(user, project_lesson_id, provisioning_def, effective_track, scenario)
    if project_lesson_id == inquiry.INQUIRY_LESSON_ID:
        project = inquiry.sync_career_question(user, project)
    if project_lesson_id != lesson_id:
        record_lesson_visit(user, lesson_id, project, effective_track, scenario)
    return success_response(
        {
            "lesson_id": lesson_id,
            "track": effective_track,
            "scenario": scenario,
            "level": level,
            "definition": strip_teacher_only(lesson_def),
            "project_id": project.project_id,
            "topic_id": project.topic_id,
            "dataset_id": project.dataset_id,
            "reset_at": progress.reset_marker(user.user_id, lesson_id),
            "progress": progress.get_position(user.user_id, effective_track, scenario, lesson_id),
        }
    )
