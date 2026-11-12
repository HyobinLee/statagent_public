import os
from typing import Any

import httpx
from app.core.errors import AppError
from app.services.secrets import get_stat_api_secret_bundle

from lessons_app.services.connector_cache import display_url, read_cache, write_cache

NEIS_MEAL_URL = "https://open.neis.go.kr/hub/mealServiceDietInfo"
NEIS_SCHOOL_URL = "https://open.neis.go.kr/hub/schoolInfo"
DEFAULT_TIMEOUT_SECONDS = 15.0
NEIS_NO_DATA_CODES = {"INFO-200"}


def _credential(key: str) -> str:
    return os.getenv(key, "") or get_stat_api_secret_bundle().get(key, "")


def _get_json(url: str, params: dict[str, Any], *, error_code: str, error_message: str) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise AppError(
            error_code,
            error_message,
            "잠시 후 다시 시도하거나 탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc
    except ValueError as exc:
        raise AppError(
            error_code,
            f"{error_message} (응답을 읽을 수 없음)",
            "잠시 후 다시 시도하거나 탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc


def fetch_meal_service(
    *,
    atpt_ofcdc_sc_code: str,
    sd_schul_code: str,
    mlsv_from_ymd: str,
    mlsv_to_ymd: str,
    mmeal_sc_code: str = "2",
    p_size: int = 1000,
) -> dict[str, Any]:
    cache_payload = {
        "endpoint": "mealServiceDietInfo",
        "atpt": atpt_ofcdc_sc_code,
        "school": sd_schul_code,
        "from": mlsv_from_ymd,
        "to": mlsv_to_ymd,
        "meal": mmeal_sc_code,
    }
    cached = read_cache("neis_meal", cache_payload)
    if cached is not None:
        return {**cached, "from_cache": True}

    params: dict[str, Any] = {
        "Type": "json",
        "pIndex": 1,
        "pSize": p_size,
        "ATPT_OFCDC_SC_CODE": atpt_ofcdc_sc_code,
        "SD_SCHUL_CODE": sd_schul_code,
        "MLSV_FROM_YMD": mlsv_from_ymd,
        "MLSV_TO_YMD": mlsv_to_ymd,
        "MMEAL_SC_CODE": mmeal_sc_code,
    }
    key = _credential("NEIS_API_KEY")
    if key:
        params["KEY"] = key

    body = _get_json(
        NEIS_MEAL_URL,
        params,
        error_code="NEIS_MEAL_UNAVAILABLE",
        error_message="NEIS 급식 정보를 불러오지 못했습니다.",
    )

    root = body.get("mealServiceDietInfo")
    request_url = display_url(NEIS_MEAL_URL, params)
    if not root:
        code = body.get("RESULT", {}).get("CODE", "")
        if code in NEIS_NO_DATA_CODES:
            raise AppError(
                "NEIS_MEAL_NO_DATA",
                "해당 학교·기간에는 급식 정보가 없습니다(방학·휴업일일 수 있습니다).",
                "기간을 조정하거나 탑재된 대체 자료로 진행해 주세요.",
                404,
                {"neis_code": code, "request_url": request_url},
            )
        raise AppError(
            "NEIS_MEAL_ERROR",
            body.get("RESULT", {}).get("MESSAGE", "NEIS 급식 정보 조회에 실패했습니다."),
            "요청 조건을 확인하거나 탑재된 대체 자료로 진행해 주세요.",
            502,
            {"neis_code": code, "request_url": request_url},
        )

    head_block, rows_block = root[0], (root[1] if len(root) > 1 else {"row": []})
    total_count = head_block.get("head", [{}])[0].get("list_total_count", 0)
    rows = rows_block.get("row", [])

    result = {"request_url": request_url, "total_count": total_count, "rows": rows}
    write_cache("neis_meal", cache_payload, result)
    return {**result, "from_cache": False}
