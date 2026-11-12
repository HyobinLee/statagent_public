import json
import os
import re
from datetime import UTC, date, datetime
from functools import cached_property
from typing import Any

from app.config import get_settings
from app.core.errors import AppError

STAT_API_SECRET_VALUE_FIELDS = ("value", "api_key", "key", "secret", "service_key", "idntfc_id")
STAT_API_NO_EXPIRATION_VALUES = {"", "none", "null", "never", "no_expiration", "unlimited", "무한", "없음"}
STAT_API_EXPIRY_WARNING_DAYS = 30


class SecretManagerService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @cached_property
    def client(self):
        try:
            from google.cloud import secretmanager
        except ImportError as exc:
            raise AppError(
                "GOOGLE_CLOUD_DEPENDENCY_MISSING",
                "Secret Manager 연동 패키지가 설치되어 있지 않습니다.",
                '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
                500,
            ) from exc
        return secretmanager.SecretManagerServiceClient()

    def _version_name(self, secret_name: str) -> str:
        if secret_name.startswith("projects/"):
            return secret_name
        if not self.settings.google_cloud_project:
            raise AppError(
                "GOOGLE_PROJECT_REQUIRED",
                "Secret Manager를 사용하려면 GOOGLE_CLOUD_PROJECT가 필요합니다.",
                "환경 변수에 Google Cloud 프로젝트 ID를 설정해 주세요.",
                500,
            )
        return f"projects/{self.settings.google_cloud_project}/secrets/{secret_name}/versions/latest"

    def _secret_name(self, secret_name: str) -> str:
        if secret_name.startswith("projects/"):
            parts = secret_name.split("/versions/", 1)
            return parts[0]
        if not self.settings.google_cloud_project:
            raise AppError(
                "GOOGLE_PROJECT_REQUIRED",
                "Secret Manager를 사용하려면 GOOGLE_CLOUD_PROJECT가 필요합니다.",
                "환경 변수에 Google Cloud 프로젝트 ID를 설정해 주세요.",
                500,
            )
        return f"projects/{self.settings.google_cloud_project}/secrets/{secret_name}"

    def access_secret(self, secret_name: str) -> str:
        if not secret_name:
            raise AppError(
                "SECRET_NAME_REQUIRED",
                "Secret Manager secret 이름이 비어 있습니다.",
                "환경 변수에 secret 이름을 설정해 주세요.",
                500,
            )
        response = self.client.access_secret_version(name=self._version_name(secret_name))
        return response.payload.data.decode("utf-8")

    def add_secret_version(self, secret_name: str, value: str) -> str:
        if not secret_name:
            raise AppError(
                "SECRET_NAME_REQUIRED",
                "Secret Manager secret 이름이 비어 있습니다.",
                "환경 변수에 secret 이름을 설정해 주세요.",
                500,
            )
        parent = self._secret_name(secret_name)
        response = self.client.add_secret_version(
            parent=parent,
            payload={"data": value.encode("utf-8")},
        )
        return str(response.name)


def _normalize_date_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.rstrip(".")
    text = re.sub(r"[./]", "-", text)
    return text


def _parse_expiry_date(value: object) -> tuple[date | None, bool]:
    text = _normalize_date_text(value)
    if text.lower() in STAT_API_NO_EXPIRATION_VALUES:
        return None, True
    if not text:
        return None, True
    try:
        return datetime.strptime(text, "%Y-%m-%d").date(), True
    except ValueError:
        return None, False


def _extract_secret_value(payload: dict[str, Any]) -> str:
    for field in STAT_API_SECRET_VALUE_FIELDS:
        value = payload.get(field)
        if value is not None:
            return str(value)
    return ""


def parse_stat_api_secret_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in payload.items():
        key = str(raw_key)
        if raw_value is None:
            entries[key] = {"value": "", "expires_at": None}
        elif isinstance(raw_value, dict):
            expires_at = raw_value.get("expires_at", raw_value.get("expires_on", raw_value.get("valid_until")))
            expires_at_explicit = any(field in raw_value for field in ("expires_at", "expires_on", "valid_until"))
            entries[key] = {
                "value": _extract_secret_value(raw_value),
                "expires_at": expires_at,
                "expires_at_explicit": expires_at_explicit,
                "issuer": raw_value.get("issuer"),
                "account": raw_value.get("account"),
                "renewal_url": raw_value.get("renewal_url"),
                "notes": raw_value.get("notes"),
            }
        else:
            entries[key] = {"value": str(raw_value), "expires_at": None, "expires_at_explicit": False}
    return entries


def get_gemini_api_key() -> str:
    settings = get_settings()
    if settings.enable_secret_manager and settings.gemini_api_key_secret:
        return SecretManagerService().access_secret(settings.gemini_api_key_secret)
    return settings.gemini_api_key


def get_kosis_api_key() -> str:
    settings = get_settings()
    if settings.enable_secret_manager and settings.kosis_api_key_secret:
        return SecretManagerService().access_secret(settings.kosis_api_key_secret)
    return settings.kosis_api_key


