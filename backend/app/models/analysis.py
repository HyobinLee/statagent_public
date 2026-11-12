from datetime import datetime

from pydantic import Field

from app.core.time import now_utc
from app.models.common import APIModel


class AnalysisResult(APIModel):
    analysis_result_id: str
    project_id: str
    dataset_id: str
    tool_name: str
    tool_args: dict
    result: dict
    row_selection: dict | None = None
    chart_urls: list[str] = Field(default_factory=list)
    explanation_hint: str | None = None
    interpretation: str = ""
    interpretation_updated_at: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc)


class SynthesisResult(APIModel):
    synthesis_result_id: str
    project_id: str
    dataset_ids: list[str]
    key_column_mappings: dict = Field(default_factory=dict)
    time_column_mappings: dict = Field(default_factory=dict)
    tool_name: str
    tool_args: dict
    result: dict
    chart_urls: list[str] = Field(default_factory=list)
    explanation_hint: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
