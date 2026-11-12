import os
from typing import Any

import httpx
from app.core.errors import AppError
from app.services.kosis_service import _loads_kosis_payload
from app.services.secrets import get_kosis_api_key

from lessons_app.services.connector_cache import display_url, read_cache, write_cache

KOSIS_PARAM_DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG_ID = "101"
TBL_ID = "DT_1PE401"
FIXED_YEAR = "2025"
DEFAULT_TIMEOUT_SECONDS = 15.0
CACHE_NAMESPACE = "kosis_private_edu"

SCHOOL_LEVELS = ("초등학교", "중학교", "고등학교")
BRACKETS = {
    "사교육받지않음": "① 받지 않음(0원)",
    "20만원미만": "② 20만원 미만",
    "20~30만원미만": "③ 20~30만원 미만",
    "30~40만원미만": "④ 30~40만원 미만",
    "40~50만원미만": "⑤ 40~50만원 미만",
    "50~60만원미만": "⑥ 50~60만원 미만",
    "60~70만원미만": "⑦ 60~70만원 미만",
    "70~100만원미만": "⑧ 70~100만원 미만",
    "100만원이상": "⑨ 100만원 이상",
}


def _api_key() -> str:
    return os.getenv("KOSIS_API_KEY", "") or get_kosis_api_key()


def _normalize_item(name: Any) -> str:
    text = str(name or "").strip()
    if text.startswith("-"):
        text = text[1:]
    return "".join(text.split())


def _parse_rate(value: Any) -> float | None:
    try:
        return round(float(str(value).replace(",", "").strip()), 1)
    except (TypeError, ValueError):
        return None


def shape_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: dict[tuple[str, str], float] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        prd_de = str(row.get("PRD_DE", FIXED_YEAR) or FIXED_YEAR).strip()
        if prd_de != FIXED_YEAR:
            continue
        school = str(row.get("C1_NM", "")).strip()
        bracket = BRACKETS.get(_normalize_item(row.get("ITM_NM")))
        if school not in SCHOOL_LEVELS or bracket is None:
            continue
        rate = _parse_rate(row.get("DT"))
        if rate is None:
            continue
        values.setdefault((school, bracket), rate)

    shaped = [
        {"학교급": school, "구간": bracket, "비율": values[(school, bracket)]}
        for school in SCHOOL_LEVELS
        for bracket in BRACKETS.values()
        if (school, bracket) in values
    ]
    if len(shaped) != len(SCHOOL_LEVELS) * len(BRACKETS):
        raise AppError(
            "KOSIS_PRIVATE_EDU_UNEXPECTED_SHAPE",
            "KOSIS 사교육비 분포 응답에서 학교급별 구간 값을 모두 찾지 못했습니다.",
            "탑재된 대체 자료로 진행하고, 관리자에게 통계표 구조 확인을 요청해 주세요.",
            502,
        )
    return shaped


def _request_params(key: str) -> dict[str, Any]:
    return {
        "method": "getList",
        "apiKey": key,
        "format": "json",
        "jsonVD": "Y",
        "orgId": ORG_ID,
        "tblId": TBL_ID,
        "itmId": "ALL",
        "objL1": "ALL",
        "prdSe": "Y",
        "startPrdDe": FIXED_YEAR,
        "endPrdDe": FIXED_YEAR,
    }


def fetch_private_edu_distribution() -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise AppError(
            "KOSIS_API_KEY_MISSING",
            "KOSIS 인증키(KOSIS_API_KEY)가 설정되어 있지 않습니다.",
            "Secret Manager 또는 환경변수에 KOSIS_API_KEY를 설정해 주세요.",
            503,
        )
    params = _request_params(key)
    request_url = display_url(KOSIS_PARAM_DATA_URL, params, secret_params=("apiKey",))

    cache_payload = {"tblId": TBL_ID, "year": FIXED_YEAR}
    cached = read_cache(CACHE_NAMESPACE, cache_payload)
    if cached is not None:
        return {"request_url": request_url, "rows": cached["rows"], "from_cache": True}

    try:
        response = httpx.get(KOSIS_PARAM_DATA_URL, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = _loads_kosis_payload(response.text)
    except httpx.HTTPError as exc:
        raise AppError(
            "KOSIS_PRIVATE_EDU_UNAVAILABLE",
            "KOSIS 사교육비 통계표를 불러오지 못했습니다.",
            "잠시 후 다시 시도하거나 탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc
    except ValueError as exc:
        raise AppError(
            "KOSIS_PRIVATE_EDU_UNAVAILABLE",
            "KOSIS 사교육비 통계표 응답을 읽을 수 없습니다.",
            "탑재된 대체 자료로 진행해 주세요.",
            502,
        ) from exc

    if isinstance(body, dict):
        if body.get("err"):
            raise AppError(
                "KOSIS_PRIVATE_EDU_UNAVAILABLE",
                "KOSIS가 오류 응답을 돌려주었습니다.",
                str(body.get("errMsg") or body.get("err"))[:300],
                502,
            )
        body = [body]
    rows = shape_rows(body if isinstance(body, list) else [])
    write_cache(CACHE_NAMESPACE, cache_payload, {"rows": rows})
    return {"request_url": request_url, "rows": rows, "from_cache": False}
