from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, unquote

import httpx

from app.config import get_settings
from app.core.errors import AppError
from app.models.stat_api import (
    CandidateDataset,
    CsvFetchResult,
    DatasetAccessInfo,
    DatasetFetchRequest,
    DatasetMetadata,
    PreferredPeriod,
    ResearchQuestionContext,
    StatApiSource,
)
from app.repositories.factory import get_repository
from app.services.secrets import build_stat_api_key_status, get_stat_api_secret_bundle


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    display_name: str
    provider: str
    category: str
    enabled_env: str
    enabled_default: bool
    required_env_keys: tuple[str, ...]
    auth_required: bool
    supports_search: bool
    supports_fetch: bool
    supports_csv_export: bool
    manual_download_url: str
    docs_url: str
    default_access_status_when_disabled: str
    student_friendly_use_cases: tuple[str, ...]
    cautions: tuple[str, ...]


SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        "public_data_catalog",
        "공공데이터포털 목록조회서비스",
        "공공데이터활용지원센터",
        "catalog",
        "PUBLIC_DATA_CATALOG_ENABLED",
        True,
        ("DATA_GO_KR_SERVICE_KEY",),
        True,
        True,
        False,
        False,
        "https://www.data.go.kr/",
        "https://www.data.go.kr/data/15077093/openapi.do",
        "FOUND_BUT_UNSUPPORTED",
        ("공공 API와 파일데이터 후보 찾기",),
        ("검색 결과가 곧 자동 수집 가능하다는 뜻은 아닙니다.",),
    ),
    SourceDefinition(
        "ecos",
        "한국은행 ECOS",
        "한국은행",
        "economy",
        "ECOS_ENABLED",
        True,
        ("ECOS_API_KEY",),
        True,
        True,
        True,
        True,
        "https://ecos.bok.or.kr/",
        "https://ecos.bok.or.kr/api/",
        "MANUAL_CSV_AVAILABLE",
        ("물가", "금리", "환율", "소비심리", "경제성장률"),
        ("경제 지표 간 관계를 인과로 단정하지 마세요.",),
    ),
    SourceDefinition(
        "index_nuri",
        "지표누리",
        "국가지표통합",
        "national_indicator",
        "INDEX_NURI_ENABLED",
        True,
        ("INDEX_GO_KR_IDNTFC_ID",),
        True,
        True,
        True,
        True,
        "https://www.index.go.kr/",
        "https://www.index.go.kr/unity/openApi/openApiIntro.do",
        "MANUAL_CSV_AVAILABLE",
        ("삶의 질", "SDG", "저출생", "고용", "사회 지표"),
        ("지표 정의와 단위를 반드시 표시하세요.",),
    ),
    SourceDefinition(
        "sgis",
        "SGIS 통계지리정보서비스",
        "통계청/SGIS",
        "spatial",
        "SGIS_ENABLED",
        True,
        ("SGIS_SERVICE_ID", "SGIS_SECURITY_KEY"),
        True,
        True,
        True,
        True,
        "https://link.mods.go.kr/",
        "https://link.mods.go.kr/developer/html/newOpenApi/api/dataApi/ready.html",
        "MANUAL_CSV_AVAILABLE",
        ("지역별 인구", "가구", "사업체", "생활업종", "지도 기반 탐구"),
        ("행정구역 코드와 기준연도를 함께 저장해야 합니다.",),
    ),
    SourceDefinition(
        "kma_asos_hourly",
        "기상청 ASOS 시간자료",
        "기상청 / 공공데이터포털",
        "weather",
        "KMA_ASOS_HOURLY_ENABLED",
        True,
        ("DATA_GO_KR_SERVICE_KEY",),
        True,
        False,
        True,
        True,
        "https://data.kma.go.kr/",
        "https://www.data.go.kr/data/15057210/openapi.do",
        "MANUAL_CSV_AVAILABLE",
        ("기온", "강수량", "습도", "풍속", "날씨와 대기질 관계"),
        ("관측 지점과 관측 기간을 명확히 표시하세요.",),
    ),
    SourceDefinition(
        "kma_asos_daily",
        "기상청 ASOS 일자료",
        "기상청 / 공공데이터포털",
        "weather",
        "KMA_ASOS_DAILY_ENABLED",
        True,
        ("DATA_GO_KR_SERVICE_KEY",),
        True,
        False,
        True,
        True,
        "https://data.kma.go.kr/",
        "https://www.data.go.kr/",
        "MANUAL_CSV_AVAILABLE",
        ("일평균 기온", "월별 기상 변화", "계절 비교"),
        ("시간자료보다 학생 분석에는 일자료가 쉬울 수 있습니다.",),
    ),
    SourceDefinition(
        "airkorea",
        "에어코리아 대기오염정보",
        "한국환경공단 / 공공데이터포털",
        "air_quality",
        "AIRKOREA_ENABLED",
        True,
        ("DATA_GO_KR_SERVICE_KEY",),
        True,
        False,
        True,
        True,
        "https://www.airkorea.or.kr/",
        "https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15073861",
        "MANUAL_CSV_AVAILABLE",
        ("미세먼지", "초미세먼지", "오존", "대기질 예보", "지역별 대기질"),
        ("실시간 자료는 변동성이 크므로 기간을 정해 저장 후 분석하세요.",),
    ),
    SourceDefinition(
        "neis",
        "NEIS 교육정보 개방 포털",
        "교육부/NEIS",
        "education",
        "NEIS_ENABLED",
        True,
        ("NEIS_API_KEY",),
        True,
        True,
        True,
        True,
        "https://open.neis.go.kr/",
        "https://open.neis.go.kr/portal/guide/apiGuidePage.do",
        "MANUAL_CSV_AVAILABLE",
        ("학교 기본정보", "급식", "학사일정", "지역별 학교 정보"),
        ("학교를 서열화하거나 낙인찍는 표현을 피하세요.",),
    ),
    SourceDefinition(
        "schoolinfo",
        "학교알리미 공시정보",
        "한국교육학술정보원",
        "education",
        "SCHOOLINFO_ENABLED",
        True,
        ("SCHOOLINFO_API_KEY",),
        True,
        True,
        True,
        True,
        "https://www.schoolinfo.go.kr/",
        "https://www.data.go.kr/data/15098092/openapi.do",
        "MANUAL_CSV_AVAILABLE",
        ("학생·교원현황", "시설", "교육여건", "재정", "급식", "학업성취 공시"),
        ("개별 학교 비교는 맥락을 충분히 설명하고 순위화 표현을 피하세요.",),
    ),
    SourceDefinition(
        "its",
        "국가교통정보센터 실시간 교통정보",
        "국토교통부/ITS",
        "transport",
        "ITS_ENABLED",
        True,
        ("ITS_API_KEY",),
        True,
        True,
        True,
        True,
        "https://www.its.go.kr/opendata/",
        "https://www.its.go.kr/opendata/opendataList",
        "MANUAL_CSV_AVAILABLE",
        ("도로 구간 통행속도", "시간대별 교통 흐름", "공사·통제 등 돌발 상황"),
        (
            "실시간 자료라 호출 시점의 값만 남습니다. 시간대 비교를 하려면 같은 구간을 여러 번 나눠 저장하세요.",
            "속도가 느린 구간을 곧바로 '위험한 도로'로 해석하지 마세요.",
        ),
    ),
    SourceDefinition(
        "taas",
        "TAAS 교통사고 다발지역·통계",
        "한국도로교통공단",
        "transport",
        "TAAS_ENABLED",
        True,
        ("TAAS_API_KEY",),
        True,
        True,
        True,
        True,
        "https://taas.koroad.or.kr/",
        "https://opendata.koroad.or.kr/api/",
        "MANUAL_CSV_AVAILABLE",
        (
            "보행자 교통사고 다발지점",
            "어린이보호구역 사고",
            "지역별 사고 건수·사망자수 비교",
            "사고 다발지점 지도",
        ),
        (
            "사고 자료는 피해자가 있는 기록입니다. 특정 지역이나 집단을 탓하는 표현을 쓰지 마세요.",
            "사고건수는 통행량이 많은 곳에서 커지므로, 건수만으로 위험도를 단정할 수 없습니다.",
        ),
    ),
    SourceDefinition(
        "world_bank",
        "World Bank Indicators",
        "World Bank",
        "international",
        "WORLD_BANK_ENABLED",
        True,
        (),
        False,
        True,
        True,
        True,
        "https://data.worldbank.org/indicator",
        "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation",
        "MANUAL_CSV_AVAILABLE",
        ("국가별 인구", "GDP", "인터넷 이용률", "교육", "보건", "환경 국제 비교"),
        ("국가 단위 자료이므로 개인 또는 지역 수준 원인으로 해석하지 마세요.",),
    ),
    SourceDefinition(
        "oecd",
        "OECD Data API",
        "OECD",
        "international",
        "OECD_ENABLED",
        True,
        (),
        False,
        True,
        True,
        True,
        "https://data-explorer.oecd.org/",
        "https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html",
        "MANUAL_CSV_AVAILABLE",
        ("OECD 국가 비교", "교육", "청년 고용", "경제", "삶의 질"),
        ("SDMX 구조가 복잡하므로 metadata/structure query를 먼저 확인해야 합니다.",),
    ),
)

