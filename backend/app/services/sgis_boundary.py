from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.core.errors import AppError
from app.services.korea_tm import utmk_to_lonlat
from app.services.region_codes import region_name_to_code
from app.services.secrets import get_stat_api_secret_bundle

SGIS_AUTH_URL = "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json"
SGIS_BOUNDARY_URL = "https://sgisapi.kostat.go.kr/OpenAPI3/boundary/hadmarea.geojson"
BOUNDARY_CACHE_DIR = "sgis_boundaries"
TOKEN_EXPIRY_MARGIN_SECONDS = 60

LEVELS = ("sido", "sigungu", "emd")
LEVEL_LABELS = {"sido": "시도", "sigungu": "시군구", "emd": "읍면동"}
PARENT_LEVEL = {"sigungu": "sido", "emd": "sigungu"}

_token_cache: tuple[str, float] | None = None


def _credential(key: str) -> str:
    value = os.getenv(key, "")
    if value:
        return value
    try:
        return get_stat_api_secret_bundle().get(key, "")
    except AppError:
        return ""


def sgis_configured() -> bool:
    return bool(_credential("SGIS_SERVICE_ID") and _credential("SGIS_SECURITY_KEY"))


def boundaries_enabled() -> bool:
    return bool(get_settings().enable_sgis_boundaries) and sgis_configured()


def _cache_path(level: str, parent_code: str | None) -> Path:
    name = f"{level}_{parent_code or 'all'}_{get_settings().sgis_boundary_year}.json"
    return get_settings().local_data_dir / BOUNDARY_CACHE_DIR / name


def _access_token(client: httpx.Client) -> str:
    global _token_cache
    if _token_cache and _token_cache[1] > time.time():
        return _token_cache[0]
    response = client.get(
        SGIS_AUTH_URL,
        params={
            "consumer_key": _credential("SGIS_SERVICE_ID"),
            "consumer_secret": _credential("SGIS_SECURITY_KEY"),
        },
    )
    response.raise_for_status()
    result = response.json().get("result") or {}
    token = result.get("accessToken")
    if not token:
        raise httpx.HTTPError("SGIS 인증 응답에 accessToken이 없습니다.")
    try:
        expires_at = float(result.get("accessTimeout", 0)) / 1000 - TOKEN_EXPIRY_MARGIN_SECONDS
    except (TypeError, ValueError):
        expires_at = 0.0
    _token_cache = (token, expires_at)
    return token


def _rings_from_geometry(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    if kind == "Polygon":
        polygons = [geometry.get("coordinates") or []]
    elif kind == "MultiPolygon":
        polygons = geometry.get("coordinates") or []
    else:
        return []

    rings: list[list[tuple[float, float]]] = []
    for polygon in polygons:
        if not polygon:
            continue
        outer = polygon[0]
        ring = [utmk_to_lonlat(float(point[0]), float(point[1])) for point in outer if len(point) >= 2]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def _parse_feature_collection(payload: dict[str, Any], level: str) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        properties = feature.get("properties") or {}
        full_name = str(properties.get("adm_nm") or "").strip()
        if not full_name:
            continue
        rings = _rings_from_geometry(feature.get("geometry") or {})
        if not rings:
            continue
        record: dict[str, Any] = {
            "sgis_code": str(properties.get("adm_cd") or ""),
            "name": full_name,
            "short_name": full_name.split()[-1],
            "rings": rings,
        }
        if level == "sido":
            record["region_code"] = region_name_to_code(full_name)
        try:
            record["lng"], record["lat"] = utmk_to_lonlat(float(properties["x"]), float(properties["y"]))
        except (KeyError, TypeError, ValueError):
            record["lng"] = record["lat"] = None
        regions.append(record)
    return regions


def _read_cache(level: str, parent_code: str | None) -> list[dict[str, Any]] | None:
    path = _cache_path(level, parent_code)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for record in raw:
        record["rings"] = [[(float(point[0]), float(point[1])) for point in ring] for ring in record.get("rings", [])]
    return raw


def _write_cache(level: str, parent_code: str | None, regions: list[dict[str, Any]]) -> None:
    path = _cache_path(level, parent_code)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(regions), encoding="utf-8")
    except OSError:
        pass


def fetch_regions(level: str, parent_code: str | None = None) -> list[dict[str, Any]] | None:
    if level not in LEVELS or not boundaries_enabled():
        return None
    if PARENT_LEVEL.get(level) and not parent_code:
        return None

    cached = _read_cache(level, parent_code)
    if cached:
        return cached

    settings = get_settings()
    params: dict[str, Any] = {"year": settings.sgis_boundary_year}
    if parent_code:
        params["adm_cd"] = parent_code
        params["low_search"] = "1"
    try:
        with httpx.Client(timeout=settings.sgis_timeout_seconds, follow_redirects=True) as client:
            token = _access_token(client)
            response = client.get(SGIS_BOUNDARY_URL, params={"accessToken": token, **params})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, OSError):
        return None

    regions = _parse_feature_collection(payload, level)
    if not regions:
        return None
    _write_cache(level, parent_code, regions)
    return regions


def sido_sgis_code(name: str) -> str | None:
    target = region_name_to_code(name)
    if not target:
        return None
    for record in fetch_regions("sido") or []:
        if record.get("region_code") == target:
            return record["sgis_code"]
    return None


def sigungu_sgis_code(sido_name: str, sigungu_name: str) -> str | None:
    parent = sido_sgis_code(sido_name)
    if not parent:
        return None
    wanted = str(sigungu_name or "").replace(" ", "")
    for record in fetch_regions("sigungu", parent) or []:
        if wanted in {record["short_name"], record["name"].replace(" ", "")}:
            return record["sgis_code"]
    return None


def fetch_sido_boundaries() -> dict[str, list[list[tuple[float, float]]]] | None:
    regions = fetch_regions("sido")
    if not regions:
        return None
    return {record["region_code"]: record["rings"] for record in regions if record.get("region_code")}
