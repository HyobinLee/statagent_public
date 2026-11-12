from typing import Any, Literal

from app.models.common import APIModel

AccessStatus = Literal[
    "AUTO_SUPPORTED",
    "SUPPORTED_BUT_KEY_MISSING",
    "FOUND_BUT_UNSUPPORTED",
    "MANUAL_CSV_AVAILABLE",
    "API_ONLY_UNSUPPORTED",
    "NO_GOOD_PUBLIC_DATA",
]

SourceCategory = Literal[
    "catalog",
    "economy",
    "national_indicator",
    "spatial",
    "weather",
    "air_quality",
    "education",
    "transport",
    "international",
]


class PreferredPeriod(APIModel):
    start: str | None = None
    end: str | None = None


class StatApiSource(APIModel):
    source_id: str
    display_name: str
    provider: str
    category: SourceCategory
    enabled_env: str
    required_env_keys: list[str]
    auth_required: bool
    supports_search: bool
    supports_fetch: bool
    supports_csv_export: bool
    manual_download_url: str
    docs_url: str
    default_access_status_when_disabled: AccessStatus
    student_friendly_use_cases: list[str]
    cautions: list[str]
    enabled: bool = True
    auth_configured: bool = False


class DatasetAccessInfo(APIModel):
    source_id: str
    backend_supported: bool
    auth_required: bool
    auth_configured: bool
    access_status: AccessStatus
    auto_fetch_available: bool
    manual_download_available: bool
    manual_download_url: str | None = None
    missing_env_keys: list[str] = []
    reason: str


class ResearchQuestionContext(APIModel):
    question: str
    grade_level: Literal["middle", "high", "middle_high", "unknown"] = "unknown"
    analysis_types: list[str] = []
    desired_dimensions: list[str] = []
    desired_measures: list[str] = []
    preferred_period: PreferredPeriod | None = None
    preferred_region: str | None = None
    blocked_topics: list[str] = []


class CandidateDataset(APIModel):
    candidate_id: str
    source_id: str
    provider: str
    dataset_id: str
    dataset_title: str
    description: str | None = None
    docs_url: str | None = None
    manual_download_url: str | None = None
    api_detail_url: str | None = None
    available_dimensions: list[str] = []
    available_measures: list[str] = []
    period_range: PreferredPeriod | None = None
    unit: str | None = None
    license: str | None = None
    access_info: DatasetAccessInfo | None = None
    cautions: list[str] = []
    raw: dict[str, Any] | None = None


class DatasetMetadata(APIModel):
    source_id: str
    source_name: str
    provider: str
    dataset_id: str
    dataset_title: str
    fetched_at: str
    request_summary: dict[str, Any]
    period_range: PreferredPeriod | None = None
    unit: str | None = None
    license: str | None = None
    notes: list[str] = []
    original_docs_url: str | None = None
    original_data_url: str | None = None


class DatasetFetchRequest(APIModel):
    source_id: str
    dataset_id: str
    indicator_id: str | None = None
    item_id: str | None = None
    start_period: str | None = None
    end_period: str | None = None
    region_codes: list[str] = []
    country_codes: list[str] = []
    station_ids: list[str] = []
    dimensions: dict[str, str | list[str]] = {}
    raw_params: dict[str, str | int | float | bool | list[str]] = {}
    topic_id: str | None = None
    import_as_dataset: bool = False
    dataset_name: str | None = None


class CsvFetchResult(APIModel):
    csv_filename: str
    csv_text: str
    metadata: DatasetMetadata
    row_count: int
    warnings: list[str] = []
    imported_dataset: dict[str, Any] | None = None
