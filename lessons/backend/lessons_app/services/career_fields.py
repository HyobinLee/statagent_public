import json
from functools import lru_cache

from app.core.errors import AppError

from lessons_app.config import LESSON_DATA_DIR

CAREER_FIELDS_PATH = LESSON_DATA_DIR / "career_fields.json"
CAREER_FIELDS_HIGH_PATH = LESSON_DATA_DIR / "career_fields.high.json"


@lru_cache
def _load_fields() -> list[dict]:
    with CAREER_FIELDS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache
def _load_fields_high() -> list[dict] | None:
    if not CAREER_FIELDS_HIGH_PATH.exists():
        return None
    with CAREER_FIELDS_HIGH_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _pools(track: str | None = None) -> list[list[dict]]:
    high = _load_fields_high()
    pools = [list_fields(track)]
    for pool in (_load_fields(), high):
        if pool is not None and pool is not pools[0]:
            pools.append(pool)
    return pools


def list_fields(track: str | None = None) -> list[dict]:
    from lessons_app.services.tracks import track_level

    if track and track_level(track) == "high":
        high = _load_fields_high()
        if high is not None:
            return high
    return _load_fields()


def get_field(field_id: str, track: str | None = None) -> dict:
    for pool in _pools(track):
        for field in pool:
            if field["field_id"] == field_id:
                return field
    raise AppError(
        "CAREER_FIELD_NOT_FOUND",
        "해당 진로 분야를 찾을 수 없습니다.",
        "목록에 있는 분야 중 하나를 선택해 주세요.",
        404,
    )


def get_topic(field_id: str, topic_id: str, track: str | None = None) -> dict:
    for pool in _pools(track):
        for field in pool:
            if field["field_id"] != field_id:
                continue
            for topic in field["topics"]:
                if topic["topic_id"] == topic_id:
                    return topic
    raise AppError(
        "CAREER_TOPIC_NOT_FOUND",
        "해당 주제를 찾을 수 없습니다.",
        "목록에 있는 주제 후보 중 하나를 선택해 주세요.",
        404,
    )
