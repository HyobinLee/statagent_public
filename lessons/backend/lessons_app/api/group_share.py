from app.core.errors import success_response
from app.dependencies import require_role
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from lessons_app.services import group_share

router = APIRouter(prefix="/api/lessons/group", tags=["lesson-group"])


@router.get("/datasets")
def list_group_datasets(user: User = Depends(require_role("student"))) -> dict:
    datasets = group_share.list_group_datasets(user)
    return success_response(datasets, {"count": len(datasets)})


class CopyDatasetRequest(BaseModel):
    dataset_id: str
    topic_id: str


@router.post("/copy-dataset")
def copy_group_dataset(
    payload: CopyDatasetRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = group_share.copy_group_dataset(
        source_dataset_id=payload.dataset_id,
        topic_id=payload.topic_id,
        owner_user_id=user.user_id,
    )
    return success_response(result)
