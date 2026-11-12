from app.core.errors import AppError, success_response
from app.dependencies import require_role
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import fixed_analysis_cache, tracks
from lessons_app.services.lesson_defs import get_lesson_def_for_track

router = APIRouter(prefix="/api/lessons", tags=["lesson-fixed-analysis"])

CACHE_COLLECTION = fixed_analysis_cache.COLLECTION


class FixedAnalysisRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)


@router.post("/{lesson_id}/fixed-analysis")
def run_fixed_analysis(
    lesson_id: str,
    payload: FixedAnalysisRequest,
    track: str = "",
    scenario: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, scenario = tracks.resolve(user, track, scenario)
    lesson_def = get_lesson_def_for_track(lesson_id, effective_track, scenario)
    result = fixed_analysis_cache.get_or_run(user, lesson_id, payload.key, effective_track, scenario, lesson_def)
    if result is None:
        raise AppError(
            "FIXED_ANALYSIS_NOT_FOUND",
            "이 차시에 그런 고정 분석이 없습니다.",
            "화면을 새로고침한 뒤 다시 시도해 주세요.",
            404,
        )
    return success_response(result)