def get_stat_api_secret_entries() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    if not settings.enable_secret_manager or not settings.stat_api_keys_secret:
        return {}
    raw = SecretManagerService().access_secret(settings.stat_api_keys_secret)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            "STAT_API_SECRET_INVALID_JSON",
            "통계 API Secret Manager 값이 JSON 형식이 아닙니다.",
            "docs/stat-api-secret-manager-template.json 형식으로 secret 값을 다시 등록해 주세요.",
            500,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            "STAT_API_SECRET_INVALID_SHAPE",
            "통계 API Secret Manager 값은 JSON 객체여야 합니다.",
            "키 이름과 발급받은 값을 쌍으로 담아 주세요.",
            500,
        )
    return parse_stat_api_secret_entries(payload)


def get_stat_api_secret_bundle() -> dict[str, str]:
    entries = get_stat_api_secret_entries()
    return {key: str(entry.get("value") or "") for key, entry in entries.items()}


def build_stat_api_key_status(
    *,
    expected_keys: list[str] | None = None,
    key_labels: dict[str, str] | None = None,
    key_usages: dict[str, list[str]] | None = None,
    entries: dict[str, dict[str, Any]] | None = None,
    warning_days: int = STAT_API_EXPIRY_WARNING_DAYS,
    today: date | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    expected = set(expected_keys or [])
    key_labels = key_labels or {}
    key_usages = key_usages or {}
    today = today or datetime.now(UTC).date()
    loaded_entries: dict[str, dict[str, Any]] = entries or {}
    secret_error: dict[str, str] | None = None
    secret_configured = bool(settings.enable_secret_manager and settings.stat_api_keys_secret)
    if entries is None and secret_configured:
        try:
            loaded_entries = get_stat_api_secret_entries()
        except AppError as exc:
            secret_error = {
                "error_code": exc.error_code,
                "message": exc.error_message_ko,
                "suggested_fix": exc.suggested_fix,
            }
    expected.update(loaded_entries.keys())
    for key in list(expected):
        if os.getenv(key, ""):
            expected.add(key)

    keys: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    summary = {
        "total": 0,
        "configured": 0,
        "missing": 0,
        "no_expiration": 0,
        "valid": 0,
        "expiring_soon": 0,
        "expired": 0,
        "invalid_expiry": 0,
        "untracked": 0,
    }

    if secret_error:
        alerts.append(
            {
                "severity": "blocked",
                "key_name": "STAT_API_KEYS_SECRET",
                "message": "통계 API Secret Manager 값을 읽을 수 없습니다.",
                "action": secret_error["suggested_fix"],
            }
        )

    for key in sorted(expected):
        entry = loaded_entries.get(key, {})
        env_value = os.getenv(key, "")
        secret_value = str(entry.get("value") or "")
        configured = bool(env_value or secret_value)
        expires_at_raw = entry.get("expires_at")
        expires_at, expiry_valid = _parse_expiry_date(expires_at_raw)
        days_remaining = (expires_at - today).days if expires_at else None
        value_source = "environment" if env_value else "secret" if secret_value else "missing"
        if not configured:
            expiry_status = "missing"
            severity = "info"
            action = "필요한 소스만 발급 후 Secret Manager에 value를 입력하세요."
        elif not expiry_valid:
            expiry_status = "invalid_expiry"
            severity = "attention"
            action = "expires_at을 YYYY-MM-DD 형식 또는 null로 고쳐 새 secret 버전을 등록하세요."
        elif expires_at is None:
            expiry_status = "no_expiration" if entry.get("expires_at_explicit") else "untracked"
            severity = "info" if expiry_status == "untracked" else "ok"
            action = (
                "운영 배포 전 Secret Manager JSON에 expires_at을 명시하세요."
                if expiry_status == "untracked"
                else "정기 점검 때 발급기관 정책 변경 여부만 확인하세요."
            )
        elif days_remaining is not None and days_remaining < 0:
            expiry_status = "expired"
            severity = "blocked"
            action = "즉시 키를 재발급하고 Secret Manager에 새 버전을 추가하세요."
        elif days_remaining is not None and days_remaining <= warning_days:
            expiry_status = "expiring_soon"
            severity = "attention"
            action = f"{days_remaining}일 이내 만료됩니다. 수업 전에 재발급 일정을 잡으세요."
        else:
            expiry_status = "valid"
            severity = "ok"
            action = "정상입니다."

        summary["total"] += 1
        summary["configured" if configured else "missing"] += 1
        if expiry_status in summary and expiry_status != "missing":
            summary[expiry_status] += 1
        row = {
            "key_name": key,
            "label": key_labels.get(key, key),
            "configured": configured,
            "value_source": value_source,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "expires_at_raw": str(expires_at_raw) if expires_at_raw not in (None, "") else None,
            "days_remaining": days_remaining,
            "expiry_status": expiry_status,
            "severity": severity,
            "issuer": entry.get("issuer"),
            "account": entry.get("account"),
            "renewal_url": entry.get("renewal_url"),
            "notes": entry.get("notes"),
            "usages": key_usages.get(key, []),
            "action": action,
        }
        keys.append(row)
        if severity in {"attention", "blocked"}:
            alerts.append(
                {
                    "severity": severity,
                    "key_name": key,
                    "message": f"{key_labels.get(key, key)}: {action}",
                    "expires_at": row["expires_at"],
                    "days_remaining": days_remaining,
                }
            )

    return {
        "secret_configured": secret_configured,
        "secret_name": settings.stat_api_keys_secret if secret_configured else "",
        "warning_days": warning_days,
        "summary": summary,
        "alerts": alerts,
        "keys": keys,
        "secret_error": secret_error,
    }
