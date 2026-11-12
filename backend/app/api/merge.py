from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import require_role
from app.models.user import User
from app.services.merge_service import MergeService

router = APIRouter(prefix="/api/merge", tags=["merge"])


class MergePreviewRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=5)
    key_column_mappings: dict[str, str]
    time_column_mappings: dict[str, str] = Field(default_factory=dict)


class HarmonizeRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    key_column: str = Field(..., min_length=1)
    rename_map: dict[str, str]


class AiHarmonizeRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=5)
    key_column_mappings: dict[str, str]


class TimePointsRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=1, max_length=5)
    time_column_mappings: dict[str, str]


class MergeExecuteRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=5)
    key_column_mappings: dict[str, str]
    join_type: str = Field(default="inner", pattern="^(inner|outer)$")
    time_column_mappings: dict[str, str] = Field(default_factory=dict)
    selected_time_points: list[str] = Field(default_factory=list)
    topic_id: str = Field(..., min_length=1)
    dataset_name: str | None = Field(default=None, max_length=80)


@router.get("/key-suggestions/{dataset_id}")
def key_suggestions(
    dataset_id: str,
    user: User = Depends(require_role("student")),
) -> dict:
    suggestions = MergeService().suggest_key_columns(dataset_id)
    return success_response(suggestions, {"count": len(suggestions)})


@router.post("/preview")
def merge_preview(
    payload: MergePreviewRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = MergeService().preview_merge(
        dataset_ids=payload.dataset_ids,
        key_column_mappings=payload.key_column_mappings,
        time_column_mappings=payload.time_column_mappings or None,
    )
    return success_response(result)


@router.post("/harmonize")
def harmonize_keys(
    payload: HarmonizeRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = MergeService().harmonize_keys(
        dataset_id=payload.dataset_id,
        key_column=payload.key_column,
        rename_map=payload.rename_map,
        owner_user_id=user.user_id,
    )
    return success_response(result)


@router.post("/ai-harmonize")
def ai_harmonize(
    payload: AiHarmonizeRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    suggestions = MergeService().ai_harmonize_suggestions(
        dataset_ids=payload.dataset_ids,
        key_column_mappings=payload.key_column_mappings,
    )
    return success_response(suggestions, {"count": len(suggestions)})


@router.post("/time-points")
def time_points(
    payload: TimePointsRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = MergeService().available_time_points(
        dataset_ids=payload.dataset_ids,
        time_column_mappings=payload.time_column_mappings,
    )
    return success_response(result)


@router.post("/execute")
def execute_merge(
    payload: MergeExecuteRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = MergeService().execute_merge(
        dataset_ids=payload.dataset_ids,
        key_column_mappings=payload.key_column_mappings,
        join_type=payload.join_type,
        time_column_mappings=payload.time_column_mappings or None,
        selected_time_points=payload.selected_time_points or None,
        topic_id=payload.topic_id,
        owner_user_id=user.user_id,
        dataset_name=payload.dataset_name,
    )
    return success_response(result)
