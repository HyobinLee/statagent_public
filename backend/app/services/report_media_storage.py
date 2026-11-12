import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import get_settings
from app.core.errors import AppError

REPORT_IMAGE_MARKER = "/static/report-images/"

MAX_IMAGE_BYTES = 8 * 1024 * 1024
EXTERNAL_FETCH_TIMEOUT_SECONDS = 10
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def _invalid(message: str, hint: str) -> AppError:
    return AppError("INVALID_ARGUMENT", message, hint, 400)


class LocalReportMediaStorage:
    def base_path(self) -> Path:
        return get_settings().local_report_image_dir

    def publish(self, filename: str, content: bytes) -> str:
        path = self.base_path() / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"{REPORT_IMAGE_MARKER}{filename}"


class GoogleCloudStorageReportMediaStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.gcs_chart_bucket:
            raise AppError(
                "GCS_BUCKET_REQUIRED",
                "Cloud Storage를 사용하려면 GCS_CHART_BUCKET이 필요합니다.",
                "환경 변수에 저장용 버킷 이름을 설정해 주세요.",
                500,
            )

    def publish(self, filename: str, content: bytes) -> str:
        from google.cloud import storage

        kwargs = {}
        if self.settings.google_cloud_project:
            kwargs["project"] = self.settings.google_cloud_project
        client = storage.Client(**kwargs)
        blob_name = f"report-images/{filename}"
        blob = client.bucket(self.settings.gcs_chart_bucket).blob(blob_name)
        blob.upload_from_string(content, content_type=_content_type_for(filename))
        if self.settings.gcs_public_base_url:
            return f"{self.settings.gcs_public_base_url.rstrip('/')}/{blob_name}"
        return f"https://storage.googleapis.com/{self.settings.gcs_chart_bucket}/{blob_name}"


def get_report_media_storage():
    if get_settings().enable_cloud_storage:
        return GoogleCloudStorageReportMediaStorage()
    return LocalReportMediaStorage()


def _content_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    for content_type, extension in ALLOWED_IMAGE_TYPES.items():
        if extension == suffix:
            return content_type
    return "application/octet-stream"


def store_uploaded_image(filename: str, content: bytes, content_type: str | None) -> str:
    if not content:
        raise _invalid("빈 파일은 올릴 수 없습니다.", "그림 파일을 다시 선택해 주세요.")
    if len(content) > MAX_IMAGE_BYTES:
        raise _invalid(
            f"그림은 {MAX_IMAGE_BYTES // (1024 * 1024)}MB까지 올릴 수 있습니다.",
            "그림 크기를 줄여서 다시 올려 주세요.",
        )
    suffix = Path(filename or "").suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()
    extension = ALLOWED_IMAGE_TYPES.get(mime)
    if extension is None and suffix in ALLOWED_IMAGE_SUFFIXES:
        extension = ".jpg" if suffix == ".jpeg" else suffix
    if extension is None:
        raise _invalid(
            "PNG, JPG, WEBP, SVG 그림만 올릴 수 있습니다.",
            "그림 형식을 확인해 주세요.",
        )
    return get_report_media_storage().publish(f"img_{uuid4().hex[:16]}{extension}", content)


def store_external_image(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise _invalid(
            "https로 시작하는 그림 주소만 넣을 수 있습니다.",
            "그림 주소를 https://로 시작하게 적어 주세요.",
        )
    _reject_private_host(parsed.hostname)

    request = Request(parsed.geturl(), headers={"User-Agent": "stat-agent-report/1.0"})
    try:
        with urlopen(request, timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_IMAGE_BYTES:
                raise _invalid("그림이 너무 큽니다.", "더 작은 그림 주소를 넣어 주세요.")
            mime = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            extension = ALLOWED_IMAGE_TYPES.get(mime)
            if extension is None:
                raise _invalid(
                    "그림 파일이 아닌 주소입니다.",
                    "PNG, JPG, WEBP, SVG 그림을 가리키는 주소를 넣어 주세요.",
                )
            content = response.read(MAX_IMAGE_BYTES + 1)
    except AppError:
        raise
    except (OSError, ValueError) as exc:
        raise _invalid(
            "그림 주소를 불러오지 못했습니다.",
            "주소가 맞는지, 누구나 볼 수 있는 그림인지 확인해 주세요.",
        ) from exc

    if len(content) > MAX_IMAGE_BYTES:
        raise _invalid("그림이 너무 큽니다.", "더 작은 그림 주소를 넣어 주세요.")
    if not content:
        raise _invalid("그림 내용이 비어 있습니다.", "다른 그림 주소를 넣어 주세요.")
    return get_report_media_storage().publish(f"img_{uuid4().hex[:16]}{extension}", content)


def _reject_private_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise _invalid(
            "그림 주소의 서버를 찾을 수 없습니다.",
            "주소를 다시 확인해 주세요.",
        ) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise _invalid(
                "내부망 주소의 그림은 넣을 수 없습니다.",
                "누구나 볼 수 있는 인터넷 주소의 그림을 넣어 주세요.",
            )


def is_stored_image_url(url: str) -> bool:
    text = str(url or "")
    if REPORT_IMAGE_MARKER in text:
        return True
    settings = get_settings()
    if settings.gcs_chart_bucket:
        prefix = "report-images/"
        if settings.gcs_public_base_url:
            base = f"{settings.gcs_public_base_url.rstrip('/')}/{prefix}"
            if text.startswith(base):
                return True
        if text.startswith(f"https://storage.googleapis.com/{settings.gcs_chart_bucket}/{prefix}"):
            return True
    return False


def local_image_path(url: str) -> Path | None:
    text = str(url or "")
    if REPORT_IMAGE_MARKER not in text:
        return None
    filename = Path(urlparse(text).path or text).name
    if not filename:
        return None
    return get_settings().local_report_image_dir / filename