WORLD_BANK_INDICATORS: tuple[dict[str, Any], ...] = (
    {
        "indicator_id": "IT.NET.USER.ZS",
        "title": "Individuals using the Internet (% of population)",
        "keywords": ("인터넷", "internet", "디지털", "온라인", "정보"),
        "unit": "%",
        "measures": ("인터넷 이용률",),
    },
    {
        "indicator_id": "NY.GDP.PCAP.CD",
        "title": "GDP per capita (current US$)",
        "keywords": ("gdp", "국내총생산", "소득", "경제", "1인당", "일인당"),
        "unit": "current US$",
        "measures": ("1인당 GDP",),
    },
    {
        "indicator_id": "SP.POP.TOTL",
        "title": "Population, total",
        "keywords": ("인구", "population", "국가", "세계"),
        "unit": "people",
        "measures": ("총인구",),
    },
    {
        "indicator_id": "SL.UEM.1524.ZS",
        "title": "Unemployment, youth total (% of total labor force ages 15-24)",
        "keywords": ("청년", "실업", "고용", "unemployment", "youth"),
        "unit": "%",
        "measures": ("청년 실업률",),
    },
    {
        "indicator_id": "SP.DYN.TFRT.IN",
        "title": "Fertility rate, total (births per woman)",
        "keywords": ("출산", "출생", "저출생", "fertility"),
        "unit": "births per woman",
        "measures": ("합계출산율",),
    },
    {
        "indicator_id": "EN.ATM.CO2E.PC",
        "title": "CO2 emissions (metric tons per capita)",
        "keywords": ("co2", "탄소", "배출", "환경", "기후"),
        "unit": "metric tons per capita",
        "measures": ("1인당 CO2 배출량",),
    },
    {
        "indicator_id": "SH.XPD.CHEX.PC.CD",
        "title": "Current health expenditure per capita (current US$)",
        "keywords": ("보건", "의료", "건강", "health"),
        "unit": "current US$",
        "measures": ("1인당 보건 지출",),
    },
)

CACHE_MAX_PAYLOAD_BYTES = 900_000

ITS_BASE_URL = "https://openapi.its.go.kr:9443"
ITS_MAX_BBOX_DEGREES = 1.0
ITS_DEFAULT_BBOX = {"minX": 126.90, "maxX": 127.10, "minY": 37.50, "maxY": 37.60}
ITS_DATASETS: tuple[dict[str, Any], ...] = (
    {
        "dataset_id": "trafficInfo",
        "title": "실시간 소통정보(구간 통행속도)",
        "unit": "km/h",
        "measures": ("구간 통행속도", "구간 통행시간"),
        "keywords": ("교통", "소통", "속도", "정체", "도로", "통행", "출근", "퇴근"),
        "extra_params": {"drcType": "all"},
    },
    {
        "dataset_id": "eventInfo",
        "title": "돌발정보(사고·공사·통제)",
        "unit": "건",
        "measures": ("돌발 건수",),
        "keywords": ("돌발", "사고", "공사", "통제", "교통", "도로"),
        "extra_params": {"eventType": "all"},
    },
)

TAAS_BASE_URL = "https://opendata.koroad.or.kr/data/rest"
TAAS_DATASETS: tuple[dict[str, Any], ...] = (
    {
        "dataset_id": "frequentzone/pedstrians",
        "title": "보행자 교통사고 다발지역",
        "approved": True,
        "region_params": ("siDo", "guGun"),
        "region_required": True,
        "region_code_hint": "법정동 코드(시도 2자리, 시군구 3자리)",
        "keywords": ("보행", "보행자", "횡단보도", "교통사고", "사고", "다발지역", "걷기"),
        "measures": ("사고건수", "사상자수", "사망자수"),
        "detail_url": "https://opendata.koroad.or.kr/api/selectPedstriansDataSet.do",
    },
    {
        "dataset_id": "frequentzone/lg",
        "approved": True,
        "title": "지자체별 교통사고 다발지역",
        "region_params": ("siDo", "guGun"),
        "region_required": True,
        "region_code_hint": "법정동 코드(시도 2자리, 시군구 3자리)",
        "keywords": ("교통사고", "사고", "다발지역", "지역", "도로"),
        "measures": ("사고건수", "사상자수", "사망자수"),
        "detail_url": "https://opendata.koroad.or.kr/api/selectLgDataSet.do",
    },
    {
        "dataset_id": "frequentzone/schoolzone/child",
        "approved": True,
        "title": "어린이보호구역 어린이 교통사고 다발지역",
        "region_params": ("sido", "gugun"),
        "region_required": True,
        "region_code_hint": "법정동 코드(시도 2자리, 시군구 3자리)",
        "keywords": ("어린이", "보호구역", "스쿨존", "통학", "보행", "사고"),
        "measures": ("사고건수", "사상자수", "사망자수"),
        "detail_url": "https://opendata.koroad.or.kr/api/selectSchoolChildDataSet.do",
    },
    {
        "dataset_id": "stt",
        "approved": True,
        "title": "지자체별 교통사고 통계",
        "region_params": ("sido", "gugun"),
        "region_required": False,
        "region_code_hint": "KOROAD 지역 코드(시도 4자리 예: 1100, 시군구 4자리 예: 1102)",
        "keywords": ("교통사고", "통계", "지자체", "사망", "부상", "치사율"),
        "measures": ("사고건수", "사망자수", "부상자수", "치사율"),
        "detail_url": "https://opendata.koroad.or.kr/api/selectSttDataSet.do",
    },
)
TAAS_MEASURE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("occrrnc_cnt", "사고건수", "건"),
    ("acc_cnt", "사고건수", "건"),
    ("caslt_cnt", "사상자수", "명"),
    ("dth_dnv_cnt", "사망자수", "명"),
    ("se_dnv_cnt", "중상자수", "명"),
    ("sl_dnv_cnt", "경상자수", "명"),
    ("wnd_dnv_cnt", "부상신고자수", "명"),
    ("injpsn_cnt", "부상자수", "명"),
    ("ftlt_rate", "치사율", "%"),
    ("pop_100k", "인구 10만명당 사고건수", "건"),
    ("car_10k", "자동차 1만대당 사고건수", "건"),
)

SOURCE_BY_ID = {source.source_id: source for source in SOURCE_DEFINITIONS}
IMPLEMENTED_FETCH_SOURCES = {"world_bank", "ecos", "index_nuri", "sgis", "neis", "oecd", "schoolinfo", "its", "taas"}
PUBLIC_DATA_CATALOG_BASE_URL = "https://api.odcloud.kr/api/15077093/v1"
PUBLIC_DATA_CATALOG_SEARCH_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "kind": "dataset",
        "path": "dataset",
        "label": "공공데이터포털 데이터셋",
        "conditions": ("cond[title::LIKE]", "cond[keywords::LIKE]", "cond[desc::LIKE]"),
    },
    {
        "kind": "open_api",
        "path": "open-data-list",
        "label": "공공데이터포털 OpenAPI",
        "conditions": ("cond[title::LIKE]", "cond[list_title::LIKE]"),
    },
    {
        "kind": "standard",
        "path": "standard-data-list",
        "label": "공공데이터포털 표준데이터",
        "conditions": ("cond[title::LIKE]", "cond[keywords::LIKE]"),
    },
)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _cache_key(namespace: str, payload: dict[str, Any]) -> str:
    safe_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(safe_payload.encode("utf-8")).hexdigest()[:24]
    return f"stat_api_cache:{namespace}:{digest}"


