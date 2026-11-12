from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import inquiry

router = APIRouter(prefix="/api/lessons/inquiry", tags=["lesson-inquiry"])


@router.get("/{project_id}")
def get_inquiry(
    project_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    return success_response(inquiry.inquiry_summary(user, project_id))


class LinkDatasetRequest(BaseModel):
    dataset_id: str


@router.put("/{project_id}/dataset")
def link_dataset(
    project_id: str,
    payload: LinkDatasetRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    project = inquiry.link_dataset(user, project_id, payload.dataset_id)
    return success_response(project.model_dump(mode="json"))


class SavePresentationRequest(BaseModel):
    selected: list[str] | None = None
    conclusion: str = Field(default="", max_length=inquiry.CONCLUSION_MAX_LENGTH)
    limitations: str = Field(default="", max_length=inquiry.CONCLUSION_MAX_LENGTH)


@router.put("/{project_id}/presentation")
def save_presentation(
    project_id: str,
    payload: SavePresentationRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    saved = inquiry.save_presentation(
        user,
        project_id,
        payload.selected,
        payload.conclusion,
        payload.limitations,
    )
    return success_response(saved)
