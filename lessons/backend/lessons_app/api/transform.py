from typing import Any

from app.core.errors import AppError, success_response
from app.dependencies import require_role
from app.models.user import User
from app.services.dataset_service import DatasetService
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services.dish_category import ALL_CATEGORIES, suggest_category
from lessons_app.services.materialize_column import materialize_column

router = APIRouter(prefix="/api/lessons/transform", tags=["lesson-transform"])


class FirstDigitPresetRequest(BaseModel):
    dataset_id: str
    source_column: str
    new_column: str = "첫자리숫자"


@router.post("/first-digit")
def first_digit_preset(
    payload: FirstDigitPresetRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = DatasetService().add_derived_column(
        payload.dataset_id,
        user.user_id,
        new_column=payload.new_column,
        formula=f"left({{{payload.source_column}}}, 1)",
        display_name="첫 자리 숫자",
        description=f"'{payload.source_column}' 값의 맨 앞자리 숫자",
    )
    return success_response(result)


class CategorySuggestionsRequest(BaseModel):
    dataset_id: str
    source_column: str


@router.post("/category-suggestions")
def category_suggestions(
    payload: CategorySuggestionsRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    service = DatasetService()
    service.assert_read_access(payload.dataset_id, user)
    df = service.read_dataframe(payload.dataset_id)
    if payload.source_column not in df.columns:
        raise AppError(
            "INVALID_COLUMN",
            f"'{payload.source_column}' 항목을 자료에서 찾을 수 없습니다.",
            "자료의 항목명을 다시 확인해 주세요.",
        )
    unique_values = [str(value) for value in df[payload.source_column].dropna().unique()]
    suggestions = [{"value": value, "suggested_category": suggest_category(value)} for value in sorted(unique_values)]
    return success_response({"suggestions": suggestions, "categories": list(ALL_CATEGORIES)})


class ApplyCategoryRequest(BaseModel):
    dataset_id: str
    source_column: str
    new_column: str = "주식종류"
    mapping: dict[str, str] = Field(default_factory=dict)


@router.post("/apply-category")
def apply_category(
    payload: ApplyCategoryRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    service = DatasetService()
    df = service.read_dataframe(payload.dataset_id)
    if payload.source_column not in df.columns:
        raise AppError(
            "INVALID_COLUMN",
            f"'{payload.source_column}' 항목을 자료에서 찾을 수 없습니다.",
            "자료의 항목명을 다시 확인해 주세요.",
        )
    source_values = df[payload.source_column].astype(str)
    missing = sorted(set(source_values.unique()) - set(payload.mapping))
    if missing:
        raise AppError(
            "CATEGORY_MAPPING_INCOMPLETE",
            f"아직 범주를 정하지 않은 값이 있습니다: {', '.join(missing[:5])}",
            "표에 있는 모든 값에 범주를 지정한 뒤 다시 확정해 주세요.",
        )
    invalid_categories = sorted(set(payload.mapping.values()) - set(ALL_CATEGORIES))
    if invalid_categories:
        raise AppError(
            "CATEGORY_INVALID",
            f"허용되지 않은 범주입니다: {', '.join(invalid_categories)}",
            f"다음 범주 중에서 선택해 주세요: {', '.join(ALL_CATEGORIES)}",
        )
    row_values: list[Any] = [payload.mapping[value] for value in source_values]
    result = materialize_column(
        dataset_id=payload.dataset_id,
        owner_user_id=user.user_id,
        new_column=payload.new_column,
        source_column=payload.source_column,
        row_values=row_values,
        display_name="주식 종류",
        description=f"'{payload.source_column}'을(를) 학생이 확정한 범주로 묶은 파생변수",
    )
    return success_response(result)
