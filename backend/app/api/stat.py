from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.errors import AppError, success_response
from app.dependencies import get_current_user
from app.models.stat_api import DatasetFetchRequest, PreferredPeriod
from app.models.user import User
from app.services.dataset_service import DatasetService
from app.services.stat_api_service import StatApiService
from app.services.topic_service import TopicService

router = APIRouter(prefix="/api/stat", tags=["stat-api"])


class RouteSourcesRequest(BaseModel):
    research_question: str = Field(..., min_length=1, max_length=1000)
    grade_level: str = Field(default="unknown", max_length=40)
    source_ids: list[str] = Field(default_factory=list)


class SearchDatasetsRequest(BaseModel):
    research_question: str = Field(..., min_length=1, max_length=1000)
    grade_level: str = Field(default="unknown", max_length=40)
    source_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    preferred_period: PreferredPeriod | None = None
    preferred_region: str | None = Field(default=None, max_length=120)


def _validate_topic(topic_id: str | None) -> None:
    if not topic_id:
        return
    if not topic_id.startswith("custom_"):
        TopicService().get_topic(topic_id)


@router.get("/sources")
def list_stat_sources(_user: User = Depends(get_current_user)) -> dict:
    sources = StatApiService().list_sources()
    return success_response(
        {"sources": sources},
        {"count": len(sources), "backend_registry_checked": True},
    )


@router.post("/route-sources")
def route_stat_sources(payload: RouteSourcesRequest, _user: User = Depends(get_current_user)) -> dict:
    routed = StatApiService().route_sources(
        research_question=payload.research_question,
        grade_level=payload.grade_level,
        source_ids=payload.source_ids or None,
    )
    return success_response(routed)


@router.post("/search-datasets")
def search_stat_datasets(payload: SearchDatasetsRequest, _user: User = Depends(get_current_user)) -> dict:
    result = StatApiService().search_datasets(
        research_question=payload.research_question,
        grade_level=payload.grade_level,
        source_ids=payload.source_ids or None,
        keywords=payload.keywords or None,
        preferred_period=payload.preferred_period,
        preferred_region=payload.preferred_region,
    )
    return success_response(result, result.get("metadata"))


@router.post("/fetch-csv")
def fetch_stat_csv(payload: DatasetFetchRequest, user: User = Depends(get_current_user)) -> dict:
    _validate_topic(payload.topic_id)
    result = StatApiService().fetch_csv(payload)
    result_payload = result.model_dump(mode="json")
    if payload.import_as_dataset:
        if user.role != "student":
            raise AppError(
                "STAT_API_IMPORT_FORBIDDEN",
                "학생 계정에서만 외부 API 자료를 프로젝트 자료로 등록할 수 있습니다.",
                "교사 미리보기 또는 학생 계정에서 다시 시도해 주세요.",
                403,
            )
        if not payload.topic_id:
            raise AppError(
                "STAT_API_TOPIC_REQUIRED",
                "자료를 프로젝트에 등록하려면 topic_id가 필요합니다.",
                "먼저 주제를 선택한 뒤 다시 시도해 주세요.",
            )
        metadata = result.metadata
        imported = DatasetService().create_uploaded_dataset(
            filename=result.csv_filename,
            content=result.csv_text.encode("utf-8-sig"),
            topic_id=payload.topic_id,
            owner_user_id=user.user_id,
            dataset_name=payload.dataset_name or metadata.dataset_title,
            source=metadata.source_name,
            source_note=f"{metadata.provider} {metadata.dataset_id}에서 {metadata.fetched_at} API로 가져옴",
            description=f"{metadata.source_name}에서 자동 수집한 공개 통계 자료입니다.",
            time_range=(
                f"{metadata.period_range.start or '?'}~{metadata.period_range.end or '?'}"
                if metadata.period_range
                else "외부 API 자료"
            ),
            geographic_unit=";".join(payload.country_codes or payload.region_codes or payload.station_ids) or None,
        )
        result_payload["imported_dataset"] = imported
    return success_response(result_payload, {"source_id": payload.source_id, "row_count": result.row_count})


@router.get("/manual-guide")
def stat_manual_guide(
    source_id: str = Query(..., min_length=1, max_length=80),
    _user: User = Depends(get_current_user),
) -> dict:
    return success_response(StatApiService().manual_guide(source_id))
