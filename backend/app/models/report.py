from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.time import now_utc
from app.models.common import APIModel

ReportStatus = Literal["submitted", "feedback_given", "returned"]


class Report(APIModel):
    report_id: str
    project_id: str
    student_user_id: str
    teacher_user_id: str | None = None
    topic_title: str
    dataset_name: str
    dataset_names: list[str] = Field(default_factory=list)
    dataset_sources: list[dict] = Field(default_factory=list)
    analysis_summary: dict
    analysis_summaries: list[dict] = Field(default_factory=list)
    chart_urls: list[str] = Field(default_factory=list)
    analysis_result_ids: list[str] = Field(default_factory=list)
    synthesis_result_ids: list[str] = Field(default_factory=list)
    conclusion_text: str
    layout: dict = Field(default_factory=dict)
    feedback_text: str | None = None
    ai_feedback_suggestion: str | None = None
    student_reflection: dict | None = None
    status: ReportStatus = "submitted"
    submitted_at: datetime = Field(default_factory=now_utc)
    feedback_at: datetime | None = None