class StatApiService:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.http_client = http_client
        self._secret_bundle_cache: dict[str, str] | None = None

    def _secret_values(self) -> dict[str, str]:
        if self._secret_bundle_cache is not None:
            return self._secret_bundle_cache
        try:
            self._secret_bundle_cache = get_stat_api_secret_bundle()
        except AppError:
            self._secret_bundle_cache = {}
        return self._secret_bundle_cache

    def _credential(self, key: str) -> str:
        return os.getenv(key, "") or self._secret_values().get(key, "")

    def source(self, source_id: str) -> SourceDefinition:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            raise AppError(
                "UNSUPPORTED_SOURCE",
                "지원하지 않는 통계 API 소스입니다.",
                "자료 소스 목록을 새로고침한 뒤 다시 선택해 주세요.",
                404,
                {"source_id": source_id},
            )
        return source

    def list_sources(self) -> list[dict]:
        return [self._source_payload(source) for source in SOURCE_DEFINITIONS]

    def stat_api_key_status(self) -> dict:
        expected_keys = sorted({key for source in SOURCE_DEFINITIONS for key in source.required_env_keys})
        key_usages: dict[str, list[str]] = {key: [] for key in expected_keys}
        for source in SOURCE_DEFINITIONS:
            for key in source.required_env_keys:
                if source.display_name not in key_usages[key]:
                    key_usages[key].append(source.display_name)
        return build_stat_api_key_status(
            expected_keys=expected_keys,
            key_usages=key_usages,
        )

    def _source_payload(self, source: SourceDefinition) -> dict:
        access_info = self.access_info(source.source_id)
        return StatApiSource(
            source_id=source.source_id,
            display_name=source.display_name,
            provider=source.provider,
            category=source.category,
            enabled_env=source.enabled_env,
            required_env_keys=list(source.required_env_keys),
            auth_required=source.auth_required,
            supports_search=source.supports_search,
            supports_fetch=source.supports_fetch,
            supports_csv_export=source.supports_csv_export,
            manual_download_url=source.manual_download_url,
            docs_url=source.docs_url,
            default_access_status_when_disabled=source.default_access_status_when_disabled,
            student_friendly_use_cases=list(source.student_friendly_use_cases),
            cautions=list(source.cautions),
            enabled=self._enabled(source),
            auth_configured=access_info.auth_configured,
        ).model_dump(mode="json") | {"access_info": access_info.model_dump(mode="json")}

    def _enabled(self, source: SourceDefinition) -> bool:
        if source.source_id == "schoolinfo" and _bool_env("SCHOOLINFO_MANUAL_ONLY", True):
            return False
        return _bool_env(source.enabled_env, source.enabled_default)

    def _public_data_catalog_access_info(self, source: SourceDefinition, *, auth_configured: bool) -> DatasetAccessInfo:
        return DatasetAccessInfo(
            source_id=source.source_id,
            backend_supported=auth_configured,
            auth_required=True,
            auth_configured=auth_configured,
            access_status="FOUND_BUT_UNSUPPORTED" if auth_configured else "SUPPORTED_BUT_KEY_MISSING",
            auto_fetch_available=False,
            manual_download_available=True,
            manual_download_url=source.manual_download_url,
            missing_env_keys=[] if auth_configured else list(source.required_env_keys),
            reason=(
                "공공데이터포털 목록 검색은 연결되어 있지만, "
                "개별 자료 자동 수집은 내부 커넥터가 확인된 경우에만 지원합니다."
                if auth_configured
                else "공공데이터포털 목록조회서비스를 호출하려면 DATA_GO_KR_SERVICE_KEY가 필요합니다."
            ),
        )

    def access_info(self, source_id: str) -> DatasetAccessInfo:
        source = self.source(source_id)
        enabled = self._enabled(source)
        missing_env_keys = [key for key in source.required_env_keys if not _clean_text(self._credential(key), 1_000)]
        auth_configured = not missing_env_keys
        manual_available = bool(source.manual_download_url)
        if not enabled:
            return DatasetAccessInfo(
                source_id=source.source_id,
                backend_supported=False,
                auth_required=source.auth_required,
                auth_configured=auth_configured,
                access_status=source.default_access_status_when_disabled,
                auto_fetch_available=False,
                manual_download_available=manual_available,
                manual_download_url=source.manual_download_url,
                missing_env_keys=missing_env_keys,
                reason="현재 서버 설정에서 자동 연동이 비활성화되어 수동 조회 경로만 안내합니다.",
            )
        if source.auth_required and not auth_configured:
            return DatasetAccessInfo(
                source_id=source.source_id,
                backend_supported=True,
                auth_required=True,
                auth_configured=False,
                access_status="SUPPORTED_BUT_KEY_MISSING",
                auto_fetch_available=False,
                manual_download_available=manual_available,
                manual_download_url=source.manual_download_url,
                missing_env_keys=missing_env_keys,
                reason="백엔드 커넥터는 준비되어 있지만 서버 인증키가 아직 설정되지 않았습니다.",
            )
        if source.source_id == "public_data_catalog":
            return self._public_data_catalog_access_info(source, auth_configured=auth_configured)
        if source.supports_fetch and source.supports_csv_export and source.source_id in IMPLEMENTED_FETCH_SOURCES:
            return DatasetAccessInfo(
                source_id=source.source_id,
                backend_supported=True,
                auth_required=source.auth_required,
                auth_configured=True,
                access_status="AUTO_SUPPORTED",
                auto_fetch_available=True,
                manual_download_available=manual_available,
                manual_download_url=source.manual_download_url,
                missing_env_keys=[],
                reason="자동 조회와 표준 CSV 변환을 지원합니다.",
            )
        if source.supports_fetch and source.supports_csv_export:
            return DatasetAccessInfo(
                source_id=source.source_id,
                backend_supported=False,
                auth_required=source.auth_required,
                auth_configured=auth_configured,
                access_status="MANUAL_CSV_AVAILABLE",
                auto_fetch_available=False,
                manual_download_available=manual_available,
                manual_download_url=source.manual_download_url,
                missing_env_keys=missing_env_keys,
                reason="공식 명세와 인증키를 확인하기 전까지 자동 수집을 열지 않고 수동 다운로드만 안내합니다.",
            )
        return DatasetAccessInfo(
            source_id=source.source_id,
            backend_supported=False,
            auth_required=source.auth_required,
            auth_configured=auth_configured,
            access_status="MANUAL_CSV_AVAILABLE",
            auto_fetch_available=False,
            manual_download_available=manual_available,
            manual_download_url=source.manual_download_url,
            missing_env_keys=missing_env_keys,
            reason="검색 또는 수동 조회 안내만 지원하며 자동 CSV 수집은 아직 지원하지 않습니다.",
        )

    def route_sources(
        self,
        *,
        research_question: str,
        grade_level: str = "unknown",
        source_ids: list[str] | None = None,
    ) -> dict:
        ctx = self._context(research_question, grade_level=grade_level)
        candidates = source_ids or self._heuristic_source_ids(ctx.question)
        sources = []
        for source_id in candidates:
            if source_id not in SOURCE_BY_ID:
                continue
            source = SOURCE_BY_ID[source_id]
            sources.append(
                {
                    "source_id": source_id,
                    "display_name": source.display_name,
                    "provider": source.provider,
                    "priority": len(sources) + 1,
                    "why_suitable": self._source_fit_reason(source, ctx.question),
                    "search_keywords": self._keywords_for_source(source, ctx.question),
                    "expected_api_task": "검색/메타데이터 확인/CSV 변환"
                    if source.supports_fetch
                    else "후보 검색과 수동 다운로드 안내",
                    "expected_csv_columns": [
                        "source_id",
                        "source_name",
                        "dataset_id",
                        "period",
                        "region",
                        "item",
                        "unit",
                        "value",
                    ],
                    "possible_analysis": self._analysis_suggestions(ctx.question),
                    "limitations": list(source.cautions),
                    "access_info": self.access_info(source_id).model_dump(mode="json"),
                }
            )
            if len(sources) >= 5:
                break
        return {
            "question_summary": _clean_text(research_question, 240),
            "data_need": {
                "main_variables": self._keyword_candidates(research_question)[:5],
                "dimensions": ctx.desired_dimensions,
                "analysis_type": ctx.analysis_types,
                "preferred_data_granularity": ctx.preferred_region or "자료 소스별 확인 필요",
            },
            "recommended_sources": sources,
            "fallback_plan": "자동 수집이 어렵다면 제공 사이트에서 CSV/XLS를 내려받아 앱의 CSV 업로드를 사용하세요.",
        }

    def search_datasets(
        self,
        *,
        research_question: str,
        grade_level: str = "unknown",
        source_ids: list[str] | None = None,
        keywords: list[str] | None = None,
        preferred_period: PreferredPeriod | None = None,
        preferred_region: str | None = None,
    ) -> dict:
        ctx = self._context(
            research_question,
            grade_level=grade_level,
            preferred_period=preferred_period,
            preferred_region=preferred_region,
        )
        search_source_ids = source_ids or [
            item["source_id"]
            for item in self.route_sources(research_question=research_question, grade_level=grade_level)[
                "recommended_sources"
            ]
        ]
        if source_ids is None and keywords:
            searchable_source_ids = [
                source.source_id for source in SOURCE_DEFINITIONS if source.supports_search and self._enabled(source)
            ]
            search_source_ids = self._merge_source_ids(search_source_ids, searchable_source_ids)
        normalized_keywords = self._normalized_search_keywords(research_question, keywords)
        candidates: list[CandidateDataset] = []
        for source_id in search_source_ids:
            if source_id == "world_bank":
                candidates.extend(self._world_bank_candidates(ctx, normalized_keywords))
            elif source_id == "public_data_catalog":
                candidates.extend(self._public_data_catalog_candidates(ctx, normalized_keywords))
            elif source_id == "its":
                candidates.extend(self._registry_candidates("its", ITS_DATASETS, ctx, normalized_keywords))
            elif source_id == "taas":
                candidates.extend(self._registry_candidates("taas", TAAS_DATASETS, ctx, normalized_keywords))
            elif source_id in SOURCE_BY_ID:
                candidates.extend(self._external_candidates(source_id, normalized_keywords, ctx))
        return {
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates[:18]],
            "metadata": {
                "searched_source_ids": search_source_ids,
                "keyword_count": len(normalized_keywords),
                "backend_registry_checked": True,
                "public_data_catalog_checked": "public_data_catalog" in search_source_ids,
            },
        }

    def fetch_csv(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        source = self.source(payload.source_id)
        access_info = self.access_info(source.source_id)
        if not access_info.auto_fetch_available:
            raise AppError(
                "STAT_API_AUTO_FETCH_UNAVAILABLE",
                "이 자료 소스는 현재 자동 CSV 가져오기를 사용할 수 없습니다.",
                access_info.reason,
                400,
                {"source_id": source.source_id, "access_status": access_info.access_status},
            )
        if source.source_id == "world_bank":
            return self._fetch_world_bank(payload)
        elif source.source_id == "ecos":
            return self._fetch_ecos(payload)
        elif source.source_id == "index_nuri":
            return self._fetch_index_nuri(payload)
        elif source.source_id == "sgis":
            return self._fetch_sgis(payload)
        elif source.source_id == "neis":
            return self._fetch_neis(payload)
        elif source.source_id == "oecd":
            return self._fetch_oecd(payload)
        elif source.source_id == "schoolinfo":
            return self._fetch_schoolinfo(payload)
        elif source.source_id == "its":
            return self._fetch_its(payload)
        elif source.source_id == "taas":
            return self._fetch_taas(payload)
        else:
            raise AppError(
                "STAT_API_CONNECTOR_NOT_IMPLEMENTED",
                "이 자료 소스의 자동 수집 커넥터는 아직 안전하게 열지 않았습니다.",
                "인증키와 공식 명세를 확인한 뒤 커넥터를 활성화해야 합니다.",
                501,
                {"source_id": source.source_id},
            )

    def manual_guide(self, source_id: str) -> dict:
        source = self.source(source_id)
        access_info = self.access_info(source_id)
        warnings = list(source.cautions)
        if source.category == "education":
            warnings.append(
                "학교별 자료는 특정 학교를 좋다/나쁘다로 평가하거나 순위를 매기는 방식으로 해석하지 않도록 주의하세요."
            )
        if source.category in {"air_quality", "weather"}:
            warnings.append(
                "이 자료는 공개 집계자료입니다. 특정 개인의 상태나 단일 원인을 단정하는 데 사용할 수 없습니다."
            )
        if source.category == "transport":
            warnings.append(
                "교통사고 자료에는 실제 피해자가 있습니다. 특정 지역이나 사람을 탓하는 표현 대신 "
                "안전 개선 방안을 찾는 방향으로 해석하세요."
            )
        return {
            "source_id": source.source_id,
            "display_name": source.display_name,
            "access_info": access_info.model_dump(mode="json"),
            "steps": [
                "제공 사이트를 엽니다.",
                "추천 검색어 또는 탐구 질문의 핵심 변수를 입력합니다.",
                "기간, 지역, 항목, 단위를 확인합니다.",
                "CSV 또는 XLS 파일로 내려받습니다.",
                "앱의 CSV 업로드에 파일을 넣고 분석 후보를 확인합니다.",
            ],
            "manual_download_url": source.manual_download_url,
            "docs_url": source.docs_url,
            "warnings": warnings,
        }

    def _merge_source_ids(self, *groups: list[str]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for source_id in group:
                if source_id in SOURCE_BY_ID and source_id not in merged:
                    merged.append(source_id)
        return merged

    def _normalized_search_keywords(self, research_question: str, keywords: list[str] | None) -> list[str]:
        raw: list[str] = []
        for keyword in keywords or []:
            text = _clean_text(keyword, 120)
            if text:
                raw.append(text)
                raw.extend(self._keyword_candidates(text))
        raw.extend(self._keyword_candidates(research_question))
        normalized: list[str] = []
        for keyword in raw:
            text = keyword.strip()
            if len(text) >= 2 and text not in normalized:
                normalized.append(text)
        return normalized[:8] or [_clean_text(research_question, 40)]

    def _public_data_catalog_candidates(
        self,
        ctx: ResearchQuestionContext,
        keywords: list[str],
    ) -> list[CandidateDataset]:
        access_info = self.access_info("public_data_catalog")
        if not access_info.auth_configured:
            return [self._manual_or_pending_candidate("public_data_catalog", keywords, ctx)]
        cache_payload = {
            "question": ctx.question,
            "keywords": keywords[:8],
            "grade_level": ctx.grade_level,
        }
        cached = self._read_cache("public_data_catalog_search", cache_payload)
        if cached and isinstance(cached.get("candidates"), list):
            return [CandidateDataset(**candidate) for candidate in cached["candidates"]]
        service_key = self._credential("DATA_GO_KR_SERVICE_KEY")
        if not service_key:
            return [self._manual_or_pending_candidate("public_data_catalog", keywords, ctx)]
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.settings.stat_api_request_timeout_ms / 1000)
        candidates: list[CandidateDataset] = []
        seen: set[str] = set()
        try:
            for target in PUBLIC_DATA_CATALOG_SEARCH_TARGETS:
                for condition in target["conditions"]:
                    for keyword in keywords[:4]:
                        params = {
                            "page": 1,
                            "perPage": 5,
                            "returnType": "JSON",
                            condition: keyword,
                        }
                        response = client.get(
                            f"{PUBLIC_DATA_CATALOG_BASE_URL}/{target['path']}",
                            params=params,
                            headers={"Authorization": f"Infuser {service_key}"},
                        )
                        response.raise_for_status()
                        payload = response.json()
                        for row in payload.get("data", []) if isinstance(payload, dict) else []:
                            if not isinstance(row, dict):
                                continue
                            candidate = self._public_data_row_to_candidate(
                                row,
                                kind=target["kind"],
                                type_label=target["label"],
                                keywords=keywords,
                                ctx=ctx,
                            )
                            key = f"{candidate.source_id}:{candidate.dataset_id}:{candidate.dataset_title}"
                            if key in seen:
                                continue
                            seen.add(key)
                            candidates.append(candidate)
                            if len(candidates) >= 8:
                                break
                        if len(candidates) >= 8:
                            break
                    if len(candidates) >= 8:
                        break
                if len(candidates) >= 8:
                    break
        except (httpx.HTTPError, ValueError) as exc:
            fallback = self._manual_or_pending_candidate("public_data_catalog", keywords, ctx)
            fallback.description = (
                f"공공데이터포털 목록조회서비스 호출이 실패했습니다. 직접 검색할 검색어 후보: {', '.join(keywords[:4])}"
            )
            fallback.raw = {"catalog_error": _clean_text(exc, 240), "search_keywords": keywords[:5]}
            return [fallback]
        finally:
            if close_client:
                client.close()
        if not candidates:
            return [self._manual_or_pending_candidate("public_data_catalog", keywords, ctx)]
        self._write_cache(
            "public_data_catalog_search",
            cache_payload,
            {"candidates": [candidate.model_dump(mode="json") for candidate in candidates]},
        )
        return candidates

    def _public_data_row_to_candidate(
        self,
        row: dict[str, Any],
        *,
        kind: str,
        type_label: str,
        keywords: list[str],
        ctx: ResearchQuestionContext,
    ) -> CandidateDataset:
        source_id = self._match_public_data_source(row) or "public_data_catalog"
        base_access = self.access_info(source_id)
        row_url = _clean_text(
            row.get("page_url") or row.get("guide_url") or row.get("meta_url") or row.get("link_url") or "",
            500,
        )
        title = _clean_text(row.get("title") or row.get("list_title") or "공공데이터포털 자료 후보", 240)
        dataset_id = _clean_text(
            row.get("id") or row.get("list_id") or hashlib.sha1(title.encode("utf-8")).hexdigest()[:10], 120
        )
        description = _clean_text(row.get("desc") or row.get("keywords") or row.get("list_title") or "", 700)
        access_status = base_access.access_status
        reason = base_access.reason
        if kind in {"dataset", "standard"} and not base_access.auto_fetch_available:
            access_status = "MANUAL_CSV_AVAILABLE"
            reason = (
                "공공데이터포털에서 실제 후보를 찾았습니다. "
                "파일 또는 표준데이터는 내려받은 뒤 CSV 업로드로 사용할 수 있습니다."
            )
        if kind == "open_api" and source_id == "public_data_catalog":
            access_status = "FOUND_BUT_UNSUPPORTED"
            reason = "공공데이터포털 OpenAPI 후보는 찾았지만 현재 앱의 자동 CSV 커넥터와 아직 매칭되지 않았습니다."
        access_info = base_access.model_copy(
            update={
                "access_status": access_status,
                "manual_download_available": bool(row_url or base_access.manual_download_url),
                "manual_download_url": row_url or base_access.manual_download_url,
                "reason": reason,
            }
        )
        category = _clean_text(row.get("new_category_nm") or row.get("category_nm") or "", 120)
        data_format = _clean_text(
            row.get("data_format") or row.get("ext") or row.get("data_type") or row.get("list_type") or type_label, 120
        )
        measures = self._unique_strings([*keywords[:4], row.get("keywords"), title, row.get("core_data_nm")])
        return CandidateDataset(
            candidate_id=f"public_data_catalog:{kind}:{dataset_id}",
            source_id=source_id,
            provider=_clean_text(row.get("org_nm") or SOURCE_BY_ID["public_data_catalog"].provider, 160),
            dataset_id=dataset_id,
            dataset_title=title,
            description=description or f"{type_label}에서 확인된 자료 후보입니다.",
            docs_url=row_url or SOURCE_BY_ID["public_data_catalog"].docs_url,
            manual_download_url=row_url or SOURCE_BY_ID["public_data_catalog"].manual_download_url,
            api_detail_url=_clean_text(row.get("operation_url") or row.get("end_point_url") or "", 500) or None,
            available_dimensions=self._unique_strings([*ctx.desired_dimensions, category, data_format]),
            available_measures=measures,
            period_range=ctx.preferred_period,
            unit="자료별 확인 필요",
            license=_clean_text(
                row.get("share_scope_nm") or row.get("use_prmisn_ennc") or "제공기관 이용조건 확인 필요", 160
            ),
            access_info=access_info,
            cautions=[
                *SOURCE_BY_ID["public_data_catalog"].cautions,
                "공공데이터포털 검색 결과는 목록 메타데이터입니다. "
                "분석 전 실제 파일/API의 항목, 기간, 단위를 확인하세요.",
            ],
            raw={
                "catalog_source_id": "public_data_catalog",
                "catalog_type": kind,
                "matched_source_id": source_id if source_id != "public_data_catalog" else None,
                "search_keywords": keywords[:5],
                "row": self._compact_public_data_row(row),
            },
        )

    def _match_public_data_source(self, row: dict[str, Any]) -> str | None:
        text = " ".join(str(value or "") for value in row.values()).lower()
        if any(token in text for token in ("airkorea", "에어코리아", "대기오염", "미세먼지", "한국환경공단")):
            return "airkorea"
        if any(token in text for token in ("asos", "종관기상", "기상청")):
            return "kma_asos_hourly" if any(token in text for token in ("시간", "hour")) else "kma_asos_daily"
        if any(token in text for token in ("학교알리미", "schoolinfo")):
            return "schoolinfo"
        if any(token in text for token in ("neis", "교육정보", "나이스")):
            return "neis"
        if any(token in text for token in ("지표누리", "e-나라", "국가지표")):
            return "index_nuri"
        if any(token in text for token in ("sgis", "통계지리")):
            return "sgis"
        if any(token in text for token in ("ecos", "한국은행")):
            return "ecos"
        return None

    def _compact_public_data_row(self, row: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "id",
            "list_id",
            "title",
            "list_title",
            "org_nm",
            "category_nm",
            "new_category_nm",
            "keywords",
            "data_format",
            "ext",
            "page_url",
            "guide_url",
            "meta_url",
            "updated_at",
            "created_at",
        ]
        return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}

    def _unique_strings(self, values: list[Any]) -> list[str]:
        unique: list[str] = []
        for value in values:
            if isinstance(value, list):
                iterable = value
            else:
                iterable = [value]
            for item in iterable:
                text = _clean_text(item, 120)
                if text and text not in unique:
                    unique.append(text)
        return unique[:8]

    def _context(
        self,
        question: str,
        *,
        grade_level: str = "unknown",
        preferred_period: PreferredPeriod | None = None,
        preferred_region: str | None = None,
    ) -> ResearchQuestionContext:
        lowered = question.lower()
        analysis_types = []
        if any(token in question for token in ("변화", "추세", "늘", "줄", "시간", "연도")):
            analysis_types.append("change")
        if any(token in question for token in ("관계", "관련", "함께", "영향")):
            analysis_types.append("relationship")
        if any(token in question for token in ("지역", "국가", "나라", "학교", "비교", "차이")):
            analysis_types.append("comparison")
        if not analysis_types:
            analysis_types.append("comparison")
        dimensions = []
        if any(token in question for token in ("연도", "시간", "월", "일", "계절")):
            dimensions.append("기간")
        if any(token in question for token in ("지역", "시도", "도시")):
            dimensions.append("지역")
        if any(token in lowered for token in ("국가", "나라", "oecd", "세계")):
            dimensions.append("국가")
        if "학교" in question:
            dimensions.append("학교")
        return ResearchQuestionContext(
            question=question,
            grade_level=grade_level if grade_level in {"middle", "high", "middle_high"} else "unknown",
            analysis_types=analysis_types,
            desired_dimensions=dimensions or ["기간", "지역 또는 집단"],
            desired_measures=self._keyword_candidates(question)[:5],
            preferred_period=preferred_period,
            preferred_region=preferred_region,
        )

    def _heuristic_source_ids(self, question: str) -> list[str]:
        lowered = question.lower()
        scored: list[str] = []

        def add(source_id: str) -> None:
            if source_id not in scored:
                scored.append(source_id)

        if any(token in question for token in ("미세먼지", "초미세먼지", "오존", "대기")):
            add("airkorea")
            add("kma_asos_daily")
        if any(token in question for token in ("기온", "날씨", "강수", "폭염", "습도")):
            add("kma_asos_daily")
            add("airkorea")
        if any(token in question for token in ("학교", "급식", "학사", "교육")):
            add("neis")
            add("schoolinfo")
        if any(token in question for token in ("물가", "금리", "환율", "소비", "경제")):
            add("ecos")
            add("world_bank")
        if any(token in lowered for token in ("국가", "나라", "세계", "oecd", "gdp", "인터넷")):
            add("world_bank")
            add("oecd")
        if any(token in question for token in ("지표", "삶", "저출생", "고용", "sdg")):
            add("index_nuri")
            add("world_bank")
        if any(token in question for token in ("인구", "가구", "사업체", "생활업종", "지도")):
            add("sgis")
            add("index_nuri")
        if any(token in question for token in ("교통사고", "사고", "보호구역", "스쿨존", "횡단보도", "보행")):
            add("taas")
            add("its")
        if any(token in question for token in ("교통", "도로", "정체", "통행", "속도", "출퇴근")):
            add("its")
            add("taas")
        add("public_data_catalog")
        add("world_bank")
        return scored[:5]

    def _keyword_candidates(self, question: str) -> list[str]:
        tokens = []
        for token in question.replace("?", " ").replace(",", " ").split():
            clean = token.strip("은는이가을를와과에의로부터보다어떻게까")
            if len(clean) >= 2 and clean not in tokens:
                tokens.append(clean)
        return tokens or [_clean_text(question, 40)]

    def _keywords_for_source(self, source: SourceDefinition, question: str) -> list[str]:
        base = self._keyword_candidates(question)
        return (base + list(source.student_friendly_use_cases))[:5]

    def _source_fit_reason(self, source: SourceDefinition, question: str) -> str:
        use_cases = ", ".join(source.student_friendly_use_cases[:3])
        return f"'{_clean_text(question, 80)}' 질문과 관련해 {use_cases} 자료를 찾을 수 있는 소스입니다."

    def _analysis_suggestions(self, question: str) -> list[str]:
        lowered = question.lower()
        suggestions = ["막대그래프 또는 선그래프로 비교"]
        if any(token in question for token in ("관계", "관련", "함께")):
            suggestions.append("산점도와 상관계수")
        if any(token in question for token in ("변화", "추세", "연도", "시간")):
            suggestions.append("시계열 변화 분석")
        if "분포" in question:
            suggestions.append("히스토그램과 요약 통계")
        if "oecd" in lowered or "국가" in question:
            suggestions.append("국가별 비교")
        return suggestions[:4]

    def _world_bank_candidates(
        self,
        ctx: ResearchQuestionContext,
        keywords: list[str],
    ) -> list[CandidateDataset]:
        text = " ".join([ctx.question, *keywords]).lower()
        matched = [
            indicator
            for indicator in WORLD_BANK_INDICATORS
            if any(keyword.lower() in text for keyword in indicator["keywords"])
        ]
        if not matched:
            matched = list(WORLD_BANK_INDICATORS[:3])
        access_info = self.access_info("world_bank")
        return [
            CandidateDataset(
                candidate_id=f"world_bank:{indicator['indicator_id']}",
                source_id="world_bank",
                provider="World Bank",
                dataset_id=indicator["indicator_id"],
                dataset_title=indicator["title"],
                description="World Bank Indicators API에서 국가별·연도별로 조회할 수 있는 공개 지표입니다.",
                docs_url=SOURCE_BY_ID["world_bank"].docs_url,
                manual_download_url=f"https://data.worldbank.org/indicator/{indicator['indicator_id']}",
                api_detail_url=f"https://api.worldbank.org/v2/country/KOR/indicator/{indicator['indicator_id']}?format=json",
                available_dimensions=["country", "period"],
                available_measures=list(indicator["measures"]),
                period_range=ctx.preferred_period or PreferredPeriod(start="1960", end=str(datetime.now(UTC).year)),
                unit=indicator["unit"],
                license="World Bank Open Data Terms of Use",
                access_info=access_info,
                cautions=list(SOURCE_BY_ID["world_bank"].cautions),
                raw={"indicator_id": indicator["indicator_id"]},
            )
            for indicator in matched[:5]
        ]

    def _registry_candidates(
        self,
        source_id: str,
        registry: tuple[dict[str, Any], ...],
        ctx: ResearchQuestionContext,
        keywords: list[str],
    ) -> list[CandidateDataset]:
        text = " ".join([ctx.question, *keywords]).lower()
        available = [item for item in registry if item.get("approved", True)]
        matched = [item for item in available if any(keyword.lower() in text for keyword in item["keywords"])]
        if not matched:
            matched = available
        source = self.source(source_id)
        access_info = self.access_info(source_id)
        return [
            CandidateDataset(
                candidate_id=f"{source_id}:{item['dataset_id']}",
                source_id=source_id,
                provider=source.provider,
                dataset_id=item["dataset_id"],
                dataset_title=item["title"],
                description=f"{source.display_name}에서 제공하는 공개 API 자료입니다.",
                docs_url=source.docs_url,
                manual_download_url=source.manual_download_url,
                api_detail_url=item.get("detail_url"),
                available_dimensions=ctx.desired_dimensions,
                available_measures=list(item.get("measures", ())),
                period_range=ctx.preferred_period,
                unit=item.get("unit", "자료별 확인 필요"),
                license="제공 기관 이용조건 확인 필요",
                access_info=access_info,
                cautions=list(source.cautions),
                raw={"dataset_id": item["dataset_id"]},
            )
            for item in matched[:5]
        ]

    def _manual_or_pending_candidate(
        self,
        source_id: str,
        keywords: list[str],
        ctx: ResearchQuestionContext,
    ) -> CandidateDataset:
        source = self.source(source_id)
        access_info = self.access_info(source_id)
        status_title = {
            "SUPPORTED_BUT_KEY_MISSING": "인증키 설정 후 자동 수집 가능",
            "MANUAL_CSV_AVAILABLE": "직접 다운로드 후 업로드 권장",
            "FOUND_BUT_UNSUPPORTED": "현재 자동 수집 미지원",
            "API_ONLY_UNSUPPORTED": "관리자 연동 필요",
            "AUTO_SUPPORTED": "자동 수집 커넥터 준비 중",
            "NO_GOOD_PUBLIC_DATA": "적합한 공개자료 부족",
        }.get(access_info.access_status, "자료 후보")
        cautions = list(source.cautions)
        if source.category == "education":
            cautions.append("학교별 자료는 학교 맥락을 충분히 설명하고 순위화 표현을 피해야 합니다.")
        if source.category in {"weather", "air_quality"}:
            cautions.append("공개 집계자료이므로 특정 원인을 단정하지 않도록 주의하세요.")
        return CandidateDataset(
            candidate_id=f"{source_id}:manual:{hashlib.sha1(' '.join(keywords).encode('utf-8')).hexdigest()[:8]}",
            source_id=source_id,
            provider=source.provider,
            dataset_id=f"{source_id}:manual-search",
            dataset_title=f"{source.display_name} 자료 검색",
            description=f"{status_title}. 검색어 후보: {', '.join(keywords[:4]) or _clean_text(ctx.question, 60)}",
            docs_url=source.docs_url,
            manual_download_url=source.manual_download_url,
            available_dimensions=ctx.desired_dimensions,
            available_measures=list(source.student_friendly_use_cases),
            period_range=ctx.preferred_period,
            unit="자료별 확인 필요",
            license="제공 기관 이용조건 확인 필요",
            access_info=access_info,
            cautions=cautions,
            raw={"search_keywords": keywords[:5]},
        )

    def _external_candidates(
        self,
        source_id: str,
        keywords: list[str],
        ctx: ResearchQuestionContext,
    ) -> list[CandidateDataset]:
        from app.services.ai_guide_service import get_guide_service

        fallback = [self._manual_or_pending_candidate(source_id, keywords, ctx)]
        recommend = getattr(get_guide_service(), "recommend_external_candidates", None)
        if not callable(recommend):
            return fallback
        try:
            recommendations = recommend(source_id, keywords[:5])
        except Exception:
            return fallback
        if not isinstance(recommendations, list):
            return fallback

        source = self.source(source_id)
        access_info = self.access_info(source_id)
        candidates: list[CandidateDataset] = []
        for item in recommendations[:3]:
            if not isinstance(item, dict):
                continue
            dataset_id = str(item.get("dataset_id") or "").strip()
            dataset_title = str(item.get("dataset_title") or "").strip()
            if not dataset_id or not dataset_title:
                continue
            candidates.append(
                CandidateDataset(
                    candidate_id=f"{source_id}:{dataset_id}",
                    source_id=source_id,
                    provider=source.provider,
                    dataset_id=dataset_id,
                    dataset_title=dataset_title,
                    description=str(item.get("description") or "").strip() or None,
                    docs_url=source.docs_url,
                    manual_download_url=source.manual_download_url,
                    available_dimensions=ctx.desired_dimensions,
                    available_measures=list(source.student_friendly_use_cases),
                    period_range=ctx.preferred_period,
                    unit="자료별 확인 필요",
                    license="제공 기관 이용조건 확인 필요",
                    access_info=access_info,
                    cautions=[*source.cautions, "AI가 추론한 통계표 코드이므로 실제로 열리는지 먼저 확인하세요."],
                    raw={"search_keywords": keywords[:5], "ai_suggested": True},
                )
            )
        return candidates or fallback

    def _fetch_world_bank(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        indicator_id = payload.indicator_id or payload.dataset_id
        countries = payload.country_codes or ["KOR"]
        start_year = payload.start_period or "2010"
        end_year = payload.end_period or str(datetime.now(UTC).year)
        cache_payload = {
            "source_id": "world_bank",
            "indicator_id": indicator_id,
            "countries": countries,
            "start": start_year,
            "end": end_year,
        }
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)
        country_path = ";".join(quote(country.upper()) for country in countries)
        url = f"https://api.worldbank.org/v2/country/{country_path}/indicator/{quote(indicator_id)}"
        params = {
            "format": "json",
            "per_page": str(min(self.settings.stat_api_max_rows, 20000)),
            "date": f"{start_year}:{end_year}",
        }
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.settings.stat_api_request_timeout_ms / 1000)
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload_json = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR",
                "World Bank API 호출에 실패했습니다.",
                "잠시 후 다시 시도하거나 국가/기간/지표 코드를 줄여 주세요.",
                502,
                {"source_id": "world_bank"},
            ) from exc
        finally:
            if close_client:
                client.close()
        if not isinstance(payload_json, list) or len(payload_json) < 2 or not isinstance(payload_json[1], list):
            raise AppError(
                "STAT_API_RESPONSE_INVALID",
                "World Bank API 응답을 표 형태로 변환할 수 없습니다.",
                "지표 코드와 국가 코드를 확인해 주세요.",
                502,
                {"source_id": "world_bank"},
            )
        rows = payload_json[1]
        if len(rows) > self.settings.stat_api_max_rows:
            raise AppError(
                "STAT_API_TOO_MANY_ROWS",
                "요청한 자료의 양이 너무 많아 자동으로 가져올 수 없습니다.",
                "기간이나 국가 수를 줄여 다시 시도해 주세요.",
                400,
                {"row_count": len(rows), "max_rows": self.settings.stat_api_max_rows},
            )
        indicator_title = self._world_bank_indicator_title(indicator_id)
        normalized = []
        warnings: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            country = row.get("country") if isinstance(row.get("country"), dict) else {}
            indicator = row.get("indicator") if isinstance(row.get("indicator"), dict) else {}
            value = row.get("value")
            normalized.append(
                {
                    "source_id": "world_bank",
                    "source_name": "World Bank Indicators",
                    "provider": "World Bank",
                    "dataset_id": indicator.get("id") or indicator_id,
                    "dataset_title": indicator.get("value") or indicator_title,
                    "period": row.get("date"),
                    "region": country.get("value"),
                    "country_code": country.get("id"),
                    "item": indicator.get("value") or indicator_title,
                    "unit": self._world_bank_unit(indicator_id),
                    "value": value,
                    "note": row.get("obs_status") or "",
                }
            )
        if not normalized:
            raise AppError(
                "STAT_API_NO_ROWS",
                "선택한 조건에서 가져올 수 있는 행을 찾지 못했습니다.",
                "기간, 국가 코드, 지표 코드를 바꿔 다시 시도해 주세요.",
                404,
                {"source_id": "world_bank"},
            )
        if any(row["value"] is None for row in normalized):
            warnings.append("일부 연도 또는 국가는 결측값입니다. 분석 전 결측의 의미를 확인하세요.")
        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="world_bank",
            source_name="World Bank Indicators",
            provider="World Bank",
            dataset_id=indicator_id,
            dataset_title=indicator_title,
            fetched_at=_now_iso(),
            request_summary={
                "countries": countries,
                "start_period": start_year,
                "end_period": end_year,
                "indicator_id": indicator_id,
            },
            period_range=PreferredPeriod(start=start_year, end=end_year),
            unit=self._world_bank_unit(indicator_id),
            license="World Bank Open Data Terms of Use",
            notes=["World Bank 국가 단위 공개 지표입니다. 개인 또는 지역 수준 원인으로 단정하지 마세요."],
            original_docs_url=SOURCE_BY_ID["world_bank"].docs_url,
            original_data_url=f"https://data.worldbank.org/indicator/{indicator_id}",
        )
        result = CsvFetchResult(
            csv_filename=f"world_bank_{indicator_id}_{start_year}_{end_year}.csv".replace("/", "_"),
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=warnings,
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _fetch_ecos(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        api_key = self._credential("ECOS_API_KEY")
        stat_code = payload.indicator_id or payload.dataset_id
        start_year = payload.start_period or "2010"
        end_year = payload.end_period or str(datetime.now(UTC).year)
        cycle = "Y"
        item_code = "?"
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10000/{stat_code}/{cycle}/{start_year}/{end_year}/{item_code}"

        cache_payload = {"source_id": "ecos", "stat_code": stat_code, "start": start_year, "end": end_year}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=20.0)
        try:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR", "ECOS API 호출에 실패했습니다.", str(exc), 502, {"source_id": "ecos"}
            ) from exc
        finally:
            if close_client:
                client.close()

        if "StatisticSearch" not in data or "row" not in data["StatisticSearch"]:
            raise AppError(
                "STAT_API_RESPONSE_INVALID",
                "ECOS API 응답 변환 실패",
                f"지표 코드({stat_code})를 확인하세요. ECOS API 메시지: {data}",
                502,
                {"source_id": "ecos"},
            )

        rows = data["StatisticSearch"]["row"]
        normalized = []
        for row in rows:
            normalized.append(
                {
                    "source_id": "ecos",
                    "source_name": "한국은행 ECOS",
                    "provider": "한국은행",
                    "dataset_id": stat_code,
                    "dataset_title": row.get("STAT_NAME"),
                    "period": row.get("TIME"),
                    "item": row.get("ITEM_NAME1"),
                    "value": row.get("DATA_VALUE"),
                    "unit": "",
                    "note": "",
                }
            )

        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="ecos",
            source_name="한국은행 ECOS",
            provider="한국은행",
            dataset_id=stat_code,
            dataset_title=rows[0].get("STAT_NAME") if rows else stat_code,
            fetched_at=_now_iso(),
            request_summary={"stat_code": stat_code, "start_period": start_year, "end_period": end_year},
            period_range=PreferredPeriod(start=start_year, end=end_year),
            original_data_url="https://ecos.bok.or.kr/",
        )
        result = CsvFetchResult(
            csv_filename=f"ecos_{stat_code}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=[],
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _fetch_index_nuri(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        raise AppError(
            "STAT_API_NOT_IMPLEMENTED_YET",
            "지표누리 자동 수집은 현재 KOSIS 연동으로 전환 중입니다.",
            "곧 지원될 예정입니다.",
            501,
            {},
        )

    def _fetch_sgis(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        service_id = self._credential("SGIS_SERVICE_ID")
        security_key = self._credential("SGIS_SECURITY_KEY")
        dataset_id = payload.indicator_id or payload.dataset_id

        auth_url = f"https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json?consumer_key={service_id}&consumer_secret={security_key}"

        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=20.0)
        try:
            auth_res = client.get(auth_url)
            auth_res.raise_for_status()
            auth_data = auth_res.json()
            access_token = auth_data["result"]["accessToken"]

            stat_url = f"https://sgisapi.kostat.go.kr/OpenAPI3/stats/{dataset_id}.json"
            params = {
                "accessToken": access_token,
                "year": payload.end_period or str(datetime.now(UTC).year - 1),
                "adm_cd": "11",
            }

            res = client.get(stat_url, params=params)
            res.raise_for_status()
            data = res.json()
        except Exception as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR", "SGIS API 호출에 실패했습니다.", str(exc), 502, {"source_id": "sgis"}
            ) from exc
        finally:
            if close_client:
                client.close()

        if "result" not in data:
            raise AppError("STAT_API_RESPONSE_INVALID", "SGIS 응답 오류", "데이터셋 ID를 확인하세요.", 502, {})

        rows = data["result"]
        normalized = []
        for row in rows:
            normalized.append(
                {
                    "source_id": "sgis",
                    "source_name": "SGIS 통계지리정보",
                    "provider": "통계청",
                    "dataset_id": dataset_id,
                    "dataset_title": dataset_id,
                    "period": params["year"],
                    "item": row.get("adm_nm", ""),
                    "value": row.get("population") or row.get("corp_cnt") or row.get("household_cnt") or str(row),
                    "unit": "",
                    "note": "",
                }
            )

        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="sgis",
            source_name="SGIS",
            provider="통계청",
            dataset_id=dataset_id,
            dataset_title=dataset_id,
            fetched_at=_now_iso(),
            request_summary={"dataset_id": dataset_id},
            period_range=PreferredPeriod(start=params["year"], end=params["year"]),
            original_data_url="https://sgis.kostat.go.kr/",
        )
        return CsvFetchResult(
            csv_filename=f"sgis_{dataset_id}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=[],
        )

    def _fetch_neis(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        api_key = self._credential("NEIS_API_KEY")
        dataset_id = payload.indicator_id or payload.dataset_id
        start_year = payload.start_period or "2010"
        end_year = payload.end_period or str(datetime.now(UTC).year)

        url = f"https://open.neis.go.kr/hub/{dataset_id}"
        params = {"KEY": api_key, "Type": "json", "pSize": 1000}

        cache_payload = {"source_id": "neis", "dataset_id": dataset_id}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=20.0)
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR", "NEIS API 호출에 실패했습니다.", str(exc), 502, {"source_id": "neis"}
            ) from exc
        finally:
            if close_client:
                client.close()

        if dataset_id not in data:
            raise AppError(
                "STAT_API_RESPONSE_INVALID",
                "NEIS API 응답 오류",
                f"데이터셋 ID({dataset_id})를 확인하세요.",
                502,
                {"source_id": "neis"},
            )

        rows = data[dataset_id][1].get("row", [])
        if not rows:
            raise AppError("STAT_API_NO_ROWS", "NEIS 조회 결과가 없습니다.", "", 404, {"source_id": "neis"})

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "source_id": "neis",
                    "source_name": "NEIS",
                    "provider": "교육부",
                    "dataset_id": dataset_id,
                    "dataset_title": dataset_id,
                    "period": row.get("YMD") or row.get("DATE") or "",
                    "item": list(row.values())[0] if row else "",
                    "value": str(row),
                    "unit": "",
                    "note": "",
                }
            )

        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="neis",
            source_name="NEIS 교육정보 개방 포털",
            provider="교육부/NEIS",
            dataset_id=dataset_id,
            dataset_title=dataset_id,
            fetched_at=_now_iso(),
            request_summary={"dataset_id": dataset_id},
            period_range=PreferredPeriod(start=start_year, end=end_year),
            original_data_url="https://open.neis.go.kr/",
        )
        result = CsvFetchResult(
            csv_filename=f"neis_{dataset_id}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=[
                "NEIS API 응답의 모든 키-값 쌍을 그대로 문자열로 저장했습니다. "
                "상세 분석을 위해 엑셀 등에서 정리해야 할 수 있습니다."
            ],
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _fetch_oecd(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        oecd_url = payload.dataset_id
        if not oecd_url.startswith("http"):
            raise AppError(
                "STAT_API_INVALID_OECD_URL",
                "올바른 OECD Developer API 주소가 아닙니다.",
                "팝업 안내에 따라 복사한 주소를 입력해 주세요.",
                400,
                {},
            )

        if "format=" not in oecd_url:
            if "?" in oecd_url:
                oecd_url += "&format=csvfilewithlabels"
            else:
                oecd_url += "?format=csvfilewithlabels"
        else:
            import re

            oecd_url = re.sub(r"format=[^&]+", "format=csvfilewithlabels", oecd_url)

        cache_payload = {"source_id": "oecd", "url": oecd_url}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=30.0)
        try:
            response = client.get(oecd_url)
            response.raise_for_status()
            csv_text = response.text
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR", "OECD API 호출에 실패했습니다.", str(exc), 502, {"source_id": "oecd"}
            ) from exc
        finally:
            if close_client:
                client.close()

        if not csv_text or len(csv_text.splitlines()) < 2:
            raise AppError(
                "STAT_API_NO_ROWS", "OECD 자료를 가져왔으나 데이터가 비어있습니다.", "", 404, {"source_id": "oecd"}
            )

        metadata = DatasetMetadata(
            source_id="oecd",
            source_name="OECD",
            provider="OECD",
            dataset_id="oecd_custom",
            dataset_title="OECD 직접 입력 자료",
            fetched_at=_now_iso(),
            request_summary={"url": oecd_url},
            period_range=PreferredPeriod(start=payload.start_period, end=payload.end_period),
            original_data_url="https://data-explorer.oecd.org/",
        )

        result = CsvFetchResult(
            csv_filename="oecd_data.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(csv_text.splitlines()) - 1,
            warnings=[
                "OECD SDMX API에서 가져온 원본 CSV 파일입니다. "
                "구조가 복잡할 수 있으므로 엑셀 등에서 정리 후 분석하세요."
            ],
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _fetch_schoolinfo(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        api_key = self._credential("SCHOOLINFO_API_KEY")
        dataset_id = payload.indicator_id or payload.dataset_id
        start_year = payload.start_period or "2010"
        end_year = payload.end_period or str(datetime.now(UTC).year)

        url = f"https://www.schoolinfo.go.kr/{dataset_id}"
        if not dataset_id.startswith("http") and not dataset_id.startswith("/"):
            url = f"https://www.schoolinfo.go.kr/openapi/{dataset_id}"

        params = {"KEY": api_key, "Type": "json", "pSize": 1000}

        cache_payload = {"source_id": "schoolinfo", "dataset_id": dataset_id}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=20.0)
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR",
                "학교알리미 API 호출에 실패했습니다.",
                str(exc),
                502,
                {"source_id": "schoolinfo"},
            ) from exc
        finally:
            if close_client:
                client.close()

        root_keys = [k for k in data.keys() if isinstance(data[k], list) and len(data[k]) > 1 and "row" in data[k][1]]
        if not root_keys:
            raise AppError(
                "STAT_API_RESPONSE_INVALID",
                "학교알리미 API 응답 오류",
                "데이터셋 ID를 확인하세요.",
                502,
                {"source_id": "schoolinfo"},
            )

        root_key = root_keys[0]
        rows = data[root_key][1].get("row", [])

        if not rows:
            raise AppError("STAT_API_NO_ROWS", "학교알리미 조회 결과가 없습니다.", "", 404, {"source_id": "schoolinfo"})

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "source_id": "schoolinfo",
                    "source_name": "학교알리미",
                    "provider": "한국교육학술정보원",
                    "dataset_id": dataset_id,
                    "dataset_title": root_key,
                    "period": row.get("SVY_YR") or str(datetime.now(UTC).year),
                    "item": row.get("SCHUL_NM") or list(row.values())[0],
                    "value": str(row),
                    "unit": "",
                    "note": "",
                }
            )

        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="schoolinfo",
            source_name="학교알리미 공시정보",
            provider="한국교육학술정보원",
            dataset_id=dataset_id,
            dataset_title=root_key,
            fetched_at=_now_iso(),
            request_summary={"dataset_id": dataset_id},
            period_range=PreferredPeriod(start=start_year, end=end_year),
            original_data_url="https://www.schoolinfo.go.kr/",
        )
        result = CsvFetchResult(
            csv_filename=f"schoolinfo_{dataset_id}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=["학교알리미 데이터의 모든 필드를 그대로 문자열로 저장했습니다."],
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _its_bbox(self, payload: DatasetFetchRequest) -> dict[str, float]:
        bbox: dict[str, float] = {}
        for name, default in ITS_DEFAULT_BBOX.items():
            raw = payload.raw_params.get(name, payload.dimensions.get(name, default))
            if isinstance(raw, list):
                raw = raw[0] if raw else default
            try:
                bbox[name] = float(str(raw))
            except (TypeError, ValueError) as exc:
                raise AppError(
                    "STAT_API_INVALID_BBOX",
                    f"교통정보 조회 범위 {name} 값이 숫자가 아닙니다.",
                    "지도에서 조회할 영역의 경도(minX, maxX)와 위도(minY, maxY)를 숫자로 입력해 주세요.",
                    400,
                    {"source_id": "its", "param": name},
                ) from exc
        if bbox["minX"] >= bbox["maxX"] or bbox["minY"] >= bbox["maxY"]:
            raise AppError(
                "STAT_API_INVALID_BBOX",
                "교통정보 조회 범위의 최소값이 최대값보다 큽니다.",
                "minX < maxX, minY < maxY가 되도록 좌표를 다시 입력해 주세요.",
                400,
                {"source_id": "its"},
            )
        if bbox["maxX"] - bbox["minX"] > ITS_MAX_BBOX_DEGREES or bbox["maxY"] - bbox["minY"] > ITS_MAX_BBOX_DEGREES:
            raise AppError(
                "STAT_API_BBOX_TOO_LARGE",
                "교통정보 조회 범위가 너무 넓습니다.",
                f"경도와 위도 폭을 각각 {ITS_MAX_BBOX_DEGREES}도(약 100km) 이내로 좁혀 주세요.",
                400,
                {"source_id": "its", "max_degrees": ITS_MAX_BBOX_DEGREES},
            )
        return bbox

    def _fetch_its(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        api_key = self._credential("ITS_API_KEY")
        dataset_id = payload.indicator_id or payload.dataset_id
        dataset = next((item for item in ITS_DATASETS if item["dataset_id"] == dataset_id), None)
        if not dataset:
            raise AppError(
                "STAT_API_UNSUPPORTED_DATASET",
                "지원하지 않는 국가교통정보센터 자료입니다.",
                f"사용할 수 있는 자료: {', '.join(item['dataset_id'] for item in ITS_DATASETS)}",
                400,
                {"source_id": "its", "dataset_id": dataset_id},
            )
        bbox = self._its_bbox(payload)
        cache_payload = {"source_id": "its", "dataset_id": dataset_id, **bbox}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        params = {
            "apiKey": api_key,
            "type": "all",
            "getType": "json",
            **dataset["extra_params"],
            **{name: f"{value:.6f}" for name, value in bbox.items()},
        }
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.settings.stat_api_request_timeout_ms / 1000)
        try:
            response = client.get(f"{ITS_BASE_URL}/{dataset_id}", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR",
                "국가교통정보센터 API 호출에 실패했습니다.",
                "잠시 후 다시 시도하거나 조회 범위를 좁혀 주세요.",
                502,
                {"source_id": "its"},
            ) from exc
        finally:
            if close_client:
                client.close()

        header = data.get("header", {}) if isinstance(data, dict) else {}
        if str(header.get("resultCode", "")) != "0":
            raise AppError(
                "STAT_API_UPSTREAM_REJECTED",
                "국가교통정보센터가 요청을 거절했습니다.",
                f"응답 메시지: {_clean_text(header.get('resultMsg'), 120)}. 인증키와 조회 범위를 확인해 주세요.",
                502,
                {"source_id": "its", "result_code": header.get("resultCode")},
            )
        body = data.get("body") if isinstance(data.get("body"), dict) else {}
        items = body.get("items") if isinstance(body.get("items"), list) else []
        if not items:
            raise AppError(
                "STAT_API_NO_ROWS",
                "선택한 범위에서 가져올 교통정보가 없습니다.",
                "조회 범위를 조금 넓히거나 다른 시간대에 다시 시도해 주세요.",
                404,
                {"source_id": "its", "dataset_id": dataset_id},
            )
        if len(items) > self.settings.stat_api_max_rows:
            raise AppError(
                "STAT_API_TOO_MANY_ROWS",
                "요청한 자료의 양이 너무 많아 자동으로 가져올 수 없습니다.",
                "지도에서 조회할 영역을 더 좁게 지정해 주세요.",
                400,
                {"row_count": len(items), "max_rows": self.settings.stat_api_max_rows},
            )

        fetched_at = _now_iso()
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if dataset_id == "trafficInfo":
                normalized.append(
                    {
                        "source_id": "its",
                        "source_name": "국가교통정보센터",
                        "provider": "국토교통부/ITS",
                        "dataset_id": dataset_id,
                        "dataset_title": dataset["title"],
                        "period": item.get("createdDate") or fetched_at,
                        "region": item.get("roadName"),
                        "item": "구간 통행속도",
                        "unit": "km/h",
                        "value": item.get("speed"),
                        "note": f"link_id={item.get('linkId')} travel_time_sec={item.get('travelTime')}",
                    }
                )
            else:
                normalized.append(
                    {
                        "source_id": "its",
                        "source_name": "국가교통정보센터",
                        "provider": "국토교통부/ITS",
                        "dataset_id": dataset_id,
                        "dataset_title": dataset["title"],
                        "period": item.get("startDate") or fetched_at,
                        "region": item.get("roadName"),
                        "item": _clean_text(item.get("eventType"), 40) or "돌발",
                        "unit": "건",
                        "value": 1,
                        "note": f"type={_clean_text(item.get('type'), 20)} link_id={item.get('linkId')}",
                    }
                )
        warnings = [
            "호출한 순간의 실시간 자료입니다. 시간대를 비교하려면 같은 범위를 여러 번 나눠 저장하세요.",
        ]
        if dataset_id == "eventInfo":
            warnings.append("행 하나가 돌발 상황 1건입니다. 도로별로 건수를 세어 비교하세요.")
        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="its",
            source_name="국가교통정보센터 실시간 교통정보",
            provider="국토교통부/ITS",
            dataset_id=dataset_id,
            dataset_title=dataset["title"],
            fetched_at=fetched_at,
            request_summary={"dataset_id": dataset_id, **bbox},
            period_range=PreferredPeriod(start=fetched_at, end=fetched_at),
            unit=dataset["unit"],
            license="국가교통정보센터 오픈API 이용약관 확인 필요",
            notes=["조회 범위 안의 도로 구간만 포함된 실시간 자료입니다."],
            original_docs_url=SOURCE_BY_ID["its"].docs_url,
            original_data_url="https://www.its.go.kr/opendata/",
        )
        result = CsvFetchResult(
            csv_filename=f"its_{dataset_id.lower()}_{fetched_at[:10]}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=warnings,
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _fetch_taas(self, payload: DatasetFetchRequest) -> CsvFetchResult:
        api_key = self._credential("TAAS_API_KEY")
        dataset_id = payload.indicator_id or payload.dataset_id
        dataset = next((item for item in TAAS_DATASETS if item["dataset_id"] == dataset_id), None)
        approved_ids = [item["dataset_id"] for item in TAAS_DATASETS if item.get("approved", True)]
        if not dataset:
            raise AppError(
                "STAT_API_UNSUPPORTED_DATASET",
                "지원하지 않는 TAAS 자료입니다.",
                f"사용할 수 있는 자료: {', '.join(approved_ids)}",
                400,
                {"source_id": "taas", "dataset_id": dataset_id},
            )
        if not dataset.get("approved", True):
            raise AppError(
                "STAT_API_DATASET_NOT_APPROVED",
                "이 TAAS 자료는 아직 인증키 활용 승인을 받지 않았습니다.",
                "KOROAD OpenAPI 포털에서 해당 API를 신청해 승인된 뒤 레지스트리의 approved 값을 바꿔 주세요. "
                f"지금 쓸 수 있는 자료: {', '.join(approved_ids)}",
                400,
                {"source_id": "taas", "dataset_id": dataset_id},
            )
        region_codes = payload.region_codes or []
        sido = str(region_codes[0]) if region_codes else str(payload.raw_params.get("sido", "") or "")
        gugun = str(region_codes[1]) if len(region_codes) > 1 else str(payload.raw_params.get("gugun", "") or "")
        if dataset["region_required"] and (not sido or not gugun):
            raise AppError(
                "STAT_API_REGION_REQUIRED",
                "이 TAAS 자료는 시도와 시군구 코드가 모두 필요합니다.",
                f"region_codes에 [시도코드, 시군구코드] 순서로 {dataset['region_code_hint']}를 넣어 주세요.",
                400,
                {"source_id": "taas", "dataset_id": dataset_id},
            )
        year = payload.start_period or payload.end_period or str(datetime.now(UTC).year - 2)
        page_size = min(self.settings.stat_api_max_rows, 1000)
        cache_payload = {"source_id": "taas", "dataset_id": dataset_id, "year": year, "sido": sido, "gugun": gugun}
        cached = self._read_cache("fetch", cache_payload)
        if cached:
            return CsvFetchResult(**cached)

        sido_param, gugun_param = dataset["region_params"]
        params = {
            "authKey": unquote(api_key),
            "searchYearCd": year,
            "type": "json",
            "numOfRows": str(page_size),
            "pageNo": "1",
        }
        params[sido_param] = sido
        params[gugun_param] = gugun
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.settings.stat_api_request_timeout_ms / 1000)
        try:
            response = client.get(f"{TAAS_BASE_URL}/{dataset_id}", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppError(
                "STAT_API_UPSTREAM_ERROR",
                "TAAS 교통사고분석시스템 API 호출에 실패했습니다.",
                "잠시 후 다시 시도하거나 연도와 지역 코드를 확인해 주세요.",
                502,
                {"source_id": "taas"},
            ) from exc
        finally:
            if close_client:
                client.close()

        if not isinstance(data, dict):
            raise AppError(
                "STAT_API_RESPONSE_INVALID",
                "TAAS API 응답을 표 형태로 변환할 수 없습니다.",
                "요청한 자료 종류와 지역 코드를 확인해 주세요.",
                502,
                {"source_id": "taas"},
            )
        result_code = str(data.get("resultCode", "")).lstrip("0") or "0"
        if result_code != "0":
            raise AppError(
                "STAT_API_UPSTREAM_REJECTED",
                "TAAS가 요청을 거절했습니다.",
                f"응답 메시지: {_clean_text(data.get('resultMsg'), 120)}. "
                "KOROAD OpenAPI 포털에서 해당 API에 인증키가 승인되었는지 확인해 주세요.",
                502,
                {"source_id": "taas", "result_code": data.get("resultCode")},
            )
        raw_items = data.get("items")
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("item", [])
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items = raw_items if isinstance(raw_items, list) else []
        if not items:
            raise AppError(
                "STAT_API_NO_ROWS",
                "선택한 조건에서 가져올 수 있는 행을 찾지 못했습니다.",
                "연도나 시군구 코드를 바꿔 다시 시도해 주세요.",
                404,
                {"source_id": "taas", "dataset_id": dataset_id},
            )

        warnings = [
            "행 하나가 '지점 × 항목' 한 쌍인 long 형식입니다. 항목별로 나눠 비교하세요.",
            "사고건수는 통행량에 크게 좌우되므로 건수만으로 위험도를 단정하지 마세요.",
        ]
        try:
            total_count = int(data.get("totalCount") or 0)
        except (TypeError, ValueError):
            total_count = 0
        if total_count > len(items):
            warnings.append(
                f"조건에 맞는 자료 {total_count}건 중 앞의 {len(items)}건만 가져왔습니다. "
                "지역이나 연도를 좁혀 다시 조회하세요."
            )

        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            region = _clean_text(item.get("spot_nm") or item.get("sido_sgg_nm"), 80)
            note_parts = [
                f"{name}={item[name]}"
                for name in ("afos_fid", "acc_cl_nm", "lo_crd", "la_crd")
                if item.get(name) not in (None, "")
            ]
            for field, label, unit in TAAS_MEASURE_FIELDS:
                if item.get(field) in (None, ""):
                    continue
                normalized.append(
                    {
                        "source_id": "taas",
                        "source_name": "TAAS 교통사고분석시스템",
                        "provider": "한국도로교통공단",
                        "dataset_id": dataset_id,
                        "dataset_title": dataset["title"],
                        "period": str(item.get("std_year") or year),
                        "region": region,
                        "item": label,
                        "unit": unit,
                        "value": item.get(field),
                        "note": " ".join(note_parts),
                    }
                )
        if not normalized:
            raise AppError(
                "STAT_API_NO_ROWS",
                "TAAS 응답에서 숫자로 된 통계 항목을 찾지 못했습니다.",
                "다른 자료 종류를 선택하거나 수동 다운로드를 이용해 주세요.",
                404,
                {"source_id": "taas", "dataset_id": dataset_id},
            )
        csv_text = self._rows_to_csv(normalized)
        metadata = DatasetMetadata(
            source_id="taas",
            source_name="TAAS 교통사고 다발지역·통계",
            provider="한국도로교통공단",
            dataset_id=dataset_id,
            dataset_title=dataset["title"],
            fetched_at=_now_iso(),
            request_summary={"dataset_id": dataset_id, "year": year, "sido": sido, "gugun": gugun},
            period_range=PreferredPeriod(start=year, end=year),
            license="한국도로교통공단 OpenAPI 이용조건 확인 필요",
            notes=["사고 피해 기록이므로 지역이나 집단을 탓하는 해석을 피해야 합니다."],
            original_docs_url=SOURCE_BY_ID["taas"].docs_url,
            original_data_url=dataset["detail_url"],
        )
        result = CsvFetchResult(
            csv_filename=f"taas_{dataset_id.replace('/', '_')}_{year}_{sido}{gugun}.csv",
            csv_text=csv_text,
            metadata=metadata,
            row_count=len(normalized),
            warnings=warnings,
        )
        self._write_cache("fetch", cache_payload, result.model_dump(mode="json"))
        return result

    def _world_bank_indicator_title(self, indicator_id: str) -> str:
        match = next((item for item in WORLD_BANK_INDICATORS if item["indicator_id"] == indicator_id), None)
        return match["title"] if match else indicator_id

    def _world_bank_unit(self, indicator_id: str) -> str:
        match = next((item for item in WORLD_BANK_INDICATORS if item["indicator_id"] == indicator_id), None)
        return match["unit"] if match else "World Bank indicator unit"

    def _rows_to_csv(self, rows: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        columns = [
            "source_id",
            "source_name",
            "provider",
            "dataset_id",
            "dataset_title",
            "period",
            "region",
            "country_code",
            "item",
            "unit",
            "value",
            "note",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
        return output.getvalue()

    def _read_cache(self, namespace: str, payload: dict[str, Any]) -> dict | None:
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

    def _write_cache(self, namespace: str, payload: dict[str, Any], data: dict) -> None:
        if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > CACHE_MAX_PAYLOAD_BYTES:
            return
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.stat_api_cache_ttl_seconds)
        get_repository().upsert_setting(
            _cache_key(namespace, payload),
            {
                "namespace": namespace,
                "payload_hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest(),
                "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "data": data,
            },
        )
