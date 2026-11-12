import json
from pathlib import Path

from app.core.errors import AppError
from app.repositories.factory import get_repository


def _load_schools() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "data" / "schools.json"
    schools = json.loads(path.read_text(encoding="utf-8"))
    if not any(school.get("is_default") for school in schools):
        schools[0]["is_default"] = True
    return schools


FIXED_SCHOOLS: list[dict] = _load_schools()

DEFAULT_SCHOOL = next(school for school in FIXED_SCHOOLS if school["is_default"])
SCHOOLS_BY_ID = {school["school_id"]: school for school in FIXED_SCHOOLS}

SCHOOL_SETTING_KEY = "lesson_school"


def get_current_school() -> dict:
    setting = get_repository().get_setting(SCHOOL_SETTING_KEY)
    if setting:
        school_id = (setting.get("value") or {}).get("school_id")
        if school_id in SCHOOLS_BY_ID:
            return SCHOOLS_BY_ID[school_id]
    return DEFAULT_SCHOOL


def set_current_school(school_id: str) -> dict:
    if school_id not in SCHOOLS_BY_ID:
        raise AppError(
            "SCHOOL_NOT_ALLOWED",
            "지정할 수 없는 학교입니다.",
            "목록에 있는 학교 중 하나를 선택해 주세요.",
        )
    get_repository().upsert_setting(SCHOOL_SETTING_KEY, {"school_id": school_id})
    return SCHOOLS_BY_ID[school_id]
