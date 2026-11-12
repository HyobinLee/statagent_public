import math
import os
from typing import Any

import httpx
from app.core.errors import AppError
from app.services.secrets import get_stat_api_secret_bundle

from lessons_app.services.connector_cache import display_url, read_cache, write_cache

GG_BASE_URL = "https://openapi.gg.go.kr"
DEFAULT_TIMEOUT_SECONDS = 15.0
SERVICE_NAME_ENV = "GG_LIBRARY_SERVICE_NAME"
DEFAULT_SERVICE_NAME = "Schoollibrrydatahold"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
}
_MAX_PAGES_WALK = 12


def _credential(key: str) -> str:
    return os.getenv(key, "") or get_stat_api_secret_bundle().get(key, "")


def _get_page(service_name: str, key: str, p_index: int, p_size: int) -> tuple[list[dict], int, dict[str, Any]]:
    url = f"{GG_BASE_URL}/{service_name}"
    params: dict[str, Any] = {"KEY": key, "Type": "json", "pIndex": p_index, "pSize": p_size}
    cache_payload = {"endpoint": service_name, "pIndex": p_index, "pSize": p_size}
    cached = read_cache("gg_library_page", cache_payload)
    if cached is not None:
        return cached["rows"], int(cached["total"]), params
    try:
        response = httpx.get(url, params=params, headers=REQUEST_HEADERS, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        raise AppError(
            "GG_LIBRARY_UNAVAILABLE",
            "경기 학교도서관 현황 정보를 불러오지 못했습니다.",
            "잠시 후 다시 시도하거나 탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc
    except ValueError as exc:
        raise AppError(
            "GG_LIBRARY_UNAVAILABLE",
            "경기 학교도서관 현황 응답을 읽을 수 없습니다.",
            "탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc
    rows, total = _extract_rows(body, service_name)
    write_cache("gg_library_page", cache_payload, {"rows": rows, "total": total})
    return rows, total, params


def fetch_school_library(*, p_size: int = 1000) -> dict[str, Any]:
    service_name = _credential(SERVICE_NAME_ENV).strip() or DEFAULT_SERVICE_NAME

    key = _credential("GG_API_KEY")
    if not key:
        raise AppError(
            "GG_API_KEY_MISSING",
            "경기데이터드림 인증키(GG_API_KEY)가 설정되어 있지 않습니다.",
            "Secret Manager 또는 환경변수에 GG_API_KEY를 설정해 주세요.",
            503,
        )

    _, total_count, _ = _get_page(service_name, key, 1, 1)
    last_page = max(1, math.ceil(max(total_count, 1) / p_size))

    latest_rows: list[dict] = []
    latest_year = ""
    request_params: dict[str, Any] = {"KEY": key, "Type": "json"}
    for offset in range(_MAX_PAGES_WALK):
        p_index = last_page - offset
        if p_index < 1:
            break
        rows, _, params = _get_page(service_name, key, p_index, p_size)
        if offset == 0:
            request_params = params
            latest_year = max((str(row.get("STD_YY", "")) for row in rows), default="")
        page_latest = [row for row in rows if str(row.get("STD_YY", "")) == latest_year]
        if not page_latest:
            break
        latest_rows = page_latest + latest_rows

    usable = [
        row
        for row in latest_rows
        if row.get("ALL_STDNT_CNT") and row.get("DATA_CNT_SUM") and str(row.get("EXCLSN_YN", "N")) != "Y"
    ]
    if not usable:
        raise AppError(
            "GG_LIBRARY_UNEXPECTED_SHAPE",
            "경기 학교도서관 현황에서 최신 연도 행을 찾지 못했습니다.",
            "탑재된 대체 자료로 진행하고, 관리자에게 응답 구조 확인을 요청해 주세요.",
            502,
        )

    request_url = display_url(f"{GG_BASE_URL}/{service_name}", request_params)
    return {"request_url": request_url, "rows": usable, "std_yy": latest_year, "from_cache": False}


def _extract_rows(body: dict, service_name: str) -> tuple[list[dict], int]:
    root = body.get(service_name)
    if not isinstance(root, list) or len(root) < 2:
        raise AppError(
            "GG_LIBRARY_UNEXPECTED_SHAPE",
            "경기 학교도서관 현황 응답 형식이 예상과 다릅니다.",
            "탑재된 대체 자료로 진행하고, 관리자에게 엔드포인트 확인을 요청해 주세요.",
            502,
        )
    head_block = root[0].get("head") if isinstance(root[0], dict) else None
    total = 0
    if isinstance(head_block, list):
        for item in head_block:
            if isinstance(item, dict) and "list_total_count" in item:
                total = int(item["list_total_count"])
                break
    rows_block = root[1]
    rows = rows_block.get("row") if isinstance(rows_block, dict) else None
    if not isinstance(rows, list):
        raise AppError(
            "GG_LIBRARY_UNEXPECTED_SHAPE",
            "경기 학교도서관 현황 응답에서 행을 찾을 수 없습니다.",
            "탑재된 대체 자료로 진행하고, 관리자에게 엔드포인트 확인을 요청해 주세요.",
            502,
        )
    return rows, total
