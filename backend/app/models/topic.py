from typing import Literal

from pydantic import Field

from app.models.common import APIModel

TopicLevel = Literal["middle", "high", "middle_high"]


class TopicLevelVariant(APIModel):
    title: str | None = None
    question: str | None = None
    concepts: list[str] | None = None
    recommended_charts: list[str] | None = None
    guidance: str | None = None


class Topic(APIModel):
    topic_id: str
    title: str
    question: str
    category: str
    level: TopicLevel
    concepts: list[str]
    recommended_charts: list[str]
    guidance: str | None = None
    level_variants: dict[str, TopicLevelVariant] = Field(default_factory=dict)
    disabled: bool = False

    def for_school_level(self, school_level: str | None) -> "Topic":
        variant = self.level_variants.get(school_level or "")
        if not variant:
            return self
        overrides = {key: value for key, value in variant.model_dump().items() if value is not None}
        return self.model_copy(update=overrides)
