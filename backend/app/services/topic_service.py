import json
from functools import lru_cache

from app.config import get_settings
from app.core.errors import AppError
from app.models.topic import Topic


@lru_cache
def _load_topics() -> list[Topic]:
    path = get_settings().data_dir / "topics.json"
    with path.open("r", encoding="utf-8") as file:
        return [Topic(**item) for item in json.load(file)]


class TopicService:
    def list_topics(
        self,
        include_disabled: bool = False,
        school_level: str | None = None,
    ) -> list[Topic]:
        topics = _load_topics()
        if not include_disabled:
            topics = [topic for topic in topics if not topic.disabled]
        if school_level in {"middle", "high"}:
            topics = [topic for topic in topics if topic.level in {school_level, "middle_high"}]
            topics = [topic.for_school_level(school_level) for topic in topics]
        return topics

    def get_topic(self, topic_id: str, school_level: str | None = None) -> Topic:
        for topic in _load_topics():
            if topic.topic_id == topic_id:
                if topic.disabled:
                    raise AppError(
                        "TOPIC_DISABLED",
                        "아직 사용할 수 없는 주제입니다.",
                        "활성화된 주제를 선택해 주세요.",
                        404,
                    )
                return topic.for_school_level(school_level)
        raise AppError(
            "TOPIC_NOT_FOUND",
            "주제를 찾을 수 없습니다.",
            "주제 목록을 새로고침해 주세요.",
            404,
        )
