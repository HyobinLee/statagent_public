from __future__ import annotations

import concurrent.futures
import json
import re
from typing import Any

import httpx
import pandas as pd

from app.core.errors import AppError
from app.core.time import now_utc
from app.models.dataset import DatasetNote
from app.services.ai_guide_service import MockGuideService, get_guide_service
from app.services.dataset_service import MAX_UPLOAD_ROWS, DatasetService
from app.services.secrets import get_kosis_api_key

KOSIS_SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
KOSIS_META_URL = "https://kosis.kr/openapi/statisticsData.do"
KOSIS_EXPL_URL = "https://kosis.kr/openapi/statisticsExplData.do"
KOSIS_PARAM_DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
KOSIS_META_TYPES = ("TBL", "ITM", "PRD", "CMMT")
KOSIS_IMPORT_META_TYPES = ("ITM", "CMMT", "SOURCE", "NCD")
KOSIS_REFERENCE_COLUMNS = ("source", "org_id", "tbl_id", "tbl_name", "last_modified", "unit")
KOSIS_RESULT_COUNT = 30
KOSIS_CANDIDATE_LIMIT = 30
KOSIS_RECOMMENDATION_LIMIT = 5
KOSIS_PERIOD_CODES = {
    "년": "Y",
    "연": "Y",
    "연간": "Y",
    "Y": "Y",
    "반기": "H",
    "H": "H",
    "분기": "Q",
    "Q": "Q",
    "월": "M",
    "월간": "M",
    "M": "M",
    "일": "D",
    "일간": "D",
    "D": "D",
    "부정기": "IR",
    "IR": "IR",
}


