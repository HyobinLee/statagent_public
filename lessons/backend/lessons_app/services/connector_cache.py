import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from app.config import get_settings
from app.repositories.factory import get_repository

_CACHE_MAX_PAYLOAD_BYTES = 900_000


def _cache_key(namespace: str, payload: dict[str, Any]) -> str:
    safe_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(safe_payload.encode("utf-8")).hexdigest()[:24]
    return f"connector_cache:{namespace}:{digest}"


def read_cache(namespace: str, payload: dict[str, Any]) -> dict | None:
    item = get_repository().get_setting(_cache_key(namespace, payload))
    if not item:
        return None
    value = item.get("value", {})
    if not isinstance(value, dict):
        return None
    expires_at = value.get("expires_at")
    if not expires_at:
        return None
    try:
        if datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) < datetime.now(UTC):
            return None
    except ValueError:
        return None
    data = value.get("data")
    return data if isinstance(data, dict) else None


def display_url(url: str, params: dict[str, Any], *, secret_params: tuple[str, ...] = ("KEY",)) -> str:
    placeholder = "MASKEDSECRET"
    masked = {key: (placeholder if key in secret_params and value else value) for key, value in params.items()}
    return str(httpx.Request("GET", url, params=masked).url).replace(placeholder, "***")


def write_cache(namespace: str, payload: dict[str, Any], data: dict, ttl_seconds: int | None = None) -> None:
    encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(encoded) > _CACHE_MAX_PAYLOAD_BYTES:
        return
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().stat_api_cache_ttl_seconds
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    get_repository().upsert_setting(
        _cache_key(namespace, payload),
        {
            "namespace": namespace,
            "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "data": data,
        },
    )
