from pathlib import Path

from app.config import get_settings
from app.core.errors import AppError


def is_gcs_uri(value: str) -> bool:
    return value.startswith("gs://")


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not is_gcs_uri(uri):
        raise ValueError("not a GCS URI")
    without_scheme = uri[5:]
    bucket, _, blob_name = without_scheme.partition("/")
    if not bucket or not blob_name:
        raise ValueError("invalid GCS URI")
    return bucket, blob_name


class DatasetObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()

    def enabled(self) -> bool:
        return self.settings.enable_cloud_storage and bool(self.bucket_name())

    def bucket_name(self) -> str:
        return self.settings.gcs_dataset_bucket or self.settings.gcs_chart_bucket

    def local_cache_path(self, dataset_id: str) -> Path:
        return self.settings.local_data_dir / "gcs_cache" / f"{dataset_id}.csv"

    def object_name(self, owner_user_id: str, dataset_id: str) -> str:
        prefix = self.settings.gcs_dataset_prefix.strip().strip("/")
        owner = owner_user_id.strip().replace("/", "_") or "unknown"
        name = f"{owner}/{dataset_id}.csv"
        return f"{prefix}/{name}" if prefix else name

    def uri_for(self, owner_user_id: str, dataset_id: str) -> str:
        if not self.enabled():
            raise AppError(
                "GCS_BUCKET_REQUIRED",
                "운영용 자료 저장소를 사용하려면 GCS_DATASET_BUCKET 또는 GCS_CHART_BUCKET이 필요합니다.",
                "민감한 CSV 자료는 공개 차트 버킷과 분리한 GCS_DATASET_BUCKET에 저장해 주세요.",
                500,
            )
        return f"gs://{self.bucket_name()}/{self.object_name(owner_user_id, dataset_id)}"

    def _client(self):
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise AppError(
                "GOOGLE_CLOUD_DEPENDENCY_MISSING",
                "Cloud Storage 연동 패키지가 설치되어 있지 않습니다.",
                '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
                500,
            ) from exc
        kwargs = {}
        if self.settings.google_cloud_project:
            kwargs["project"] = self.settings.google_cloud_project
        return storage.Client(**kwargs)

    def upload_file(self, local_path: Path, gcs_uri: str) -> None:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        bucket = self._client().bucket(bucket_name)
        bucket.blob(blob_name).upload_from_filename(local_path, content_type="text/csv")

    def download_file(self, gcs_uri: str, local_path: Path) -> Path:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        bucket = self._client().bucket(bucket_name)
        bucket.blob(blob_name).download_to_filename(local_path)
        return local_path

    def delete_file(self, gcs_uri: str) -> None:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        bucket = self._client().bucket(bucket_name)
        bucket.blob(blob_name).delete()