def _clean_text(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _get(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if payload.get("err"):
            raise AppError(
                "KOSIS_RESPONSE_ERROR",
                "KOSIS API가 오류 응답을 반환했습니다.",
                _clean_text(payload.get("errMsg") or payload.get("message") or payload.get("err")),
                502,
            )
        for key in ("data", "result", "RESULT", "items", "list", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _loads_kosis_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        normalized = re.sub(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)
        return json.loads(normalized)


def _unique_strings(values: list[Any], limit: int = 8) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = _clean_text(value, 120)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
        if len(unique) >= limit:
            break
    return unique


def _parse_number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "X", "x", "..."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _period_code(value: Any) -> str:
    text = _clean_text(value, 20)
    return KOSIS_PERIOD_CODES.get(text, text or "Y")


def _is_no_data_error(exc: AppError) -> bool:
    return exc.error_code == "KOSIS_RESPONSE_ERROR" and "데이터가 존재하지 않습니다" in exc.suggested_fix


def _is_missing_obj_level_error(exc: AppError) -> bool:
    return exc.error_code == "KOSIS_RESPONSE_ERROR" and "objL" in exc.suggested_fix


class KosisClient:
    def __init__(
        self,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_kosis_api_key()
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def _require_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        raise AppError(
            "KOSIS_API_KEY_REQUIRED",
            "KOSIS API 키가 설정되어 있지 않습니다.",
            "서버 환경변수 KOSIS_API_KEY 또는 KOSIS_API_KEY_SECRET을 설정해 주세요.",
            500,
        )

    def _request_json(self, url: str, params: dict[str, Any]) -> Any:
        request_params = {
            "apiKey": self._require_api_key(),
            "format": "json",
            "jsonVD": "Y",
            **params,
        }
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.get(url, params=request_params)
            response.raise_for_status()
            payload = _loads_kosis_payload(response.text)
        except httpx.HTTPError as exc:
            raise AppError(
                "KOSIS_REQUEST_FAILED",
                "KOSIS API 호출에 실패했습니다.",
                "네트워크 상태와 KOSIS API 키를 확인해 주세요.",
                502,
                {"detail": str(exc)},
            ) from exc
        except ValueError as exc:
            raise AppError(
                "KOSIS_RESPONSE_INVALID",
                "KOSIS API 응답을 JSON으로 읽을 수 없습니다.",
                "잠시 후 다시 시도하거나 검색어를 바꿔 주세요.",
                502,
            ) from exc
        finally:
            if close_client:
                client.close()
        if isinstance(payload, dict) and payload.get("err"):
            raise AppError(
                "KOSIS_RESPONSE_ERROR",
                "KOSIS API가 오류 응답을 반환했습니다.",
                _clean_text(payload.get("errMsg") or payload.get("message") or payload.get("err")),
                502,
            )
        return payload

    def search(self, keyword: str, result_count: int = KOSIS_RESULT_COUNT) -> list[dict[str, Any]]:
        try:
            payload = self._request_json(
                KOSIS_SEARCH_URL,
                {
                    "method": "getList",
                    "searchNm": keyword,
                    "sort": "RANK",
                    "startCount": "1",
                    "resultCount": str(result_count),
                    "content": "json",
                },
            )
        except AppError as exc:
            if _is_no_data_error(exc):
                return []
            raise
        return _rows(payload)

    def table_meta(
        self, org_id: str, tbl_id: str, types: tuple[str, ...] = KOSIS_META_TYPES
    ) -> dict[str, list[dict[str, Any]]]:
        meta: dict[str, list[dict[str, Any]]] = {}
        for meta_type in types:
            try:
                payload = self._request_json(
                    KOSIS_META_URL,
                    {
                        "method": "getMeta",
                        "type": meta_type,
                        "orgId": org_id,
                        "tblId": tbl_id,
                        "content": "json",
                    },
                )
                meta[meta_type] = _rows(payload)
            except AppError:
                meta[meta_type] = []
        return meta

    def statistics_explanation(self, stat_id: str) -> dict[str, Any]:
        try:
            payload = self._request_json(
                KOSIS_EXPL_URL,
                {"method": "getList", "statId": stat_id, "metaItm": "ALL", "content": "json"},
            )
        except AppError:
            return {}
        rows = _rows(payload)
        return rows[0] if rows else {}

    def fetch_data(self, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        org_id = _clean_text(parameters.get("orgId") or parameters.get("org_id"), 40)
        tbl_id = _clean_text(parameters.get("tblId") or parameters.get("tbl_id"), 80)
        if not org_id or not tbl_id:
            raise AppError(
                "KOSIS_FETCH_PARAMETERS_INVALID",
                "KOSIS 자료 호출에 필요한 기관코드와 통계표ID가 없습니다.",
                "자료 후보를 다시 검색해 주세요.",
            )
        request_params = {
            "method": "getList",
            "orgId": org_id,
            "tblId": tbl_id,
            "itmId": parameters.get("itmId") or parameters.get("itm_id") or "ALL",
            "objL1": parameters.get("objL1") or "ALL",
            "objL2": parameters.get("objL2") or "",
            "objL3": parameters.get("objL3") or "",
            "objL4": parameters.get("objL4") or "",
            "objL5": parameters.get("objL5") or "",
            "objL6": parameters.get("objL6") or "",
            "objL7": parameters.get("objL7") or "",
            "objL8": parameters.get("objL8") or "",
            "prdSe": _period_code(parameters.get("prdSe") or parameters.get("prd_se") or "Y"),
            "newEstPrdCnt": parameters.get("newEstPrdCnt") or parameters.get("new_est_prd_cnt") or "3",
            "prdInterval": parameters.get("prdInterval") or "1",
        }
        if parameters.get("startPrdDe"):
            request_params["startPrdDe"] = parameters["startPrdDe"]
        if parameters.get("endPrdDe"):
            request_params["endPrdDe"] = parameters["endPrdDe"]
        payload = self._request_data_with_obj_retry(request_params)
        return _rows(payload)

    def _request_data_with_obj_retry(self, request_params: dict[str, Any]) -> Any:
        params = dict(request_params)
        while True:
            try:
                return self._request_json(KOSIS_PARAM_DATA_URL, params)
            except AppError as exc:
                if not _is_missing_obj_level_error(exc):
                    raise
                for level in range(2, 9):
                    key = f"objL{level}"
                    if not params.get(key):
                        params[key] = "ALL"
                        break
                else:
                    raise


class KosisDatasetService:
    def __init__(
        self,
        client: KosisClient | None = None,
        dataset_service: DatasetService | None = None,
        ai_service: Any | None = None,
    ) -> None:
        self.client = client or KosisClient()
        self.dataset_service = dataset_service or DatasetService()
        self.ai_service = ai_service

    def recommend(self, *, research_question: str, grade_level: str = "middle_high") -> dict:
        question = _clean_text(research_question, 500)
        if not question:
            raise AppError(
                "KOSIS_RESEARCH_QUESTION_REQUIRED",
                "KOSIS 자료를 찾을 탐구 질문이 필요합니다.",
                "결정한 탐구 주제를 먼저 입력해 주세요.",
            )
        plan, ai_fallback = self._search_plan(question, grade_level)
        keywords = _unique_strings(plan.get("search_keywords") or [], limit=5)
        if not keywords:
            keywords = _unique_strings([question], limit=1)

        candidates = self._search_candidates(keywords)
        recommendations = self._recommend_from_candidates(question, grade_level, plan, candidates)
        metadata = {
            "source": "kosis",
            "searched_keywords": keywords,
            "candidate_count": len(candidates),
        }
        if ai_fallback:
            metadata["ai_fallback"] = ai_fallback
        return {
            "search_plan": plan,
            "recommendations": recommendations,
            "raw_candidates": candidates,
            "metadata": metadata,
        }

    def search_by_keyword(
        self,
        *,
        search_keyword: str,
        research_question: str,
        grade_level: str = "middle_high",
    ) -> dict:
        keyword = _clean_text(search_keyword, 120)
        question = _clean_text(research_question, 500) or keyword
        if not keyword:
            raise AppError(
                "KOSIS_SEARCH_KEYWORD_REQUIRED",
                "KOSIS 검색어를 입력해야 합니다.",
                "통계표에 들어 있을 법한 핵심어를 한두 개 입력해 주세요.",
            )
        plan, ai_fallback = self._search_plan(question, grade_level)
        plan = {
            **plan,
            "research_question": question,
            "student_search_keyword": keyword,
            "search_keywords": [keyword],
            "search_mode": "student_keyword",
        }
        candidates = self._search_candidates([keyword])
        recommendations = self._recommend_from_candidates(question, grade_level, plan, candidates)
        metadata = {
            "source": "kosis",
            "search_mode": "student_keyword",
            "student_search_keyword": keyword,
            "searched_keywords": [keyword],
            "candidate_count": len(candidates),
        }
        if ai_fallback:
            metadata["ai_fallback"] = ai_fallback
        return {
            "search_plan": plan,
            "recommendations": recommendations,
            "raw_candidates": candidates,
            "metadata": metadata,
        }

    def import_recommendation(
        self,
        *,
        topic_id: str,
        owner_user_id: str,
        recommendation: dict[str, Any],
    ) -> dict:
        parameters = recommendation.get("fetch_parameters") or recommendation.get("fetchParameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}
        parameters = {
            **parameters,
            "orgId": parameters.get("orgId") or recommendation.get("org_id"),
            "tblId": parameters.get("tblId") or recommendation.get("tbl_id"),
        }
        rows = self.client.fetch_data(parameters)
        if not rows:
            raise AppError(
                "KOSIS_DATA_EMPTY",
                "선택한 KOSIS 자료에서 데이터 행을 찾지 못했습니다.",
                "다른 후보를 선택하거나 검색어를 바꿔 주세요.",
                404,
            )
        df = self._normalize_data_rows(rows)
        if len(df) > MAX_UPLOAD_ROWS:
            df = self._reduce_rows_for_student(df)
        table_title = _clean_text(
            recommendation.get("dataset_title")
            or recommendation.get("tbl_name")
            or parameters.get("tblId")
            or "KOSIS 자료",
            80,
        )
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        org_name = _clean_text(recommendation.get("source_agency") or recommendation.get("org_name"), 120)
        tbl_id = _clean_text(recommendation.get("tbl_id") or parameters.get("tblId"), 80)
        description = _clean_text(
            recommendation.get("student_friendly_summary")
            or recommendation.get("student_friendly_explanation")
            or f"KOSIS에서 가져온 {table_title} 자료입니다.",
            500,
        )
        source_note = f"{org_name or 'KOSIS'} {tbl_id}에서 {now_utc().strftime('%Y-%m-%d')} API로 가져옴"
        column_display_names, column_descriptions, column_units = self._column_metadata(df)
        meta: dict[str, list[dict[str, Any]]] = {}
        explanation: dict[str, Any] = {}
        org_id = _clean_text(parameters.get("orgId") or recommendation.get("org_id"), 40)
        if org_id and tbl_id:
            try:
                meta = self.client.table_meta(org_id, tbl_id, types=KOSIS_IMPORT_META_TYPES)
            except AppError:
                meta = {}
            stat_id = next(
                (
                    _clean_text(_get(row, "STAT_ID", "statId"), 40)
                    for row in (meta.get("SOURCE") or [])
                    if _clean_text(_get(row, "STAT_ID", "statId"), 40)
                ),
                f"{org_id}{tbl_id}",
            )
            try:
                explanation = self.client.statistics_explanation(stat_id)
            except AppError:
                explanation = {}
        return self.dataset_service.create_uploaded_dataset(
            filename=f"kosis_{tbl_id or 'dataset'}.csv",
            content=csv_bytes,
            topic_id=topic_id,
            owner_user_id=owner_user_id,
            dataset_name=table_title,
            source="KOSIS OpenAPI",
            source_note=source_note,
            description=description,
            time_range=self._period_range(df),
            geographic_unit=self._geographic_unit(df),
            column_display_names=column_display_names,
            column_descriptions=column_descriptions,
            column_units=column_units,
            column_extras=self._column_extras(df, meta),
            source_notes=self._source_notes(meta, explanation),
        )

    def _search_plan(self, question: str, grade_level: str) -> tuple[dict, str | None]:
        service = self.ai_service or get_guide_service()
        try:
            return service.kosis_search_plan(question, grade_level), None
        except (AttributeError, AppError) as exc:
            fallback = MockGuideService().kosis_search_plan(question, grade_level)
            return fallback, getattr(exc, "error_code", "AI_SEARCH_PLAN_UNAVAILABLE")

    def _recommend_from_candidates(
        self,
        question: str,
        grade_level: str,
        plan: dict,
        candidates: list[dict],
    ) -> dict:
        service = self.ai_service or get_guide_service()
        try:
            recommendations = service.kosis_dataset_recommendations(question, grade_level, plan, candidates)
        except (AttributeError, AppError):
            recommendations = MockGuideService().kosis_dataset_recommendations(
                question,
                grade_level,
                plan,
                candidates,
            )
        recommendations["recommended_datasets"] = self._attach_fetch_parameters(
            recommendations.get("recommended_datasets") or [],
            candidates,
        )
        return recommendations

    def _search_candidates(self, keywords: list[str]) -> list[dict]:
        candidates: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for keyword in keywords:
            for row in self.client.search(keyword, result_count=KOSIS_RESULT_COUNT):
                candidate = self._candidate_from_search_row(row, keyword)
                key = (candidate["org_id"], candidate["tbl_id"])
                if not candidate["org_id"] or not candidate["tbl_id"] or key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if len(candidates) >= KOSIS_CANDIDATE_LIMIT:
                    break
            if len(candidates) >= KOSIS_CANDIDATE_LIMIT:
                break
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            enriched_candidates = list(executor.map(self._enrich_candidate, candidates))
        return enriched_candidates

    def _candidate_from_search_row(self, row: dict[str, Any], keyword: str) -> dict:
        return {
            "org_id": _clean_text(_get(row, "ORG_ID", "orgId"), 40),
            "org_name": _clean_text(_get(row, "ORG_NM", "orgNm"), 120),
            "tbl_id": _clean_text(_get(row, "TBL_ID", "tblId"), 80),
            "tbl_name": _clean_text(_get(row, "TBL_NM", "tblNm"), 200),
            "stat_id": _clean_text(_get(row, "STAT_ID", "statId"), 80),
            "stat_name": _clean_text(_get(row, "STAT_NM", "statNm"), 200),
            "contents": _clean_text(_get(row, "CONTENTS", "contents"), 400),
            "start_period": _clean_text(_get(row, "STRT_PRD_DE", "startPeriod"), 40),
            "end_period": _clean_text(_get(row, "END_PRD_DE", "endPeriod"), 40),
            "note": _clean_text(_get(row, "ITEM03", "note"), 400),
            "table_url": _clean_text(_get(row, "LINK_URL", "TBL_VIEW_URL", "tableUrl"), 600),
            "search_keyword": keyword,
        }

    def _enrich_candidate(self, candidate: dict) -> dict:
        meta = self.client.table_meta(candidate["org_id"], candidate["tbl_id"])
        candidate["available_dimensions"] = self._dimensions(meta)
        candidate["available_items"] = self._items(meta)
        candidate["unit"] = self._unit(meta)
        candidate["period_range"] = self._candidate_period_range(candidate, meta)
        candidate["fetch_parameters"] = self._default_fetch_parameters(candidate, meta)
        candidate["metadata_summary"] = {
            "meta_item_count": len(meta.get("ITM") or []),
            "has_period_meta": bool(meta.get("PRD")),
            "has_note": bool(meta.get("CMMT")),
        }
        return candidate

    def _dimensions(self, meta: dict[str, list[dict[str, Any]]]) -> list[str]:
        rows = meta.get("ITM") or []
        return _unique_strings([_get(row, "OBJ_NM", "objNm") for row in rows], limit=8)

    def _items(self, meta: dict[str, list[dict[str, Any]]]) -> list[str]:
        rows = meta.get("ITM") or []
        return _unique_strings([_get(row, "ITM_NM", "itmNm") for row in rows], limit=8)

    def _unit(self, meta: dict[str, list[dict[str, Any]]]) -> str:
        rows = meta.get("ITM") or []
        units = _unique_strings([_get(row, "UNIT_NM", "unitNm", "UNIT_ENG_NM") for row in rows], limit=2)
        return ", ".join(units)

    def _candidate_period_range(self, candidate: dict, meta: dict[str, list[dict[str, Any]]]) -> str:
        if candidate.get("start_period") or candidate.get("end_period"):
            return f"{candidate.get('start_period') or '?'}~{candidate.get('end_period') or '?'}"
        period_rows = meta.get("PRD") or []
        periods = _unique_strings([_get(row, "PRD_DE", "prdDe", "PRD_NM", "prdNm") for row in period_rows], limit=20)
        if len(periods) >= 2:
            return f"{periods[-1]}~{periods[0]}"
        return periods[0] if periods else "확인 필요"

    def _default_fetch_parameters(self, candidate: dict, meta: dict[str, list[dict[str, Any]]]) -> dict:
        period_rows = meta.get("PRD") or []
        period_codes = _unique_strings([_get(row, "PRD_SE", "prdSe") for row in period_rows], limit=1)
        return {
            "orgId": candidate["org_id"],
            "tblId": candidate["tbl_id"],
            "itmId": "ALL",
            "objL1": "ALL",
            "objL2": "",
            "objL3": "",
            "objL4": "",
            "objL5": "",
            "objL6": "",
            "objL7": "",
            "objL8": "",
            "prdSe": _period_code(period_codes[0] if period_codes else "Y"),
            "newEstPrdCnt": "3",
            "prdInterval": "1",
        }

    def _attach_fetch_parameters(self, recommendations: list[dict], candidates: list[dict]) -> list[dict]:
        by_key = {(candidate["org_id"], candidate["tbl_id"]): candidate for candidate in candidates}
        hydrated: list[dict] = []
        for index, recommendation in enumerate(recommendations[:KOSIS_RECOMMENDATION_LIMIT], start=1):
            org_id = _clean_text(recommendation.get("org_id"), 40)
            tbl_id = _clean_text(recommendation.get("tbl_id"), 80)
            candidate = by_key.get((org_id, tbl_id))
            if candidate:
                recommendation = {
                    **recommendation,
                    "rank": recommendation.get("rank") or index,
                    "org_id": candidate["org_id"],
                    "org_name": candidate["org_name"],
                    "tbl_id": candidate["tbl_id"],
                    "tbl_name": candidate["tbl_name"],
                    "dataset_title": recommendation.get("dataset_title") or candidate["tbl_name"],
                    "source_agency": recommendation.get("source_agency") or candidate["org_name"],
                    "stat_name": recommendation.get("stat_name") or candidate["stat_name"],
                    "available_dimensions": recommendation.get("available_dimensions")
                    or candidate.get("available_dimensions")
                    or [],
                    "available_items": recommendation.get("available_items") or candidate.get("available_items") or [],
                    "period_range": recommendation.get("period_range") or candidate.get("period_range") or "확인 필요",
                    "unit": recommendation.get("unit") or candidate.get("unit") or "확인 필요",
                    "table_url": candidate.get("table_url"),
                    "fetch_parameters": candidate.get("fetch_parameters"),
                }
            hydrated.append(recommendation)
        return hydrated

    def _normalize_data_rows(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {
                "source": "KOSIS",
                "org_id": _get(row, "ORG_ID", "orgId"),
                "tbl_id": _get(row, "TBL_ID", "tblId"),
                "tbl_name": _get(row, "TBL_NM", "tblNm"),
                "period": _get(row, "PRD_DE", "prdDe"),
                "item": _get(row, "ITM_NM", "itmNm"),
                "unit": _get(row, "UNIT_NM", "unitNm"),
                "value": _parse_number(_get(row, "DT", "dt")),
                "last_modified": _get(row, "LST_CHN_DE", "lstChnDe"),
            }
            for index in range(1, 9):
                dim_name = _get(row, f"C{index}_OBJ_NM", f"c{index}ObjNm")
                dim_value = _get(row, f"C{index}_NM", f"c{index}Nm")
                if dim_name or dim_value:
                    item[f"dimension_{index}_name"] = dim_name
                    item[f"dimension_{index}_value"] = dim_value
            if "dimension_1_value" not in item:
                dim_name = _get(row, "OBJ_NM", "objNm")
                dim_value = _get(row, "NM", "nm")
                if dim_name or dim_value:
                    item["dimension_1_name"] = dim_name
                    item["dimension_1_value"] = dim_value
            normalized_rows.append(item)
        df = pd.DataFrame(normalized_rows)
        empty_columns = [column for column in df.columns if df[column].isna().all()]
        if empty_columns:
            df = df.drop(columns=empty_columns)
        if "value" not in df.columns or df["value"].isna().all():
            raise AppError(
                "KOSIS_DATA_VALUE_MISSING",
                "선택한 KOSIS 자료에서 수치값을 찾지 못했습니다.",
                "다른 후보를 선택하거나 기간과 항목 조건을 조정해 주세요.",
            )
        return df

    def _column_extras(self, df: pd.DataFrame, meta: dict[str, list[dict[str, Any]]]) -> dict[str, dict]:
        extras: dict[str, dict] = {}

        for column_name in KOSIS_REFERENCE_COLUMNS:
            if column_name in df.columns:
                extras.setdefault(column_name, {})["secondary"] = True
        for column_name in df.columns:
            if str(column_name).startswith("dimension_") and str(column_name).endswith("_name"):
                extras.setdefault(column_name, {})["secondary"] = True

        if "item" in df.columns:
            unit_by_item: dict[str, str] = {}
            for row in meta.get("ITM") or []:
                item_name = _clean_text(_get(row, "ITM_NM", "itmNm"), 120)
                item_unit = _clean_text(_get(row, "UNIT_NM", "unitNm", "UNIT_ENG_NM", "unitEngNm"), 40)
                if item_name and item_unit:
                    unit_by_item.setdefault(item_name, item_unit)
            if "unit" in df.columns:
                pairs = df[["item", "unit"]].dropna().astype(str).drop_duplicates()
                for item_name, item_unit in pairs.itertuples(index=False):
                    unit_by_item.setdefault(_clean_text(item_name, 120), _clean_text(item_unit, 40))

            note_by_item: dict[str, str] = {}
            for row in meta.get("CMMT") or []:
                item_name = _clean_text(_get(row, "ITM_NM", "itmNm"), 120)
                comment = _clean_text(_get(row, "CMMT_DC", "cmmtDc"), 300)
                if item_name and comment:
                    note_by_item.setdefault(item_name, comment)

            value_labels = []
            for item_name in _unique_strings(df["item"].dropna().tolist(), limit=20):
                value_labels.append(
                    {
                        "value": item_name,
                        "label": item_name,
                        "unit": unit_by_item.get(item_name) or None,
                        "note": note_by_item.get(item_name) or None,
                    }
                )
            if value_labels:
                extras.setdefault("item", {})["value_labels"] = value_labels

        if "unit" in df.columns and "value" in df.columns:
            units = _unique_strings(df["unit"].dropna().tolist(), limit=5)
            if len(units) >= 2:
                extras.setdefault("value", {})["warnings"] = [
                    f"단위가 {len(units)}가지({', '.join(units[:3])}) 섞여 있습니다. "
                    "먼저 '항목'에서 지표 하나를 고른 뒤 비교하세요."
                ]
        return extras

    def _source_notes(
        self,
        meta: dict[str, list[dict[str, Any]]],
        explanation: dict[str, Any] | None = None,
    ) -> list[DatasetNote]:
        notes: list[DatasetNote] = []
        seen: set[tuple[str, str]] = set()

        def add(label: str, value: Any, limit: int = 600) -> None:
            text = _clean_text(value, limit)
            if not text or (label, text) in seen:
                return
            seen.add((label, text))
            notes.append(DatasetNote(label=label, text=text))

        for row in (meta.get("NCD") or [])[:1]:
            add("작성 기관", _get(row, "ORG_NM", "orgNm"), 120)
            add("수록 주기", _get(row, "PRD_SE", "prdSe"), 60)
            add("자료 갱신일", _get(row, "SEND_DE", "sendDe"), 40)
        for row in (meta.get("SOURCE") or [])[:1]:
            add("조사명", _get(row, "JOSA_NM", "josaNm"), 200)
            add("담당 부서", _get(row, "DEPT_NM", "deptNm"), 200)

        explanation = explanation or {}
        add("조사 목적", _get(explanation, "writingPurps"), 800)
        add("조사 대상", _get(explanation, "josaUnit"), 400)
        add("주요 용어", _get(explanation, "mainTermExpl"), 900)
        add("읽을 때 주의할 점", _get(explanation, "dataUserNote"), 900)

        for row in (meta.get("CMMT") or [])[:5]:
            if _clean_text(_get(row, "ITM_NM", "itmNm"), 200):
                continue
            label = _clean_text(_get(row, "CMMT_NM", "cmmtNm"), 40) or "주석"
            add(label, _get(row, "CMMT_DC", "cmmtDc"), 900)
        return notes

    def _column_metadata(self, df: pd.DataFrame) -> tuple[dict[str, str], dict[str, str], dict[str, str | None]]:
        display_names = {
            "source": "출처",
            "org_id": "기관 코드",
            "tbl_id": "통계표 ID",
            "tbl_name": "통계표명",
            "period": "수록 시점",
            "item": "항목",
            "unit": "단위",
            "value": "수치값",
            "last_modified": "최종 수정일",
        }
        descriptions = {
            "source": "자료 출처",
            "org_id": "KOSIS 작성 기관 코드",
            "tbl_id": "KOSIS 통계표 ID",
            "tbl_name": "KOSIS 통계표 이름",
            "period": "통계값이 수록된 시점",
            "item": "통계표의 항목 또는 지표 이름",
            "unit": "수치값의 단위",
            "value": "KOSIS 통계자료 API의 수치값",
            "last_modified": "KOSIS 자료 최종 수정일",
        }
        units: dict[str, str | None] = {}
        value_units = _unique_strings(df["unit"].dropna().tolist(), limit=2) if "unit" in df.columns else []
        if len(value_units) == 1:
            units["value"] = value_units[0]

        for index in range(1, 9):
            name_column = f"dimension_{index}_name"
            value_column = f"dimension_{index}_value"
            if name_column in df.columns:
                dimension_names = _unique_strings(df[name_column].dropna().tolist(), limit=3)
                display_names[name_column] = f"분류{index} 이름"
                descriptions[name_column] = f"KOSIS 분류{index}의 이름"
                if value_column in df.columns:
                    display = dimension_names[0] if len(dimension_names) == 1 else f"분류{index} 값"
                    display_names[value_column] = display
                    descriptions[value_column] = f"KOSIS 분류{index}의 값"
            elif value_column in df.columns:
                display_names[value_column] = f"분류{index} 값"
                descriptions[value_column] = f"KOSIS 분류{index}의 값"

        return display_names, descriptions, units

    def _reduce_rows_for_student(self, df: pd.DataFrame) -> pd.DataFrame:
        reduced = df.copy()
        if "period" in reduced.columns:
            reduced = reduced.sort_values("period", ascending=False, kind="stable")
        return reduced.head(MAX_UPLOAD_ROWS).reset_index(drop=True)

    def _period_range(self, df: pd.DataFrame) -> str:
        if "period" not in df:
            return "KOSIS 자료"
        periods = [str(value) for value in df["period"].dropna().unique()]
        if not periods:
            return "KOSIS 자료"
        periods.sort()
        return f"{periods[0]}~{periods[-1]}" if len(periods) > 1 else periods[0]

    def _geographic_unit(self, df: pd.DataFrame) -> str | None:
        for column in df.columns:
            if column.startswith("dimension_") and column.endswith("_name"):
                names = {str(value) for value in df[column].dropna().unique()}
                if any("지역" in value or "시도" in value or "행정구역" in value for value in names):
                    return "KOSIS 지역 분류"
        return None
