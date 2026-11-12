import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


class Settings(BaseModel):
    app_env: str = "local"
    app_region: str = "asia-northeast3"
    google_cloud_project: str = ""
    firebase_web_api_key: str = ""
    firebase_auth_domain: str = ""
    firebase_project_id: str = ""
    firebase_app_id: str = ""
    firebase_messaging_sender_id: str = ""
    firebase_measurement_id: str = ""
    firebase_whitelist_secret: str = ""
    firebase_service_account_id: str = ""
    enable_gemini: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 60
    gemini_max_function_calls: int = 5
    kosis_api_key: str = ""
    kosis_api_key_secret: str = ""
    stat_api_keys_secret: str = ""
    stat_api_cache_ttl_seconds: int = 86400
    stat_api_max_rows: int = 20000
    stat_api_request_timeout_ms: int = 15000
    stat_api_log_requests: bool = False
    enable_secret_manager: bool = False
    gemini_api_key_secret: str = ""
    enable_firestore: bool = False
    firestore_database: str = "(default)"
    firestore_collection_prefix: str = ""
    allow_cloud_reset: bool = False
    enable_cloud_storage: bool = False
    gcs_chart_bucket: str = ""
    gcs_chart_prefix: str = "charts"
    gcs_dataset_bucket: str = ""
    gcs_dataset_prefix: str = "datasets"
    gcs_public_base_url: str = ""
    local_data_dir: Path = BACKEND_DIR / ".local_data"
    local_chart_dir: Path = BACKEND_DIR / "app" / "static" / "charts"
    local_report_image_dir: Path = BACKEND_DIR / "app" / "static" / "report-images"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    dev_auth_enabled: bool = False
    auto_provision_firebase_users: bool = False
    firebase_default_role: str = "student"
    google_workspace_domain: str = ""
    min_student_age: int = 14
    privacy_policy_url: str = ""
    enable_map_tiles: bool = True
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    map_tile_attribution: str = "© OpenStreetMap contributors"
    map_tile_user_agent: str = "stat-agent/0.1"
    map_tile_timeout_seconds: int = 10
    enable_sgis_boundaries: bool = True
    sgis_boundary_year: str = "2022"
    sgis_timeout_seconds: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def data_dir(self) -> Path:
        return BACKEND_DIR / "app" / "data"

    @property
    def csv_dir(self) -> Path:
        return self.data_dir / "csv"


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    settings = Settings(
        app_env=os.getenv("APP_ENV", "local"),
        app_region=os.getenv("APP_REGION", "asia-northeast3"),
        google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        firebase_web_api_key=os.getenv("FIREBASE_WEB_API_KEY", ""),
        firebase_auth_domain=os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", ""),
        firebase_app_id=os.getenv("FIREBASE_APP_ID", ""),
        firebase_messaging_sender_id=os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        firebase_measurement_id=os.getenv("FIREBASE_MEASUREMENT_ID", ""),
        firebase_whitelist_secret=os.getenv("FIREBASE_WHITELIST_SECRET", ""),
        firebase_service_account_id=os.getenv("FIREBASE_SERVICE_ACCOUNT_ID", ""),
        enable_gemini=_bool_env("ENABLE_GEMINI", False),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_timeout_seconds=int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")),
        gemini_max_function_calls=int(os.getenv("GEMINI_MAX_FUNCTION_CALLS", "5")),
        kosis_api_key=os.getenv("KOSIS_API_KEY", ""),
        kosis_api_key_secret=os.getenv("KOSIS_API_KEY_SECRET", ""),
        stat_api_keys_secret=os.getenv("STAT_API_KEYS_SECRET", ""),
        stat_api_cache_ttl_seconds=int(os.getenv("STAT_API_CACHE_TTL_SECONDS", "86400")),
        stat_api_max_rows=int(os.getenv("STAT_API_MAX_ROWS", "20000")),
        stat_api_request_timeout_ms=int(os.getenv("STAT_API_REQUEST_TIMEOUT_MS", "15000")),
        stat_api_log_requests=_bool_env("STAT_API_LOG_REQUESTS", False),
        enable_secret_manager=_bool_env("ENABLE_SECRET_MANAGER", False),
        gemini_api_key_secret=os.getenv("GEMINI_API_KEY_SECRET", ""),
        enable_firestore=_bool_env("ENABLE_FIRESTORE", False),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        firestore_collection_prefix=os.getenv("FIRESTORE_COLLECTION_PREFIX", ""),
        allow_cloud_reset=_bool_env("ALLOW_CLOUD_RESET", False),
        enable_cloud_storage=_bool_env("ENABLE_CLOUD_STORAGE", False),
        gcs_chart_bucket=os.getenv("GCS_CHART_BUCKET", ""),
        gcs_chart_prefix=os.getenv("GCS_CHART_PREFIX", "charts"),
        gcs_dataset_bucket=os.getenv("GCS_DATASET_BUCKET", ""),
        gcs_dataset_prefix=os.getenv("GCS_DATASET_PREFIX", "datasets"),
        gcs_public_base_url=os.getenv("GCS_PUBLIC_BASE_URL", ""),
        local_data_dir=_path_env("LOCAL_DATA_DIR", BACKEND_DIR / ".local_data"),
        local_chart_dir=_path_env("LOCAL_CHART_DIR", BACKEND_DIR / "app" / "static" / "charts"),
        local_report_image_dir=_path_env("LOCAL_REPORT_IMAGE_DIR", BACKEND_DIR / "app" / "static" / "report-images"),
        cors_origins=os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000",
        ),
        dev_auth_enabled=_bool_env("DEV_AUTH_ENABLED", False),
        auto_provision_firebase_users=_bool_env("AUTO_PROVISION_FIREBASE_USERS", False),
        firebase_default_role=os.getenv("FIREBASE_DEFAULT_ROLE", "student"),
        google_workspace_domain=os.getenv("GOOGLE_WORKSPACE_DOMAIN", ""),
        min_student_age=int(os.getenv("MIN_STUDENT_AGE", "14")),
        privacy_policy_url=os.getenv("PRIVACY_POLICY_URL", ""),
        enable_map_tiles=_bool_env("ENABLE_MAP_TILES", True),
        map_tile_url=os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
        map_tile_attribution=os.getenv("MAP_TILE_ATTRIBUTION", "© OpenStreetMap contributors"),
        map_tile_user_agent=os.getenv("MAP_TILE_USER_AGENT", "stat-agent/0.1"),
        map_tile_timeout_seconds=int(os.getenv("MAP_TILE_TIMEOUT_SECONDS", "10")),
        enable_sgis_boundaries=_bool_env("ENABLE_SGIS_BOUNDARIES", True),
        sgis_boundary_year=os.getenv("SGIS_BOUNDARY_YEAR", "2022"),
        sgis_timeout_seconds=int(os.getenv("SGIS_TIMEOUT_SECONDS", "20")),
    )
    settings.local_data_dir.mkdir(parents=True, exist_ok=True)
    settings.local_chart_dir.mkdir(parents=True, exist_ok=True)
    settings.local_report_image_dir.mkdir(parents=True, exist_ok=True)
    return settings
