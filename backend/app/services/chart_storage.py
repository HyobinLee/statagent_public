from pathlib import Path

from app.config import get_settings
from app.core.errors import AppError


class LocalChartStorage:
    def base_path(self) -> Path:
        return get_settings().local_chart_dir

    def publish_chart(self, chart_id: str, png_path: Path, svg_path: Path) -> dict:
        return {
            "png_url": f"/static/charts/{png_path.name}",
            "svg_url": f"/static/charts/{svg_path.name}",
            "storage_backend": "local",
            "gcs_png_uri": None,
            "gcs_svg_uri": None,
        }


class GoogleCloudStorageChartStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.gcs_chart_bucket:
            raise AppError(
                "GCS_BUCKET_REQUIRED",
                "Cloud Storage를 사용하려면 GCS_CHART_BUCKET이 필요합니다.",
                "환경 변수에 차트 저장용 버킷 이름을 설정해 주세요.",
                500,
            )

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

    def _blob_name(self, filename: str) -> str:
        prefix = self.settings.gcs_chart_prefix.strip().strip("/")
        return f"{prefix}/{filename}" if prefix else filename

    def _public_url(self, blob_name: str) -> str:
        if self.settings.gcs_public_base_url:
            return f"{self.settings.gcs_public_base_url.rstrip('/')}/{blob_name}"
        return f"https://storage.googleapis.com/{self.settings.gcs_chart_bucket}/{blob_name}"

    def publish_chart(self, chart_id: str, png_path: Path, svg_path: Path) -> dict:
        bucket = self._client().bucket(self.settings.gcs_chart_bucket)
        uploaded = {}
        for path, content_type, key in [
            (png_path, "image/png", "png"),
            (svg_path, "image/svg+xml", "svg"),
        ]:
            blob_name = self._blob_name(path.name)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(path, content_type=content_type)
            uploaded[key] = {
                "url": self._public_url(blob_name),
                "gcs_uri": f"gs://{self.settings.gcs_chart_bucket}/{blob_name}",
            }
        return {
            "png_url": uploaded["png"]["url"],
            "svg_url": uploaded["svg"]["url"],
            "storage_backend": "gcs",
            "gcs_png_uri": uploaded["png"]["gcs_uri"],
            "gcs_svg_uri": uploaded["svg"]["gcs_uri"],
            "chart_id": chart_id,
        }


def get_chart_storage():
    if get_settings().enable_cloud_storage:
        return GoogleCloudStorageChartStorage()
    return LocalChartStorage()
