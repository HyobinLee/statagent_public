import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.core.errors import AppError, success_response
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.services.dataset_service import DatasetService
from app.services.kosis_service import KosisDatasetService
from app.services.topic_service import TopicService

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class KosisRecommendRequest(BaseModel):
    topic_id: str = Field(..., min_length=1, max_length=120)
    research_question: str = Field(..., min_length=1, max_length=500)
    grade_level: str = Field(default="middle_high", max_length=40)


class KosisSearchRequest(BaseModel):
    topic_id: str = Field(..., min_length=1, max_length=120)
    search_keyword: str = Field(..., min_length=1, max_length=120)
    research_question: str = Field(default="", max_length=500)
    grade_level: str = Field(default="middle_high", max_length=40)


class KosisImportRequest(BaseModel):
    topic_id: str = Field(..., min_length=1, max_length=120)
    recommendation: dict[str, Any]


class SheetUpdateRequest(BaseModel):
    updates: list[dict[str, Any]] = Field(default_factory=list)


class DeleteColumnsRequest(BaseModel):
    columns: list[str] = Field(default_factory=list)


class DerivedColumnRequest(BaseModel):
    new_column: str = Field(..., min_length=1, max_length=80)
    formula: str = Field(..., min_length=1, max_length=500)
    display_name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=300)


def _validate_topic(topic_id: str) -> None:
    if not topic_id.startswith("custom_"):
        TopicService().get_topic(topic_id)


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    topic_id: str = Form(...),
    dataset_name: str | None = Form(None),
    school_level: str | None = Form(None),
    user: User = Depends(require_role("student")),
) -> dict:
    _validate_topic(topic_id)
    content = await file.read()
    payload = DatasetService().create_uploaded_dataset(
        filename=file.filename or "uploaded.csv",
        content=content,
        topic_id=topic_id,
        owner_user_id=user.user_id,
        dataset_name=dataset_name,
        school_level=school_level,
    )
    return success_response(payload)


@router.post("/kosis/recommend")
def recommend_kosis_datasets(
    payload: KosisRecommendRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    _validate_topic(payload.topic_id)
    recommendation = KosisDatasetService().recommend(
        research_question=payload.research_question,
        grade_level=payload.grade_level,
    )
    return success_response(recommendation)


@router.post("/kosis/search")
def search_kosis_datasets(
    payload: KosisSearchRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    _validate_topic(payload.topic_id)
    recommendation = KosisDatasetService().search_by_keyword(
        search_keyword=payload.search_keyword,
        research_question=payload.research_question,
        grade_level=payload.grade_level,
    )
    return success_response(recommendation)


@router.post("/kosis/import")
def import_kosis_dataset(
    payload: KosisImportRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    _validate_topic(payload.topic_id)
    imported = KosisDatasetService().import_recommendation(
        topic_id=payload.topic_id,
        owner_user_id=user.user_id,
        recommendation=payload.recommendation,
    )
    return success_response(imported)


@router.get("/{dataset_id}/schema")
def dataset_schema(
    dataset_id: str,
    school_level: str = "",
    user: User = Depends(get_current_user),
) -> dict:
    from app.models.project import normalize_school_level

    service = DatasetService()
    service.assert_read_access(dataset_id, user)
    return success_response(service.schema(dataset_id, school_level=normalize_school_level(school_level)))


@router.get("/{dataset_id}/summary")
def dataset_summary(dataset_id: str, user: User = Depends(get_current_user)) -> dict:
    service = DatasetService()
    service.assert_read_access(dataset_id, user)
    return success_response(service.summary(dataset_id))


@router.get("/{dataset_id}/sheet")
def dataset_sheet(
    dataset_id: str,
    limit: int = 100,
    offset: int = 0,
    filters: str = "",
    user: User = Depends(get_current_user),
) -> dict:
    service = DatasetService()
    service.assert_read_access(dataset_id, user)
    parsed_filters: dict[str, Any] = {}
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError as exc:
            raise AppError(
                "SHEET_FILTER_INVALID",
                "자료 표 필터를 읽을 수 없습니다.",
                "필터를 초기화한 뒤 다시 시도해 주세요.",
            ) from exc
        if not isinstance(parsed, dict):
            raise AppError(
                "SHEET_FILTER_INVALID",
                "자료 표 필터 형식이 올바르지 않습니다.",
                "필터를 초기화한 뒤 다시 시도해 주세요.",
            )
        parsed_filters = parsed
    return success_response(service.sheet(dataset_id, limit=limit, offset=offset, filters=parsed_filters))


@router.patch("/{dataset_id}/sheet")
def update_dataset_sheet(
    dataset_id: str,
    payload: SheetUpdateRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = DatasetService().update_cells(dataset_id, user.user_id, payload.updates)
    return success_response(result)


@router.post("/{dataset_id}/columns/delete")
def delete_dataset_columns(
    dataset_id: str,
    payload: DeleteColumnsRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = DatasetService().delete_columns(dataset_id, user.user_id, payload.columns)
    return success_response(result)


@router.post("/{dataset_id}/derived-column")
def add_derived_column(
    dataset_id: str,
    payload: DerivedColumnRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = DatasetService().add_derived_column(
        dataset_id,
        user.user_id,
        new_column=payload.new_column,
        formula=payload.formula,
        display_name=payload.display_name,
        description=payload.description,
    )
    return success_response(result)
