import os
from pathlib import Path

LESSONS_APP_DIR = Path(__file__).resolve().parent
LESSONS_BACKEND_DIR = LESSONS_APP_DIR.parent
REPO_ROOT = LESSONS_BACKEND_DIR.parent.parent

LESSON_DATA_DIR = LESSONS_APP_DIR / "data"
LESSON_CSV_DIR = LESSON_DATA_DIR / "csv"
LESSON_DEFS_PATH = LESSON_DATA_DIR / "lesson_defs.json"

_LOCAL_DATA_DIR = LESSONS_BACKEND_DIR / ".local_data"

DEFAULT_MAIN_BACKEND_URL = "http://127.0.0.1:8080"

_DEFAULT_ENV = {
    "LOCAL_DATA_DIR": str(_LOCAL_DATA_DIR),
    "LOCAL_CHART_DIR": str(_LOCAL_DATA_DIR / "static" / "charts"),
    "LOCAL_REPORT_IMAGE_DIR": str(_LOCAL_DATA_DIR / "static" / "report-images"),
    "FIRESTORE_COLLECTION_PREFIX": "lesson",
    "CORS_ORIGINS": "http://127.0.0.1:8001,http://localhost:8001",
    "MAIN_BACKEND_URL": DEFAULT_MAIN_BACKEND_URL,
}


def ensure_env_defaults() -> None:
    for key, value in _DEFAULT_ENV.items():
        os.environ.setdefault(key, value)


def main_backend_url() -> str:
    return os.getenv("MAIN_BACKEND_URL", DEFAULT_MAIN_BACKEND_URL).rstrip("/")
