from __future__ import annotations

import re
from typing import Any

SIDO_REGIONS: list[dict[str, Any]] = [
    {"code": "11", "name": "서울특별시", "short": "서울", "lat": 37.5665, "lng": 126.9780},
    {"code": "26", "name": "부산광역시", "short": "부산", "lat": 35.1796, "lng": 129.0756},
    {"code": "27", "name": "대구광역시", "short": "대구", "lat": 35.8714, "lng": 128.6014},
    {"code": "28", "name": "인천광역시", "short": "인천", "lat": 37.4563, "lng": 126.7052},
    {"code": "29", "name": "광주광역시", "short": "광주", "lat": 35.1595, "lng": 126.8526},
    {"code": "30", "name": "대전광역시", "short": "대전", "lat": 36.3504, "lng": 127.3845},
    {"code": "31", "name": "울산광역시", "short": "울산", "lat": 35.5384, "lng": 129.3114},
    {"code": "36", "name": "세종특별자치시", "short": "세종", "lat": 36.4800, "lng": 127.0000},
    {"code": "41", "name": "경기도", "short": "경기", "lat": 37.4138, "lng": 127.5183},
    {"code": "42", "name": "강원도", "short": "강원", "lat": 37.8228, "lng": 128.1555},
    {"code": "43", "name": "충청북도", "short": "충북", "lat": 36.6358, "lng": 127.4913},
    {"code": "44", "name": "충청남도", "short": "충남", "lat": 36.5184, "lng": 126.8000},
    {"code": "45", "name": "전라북도", "short": "전북", "lat": 35.7175, "lng": 127.1530},
    {"code": "46", "name": "전라남도", "short": "전남", "lat": 34.8679, "lng": 126.9910},
    {"code": "47", "name": "경상북도", "short": "경북", "lat": 36.4919, "lng": 128.8889},
    {"code": "48", "name": "경상남도", "short": "경남", "lat": 35.4606, "lng": 128.2132},
    {"code": "50", "name": "제주특별자치도", "short": "제주", "lat": 33.4890, "lng": 126.4983},
]

_REGION_ALIASES: dict[str, str] = {}
for _r in SIDO_REGIONS:
    _REGION_ALIASES[_r["name"]] = _r["code"]
    _REGION_ALIASES[_r["short"]] = _r["code"]
    _REGION_ALIASES[_r["name"].replace("특별자치", "")] = _r["code"]

_REGION_ALIASES.update(
    {
        "강원특별자치도": "42",
        "전북특별자치도": "45",
        "전라북특별자치도": "45",
    }
)

_WHITESPACE = re.compile(r"\s+")


def _normalize_for_lookup(name: str) -> str:
    return _WHITESPACE.sub("", str(name or "")).strip()


def region_name_to_code(name: str) -> str | None:
    normalized = _normalize_for_lookup(name)
    if normalized in _REGION_ALIASES:
        return _REGION_ALIASES[normalized]
    for alias, code in _REGION_ALIASES.items():
        if alias in normalized or normalized in alias:
            return code
    return None


def region_info(code: str | None) -> dict[str, Any] | None:
    return next((region for region in SIDO_REGIONS if region["code"] == code), None) if code else None
