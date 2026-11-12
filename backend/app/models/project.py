from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.time import now_utc
from app.models.common import APIModel

ProjectStatus = Literal[
    "created",
    "topic_selected",
    "dataset_chosen",
    "analysis_done",
    "conclusion_submitted",
    "stopped",
]

StepType = Literal[
    "topic_selected",
    "dataset_chosen",
    "analysis_done",
    "interpretation_saved",
    "synthesis_done",
    "reflection_written",
]

SchoolLevel = Literal["middle", "high", "middle_high"]


def normalize_school_level(value: object) -> SchoolLevel | None:
    return value if value in {"middle", "high", "middle_high"} else None


class InquiryStep(APIModel):
    step_id: str
    step_type: StepType
    payload: dict
    timestamp: datetime = Field(default_factory=now_utc)


class Project(APIModel):
    project_id: str
    owner_user_id: str
    school_level: SchoolLevel | None = None
    topic_id: str | None = None
    custom_topic_title: str | None = None
    custom_topic_question: str | None = None
    dataset_id: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    status: ProjectStatus = "created"
    steps: list[InquiryStep] = Field(default_factory=list)
    latest_analysis_result_id: str | None = None
    analysis_result_ids: list[str] = Field(default_factory=list)
    synthesis_result_ids: list[str] = Field(default_factory=list)
    report_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
