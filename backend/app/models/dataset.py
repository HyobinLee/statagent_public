from app.models.common import APIModel

COLUMN_ROLE_LABELS = {
    "measure": "측정값",
    "group": "집단 나누기",
    "period": "시점",
    "location": "위치",
    "identifier": "식별자",
    "reference": "출처·참고",
}
COLUMN_ROLE_ORDER = ("measure", "group", "period", "location", "identifier", "reference")


class ColumnValueLabel(APIModel):
    value: str
    label: str
    unit: str | None = None
    note: str | None = None


class DatasetColumn(APIModel):
    name: str
    display_name: str
    dtype: str
    description: str
    unit: str | None = None
    role: str | None = None
    role_label: str | None = None
    value_labels: list[ColumnValueLabel] = []
    warnings: list[str] = []
    secondary: bool = False
    estimated: bool = False


class DatasetNote(APIModel):
    label: str
    text: str


class RecommendedAnalysis(APIModel):
    tool_name: str
    label: str
    tool_args: dict
    description: str


class Dataset(APIModel):
    dataset_id: str
    topic_id: str
    name: str
    source: str
    source_note: str
    csv_path: str
    description: str
    time_range: str
    geographic_unit: str | None = None
    columns: list[DatasetColumn]
    recommended_analyses: list[RecommendedAnalysis]
    source_notes: list[DatasetNote] = []
    uploaded: bool = False
    curated: bool = False
    owner_user_id: str | None = None
    merged: bool = False
    merge_sources: list[dict] | None = None
    merge_key_column: str | None = None
