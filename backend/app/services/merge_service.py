from __future__ import annotations

import re
from difflib import SequenceMatcher
from uuid import uuid4

import pandas as pd

from app.core.errors import AppError
from app.core.time import now_utc
from app.services.dataset_service import DatasetService


MAX_MERGE_DATASETS = 5
MAX_KEY_VALUES = 2000
SIMILARITY_THRESHOLD = 0.70

_REGION_SUFFIXES = re.compile(r"(특별시|광역시|특별자치시|특별자치도|특별자치구)$")
_WHITESPACE = re.compile(r"\s+")


def _normalize_region(name: str) -> str:
    text = _WHITESPACE.sub("", str(name or "")).strip()
    text = _REGION_SUFFIXES.sub("", text)
    return text


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _is_likely_key_column(series: pd.Series, *, dtype: str = "", display_name: str = "") -> tuple[str | None, float]:
    lowered = (display_name or series.name or "").lower()
    name_lower = str(series.name or "").lower()

    region_keywords = (
        "지역",
        "시도",
        "행정구역",
        "시군구",
        "region",
        "area",
        "province",
        "city",
        "district",
        "dimension_1_value",
    )
    if any(keyword in lowered or keyword in name_lower for keyword in region_keywords):
        return "region", 0.9

    time_keywords = (
        "연도",
        "년도",
        "시점",
        "period",
        "year",
        "date",
        "month",
        "분기",
        "quarter",
    )
    if any(keyword in lowered or keyword in name_lower for keyword in time_keywords):
        return "time", 0.85

    if dtype == "categorical":
        non_null = series.dropna()
        unique_count = non_null.nunique()
        total = len(non_null)
        if 0 < unique_count <= 200 and total > 0:
            ratio = unique_count / total
            if ratio > 0.3:
                return "category", 0.5
    return None, 0.0


def _safe_column_suffix(base: str, existing: set[str], suffix: str) -> str:
    candidate = f"{base}_{suffix}"
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}_{counter}"
        counter += 1
    return candidate


def build_merged_dataframe(
    dataset_service: DatasetService,
    *,
    dataset_ids: list[str],
    key_column_mappings: dict[str, str],
    join_type: str = "inner",
    time_column_mappings: dict[str, str] | None = None,
    selected_time_points: list[str] | None = None,
) -> tuple[pd.DataFrame, list[dict], str]:
    if len(dataset_ids) < 2:
        raise AppError(
            "MERGE_MINIMUM_DATASETS",
            "결합하려면 자료를 2개 이상 선택해야 합니다.",
            "자료 목록에서 하나 더 선택해 주세요.",
        )
    if join_type not in ("inner", "outer"):
        join_type = "inner"

    use_composite = bool(time_column_mappings and all(time_column_mappings.get(did) for did in dataset_ids))

    unified_key = "__merge_key__"
    unified_time = "__merge_time__"

    frames: list[tuple[str, pd.DataFrame, str, str | None]] = []
    source_info: list[dict] = []
    for did in dataset_ids:
        key_col = key_column_mappings.get(did)
        if not key_col:
            raise AppError(
                "MERGE_KEY_COLUMN_REQUIRED",
                f"자료 {did}의 지역 기준 컬럼을 지정해 주세요.",
                "각 자료에서 지역(시도 등) 컬럼을 선택해 주세요.",
            )
        ds = dataset_service.get_dataset(did)
        df = dataset_service.read_dataframe(did)
        if key_col not in df.columns:
            raise AppError(
                "MERGE_KEY_COLUMN_NOT_FOUND",
                f"자료 '{ds.name}'에서 '{key_col}' 컬럼을 찾을 수 없습니다.",
                "자료 표를 확인한 뒤 다시 시도해 주세요.",
            )

        time_col: str | None = (time_column_mappings or {}).get(did)

        if time_col and time_col in df.columns and selected_time_points:
            allowed = set(str(t) for t in selected_time_points)
            df = df[df[time_col].astype(str).isin(allowed)].copy()

        frames.append((did, df, key_col, time_col))
        source_info.append(
            {
                "dataset_id": did,
                "name": ds.name,
                "key_column": key_col,
                "time_column": time_col,
                "composite_join": use_composite,
                "row_count": len(df),
            }
        )

    reserved = {unified_key, unified_time}
    renamed_frames: list[pd.DataFrame] = []
    all_columns: set[str] = set(reserved)

    for idx, (did, df, key_col, time_col) in enumerate(frames):
        ds = dataset_service.get_dataset(did)
        short_name = ds.name[:10] if ds.name else f"ds{idx + 1}"

        rename_map: dict[str, str] = {key_col: unified_key}
        if use_composite and time_col:
            rename_map[time_col] = unified_time

        cols_to_rename: dict[str, str] = {}
        for col in df.columns:
            if col in rename_map:
                continue
            new_name = col
            if new_name in all_columns:
                new_name = _safe_column_suffix(col, all_columns, short_name)
            cols_to_rename[col] = new_name
            all_columns.add(new_name)

        df = df.rename(columns={**rename_map, **cols_to_rename})
        renamed_frames.append(df)

    join_on: list[str] | str = [unified_key, unified_time] if use_composite else unified_key
    merged = renamed_frames[0]
    for frame in renamed_frames[1:]:
        merged = pd.merge(
            merged,
            frame,
            on=join_on,
            how=join_type,
            suffixes=("", f"_{len(renamed_frames)}"),
        )

    first_ds = dataset_service.get_dataset(dataset_ids[0])
    first_key_col = key_column_mappings[dataset_ids[0]]
    first_key_meta = next((c for c in first_ds.columns if c.name == first_key_col), None)
    final_key_name = first_key_meta.display_name if first_key_meta else first_key_col
    if final_key_name in merged.columns and final_key_name != unified_key:
        final_key_name = f"{final_key_name}_key"

    rename_back: dict[str, str] = {unified_key: final_key_name}
    if use_composite and unified_time in merged.columns:
        first_time_col = (time_column_mappings or {}).get(dataset_ids[0], "")
        first_time_meta = next((c for c in first_ds.columns if c.name == first_time_col), None)
        final_time_name = first_time_meta.display_name if first_time_meta else first_time_col
        if final_time_name in merged.columns and final_time_name != unified_time:
            final_time_name = f"{final_time_name}_시점"
        rename_back[unified_time] = final_time_name

    merged = merged.rename(columns=rename_back)

    if merged.empty:
        raise AppError(
            "MERGE_RESULT_EMPTY",
            "결합 결과에 데이터가 없습니다.",
            "키 정규화를 수행하거나 outer join을 선택해 주세요.",
        )

    return merged, source_info, final_key_name


class MergeService:
    def __init__(self, dataset_service: DatasetService | None = None) -> None:
        self.datasets = dataset_service or DatasetService()

    def suggest_key_columns(self, dataset_id: str) -> list[dict]:
        dataset = self.datasets.get_dataset(dataset_id)
        df = self.datasets.read_dataframe(dataset_id)
        suggestions: list[dict] = []
        for col_meta in dataset.columns:
            series = df[col_meta.name]
            key_type, confidence = _is_likely_key_column(
                series,
                dtype=col_meta.dtype,
                display_name=col_meta.display_name,
            )
            if key_type:
                unique_values = [str(v) for v in series.dropna().unique()[:50]]
                suggestions.append(
                    {
                        "column_name": col_meta.name,
                        "display_name": col_meta.display_name,
                        "key_type": key_type,
                        "confidence": round(confidence, 2),
                        "unique_count": int(series.nunique(dropna=True)),
                        "sample_values": unique_values[:10],
                    }
                )
        suggestions.sort(key=lambda s: s["confidence"], reverse=True)
        return suggestions

    def preview_merge(
        self,
        dataset_ids: list[str],
        key_column_mappings: dict[str, str],
        time_column_mappings: dict[str, str] | None = None,
    ) -> dict:
        if len(dataset_ids) < 2:
            raise AppError(
                "MERGE_MINIMUM_DATASETS",
                "결합하려면 자료를 2개 이상 선택해야 합니다.",
                "자료 목록에서 하나 더 선택해 주세요.",
            )
        if len(dataset_ids) > MAX_MERGE_DATASETS:
            raise AppError(
                "MERGE_TOO_MANY_DATASETS",
                f"자료는 최대 {MAX_MERGE_DATASETS}개까지 결합할 수 있습니다.",
                "결합할 자료 수를 줄여 주세요.",
            )

        use_composite = bool(time_column_mappings and all(time_column_mappings.get(did) for did in dataset_ids))

        dataset_keys: dict[str, set[str]] = {}
        region_keys: dict[str, set[str]] = {}
        dataset_info: list[dict] = []
        for did in dataset_ids:
            col = key_column_mappings.get(did)
            if not col:
                raise AppError(
                    "MERGE_KEY_COLUMN_REQUIRED",
                    f"자료 {did}의 지역 기준 컬럼을 지정해 주세요.",
                    "각 자료에서 지역(시도 등)으로 사용할 컬럼을 선택해 주세요.",
                )
            ds = self.datasets.get_dataset(did)
            df = self.datasets.read_dataframe(did)
            if col not in df.columns:
                raise AppError(
                    "MERGE_KEY_COLUMN_NOT_FOUND",
                    f"자료 '{ds.name}'에서 '{col}' 컬럼을 찾을 수 없습니다.",
                    "자료 요약을 확인한 뒤 올바른 컬럼을 선택해 주세요.",
                )

            region_vals = set(df[col].dropna().astype(str).unique())
            region_keys[did] = region_vals

            if use_composite:
                time_col = (time_column_mappings or {}).get(did, "")
                if time_col and time_col in df.columns:
                    sub = df[[col, time_col]].dropna()
                    values: set[str] = {
                        f"{r}||{t}" for r, t in zip(sub[col].astype(str), sub[time_col].astype(str), strict=True)
                    }
                else:
                    values = region_vals
            else:
                values = region_vals

            if len(values) > MAX_KEY_VALUES:
                raise AppError(
                    "MERGE_KEY_TOO_MANY_VALUES",
                    f"'{col}' 컬럼의 고유값이 {MAX_KEY_VALUES}개를 넘습니다.",
                    "더 적은 범주를 가진 컬럼을 선택하거나, 자료를 먼저 필터링해 주세요.",
                )
            dataset_keys[did] = values
            sample_raw = sorted(list(values))[:10]
            sample_display = [v.replace("||", " × ") for v in sample_raw] if use_composite else sample_raw
            dataset_info.append(
                {
                    "dataset_id": did,
                    "name": ds.name,
                    "key_column": col,
                    "time_column": (time_column_mappings or {}).get(did),
                    "composite_key": use_composite,
                    "key_count": len(values),
                    "sample_keys": sample_display,
                    "row_count": len(df),
                    "column_count": len(df.columns),
                }
            )

        all_key_sets = list(dataset_keys.values())
        common = set.intersection(*all_key_sets) if all_key_sets else set()
        unique_per_dataset: dict[str, list[str]] = {}
        for did, keys in dataset_keys.items():
            unique = keys - common
            display = [v.replace("||", " × ") for v in sorted(list(unique))[:30]]
            unique_per_dataset[did] = display

        fuzzy_suggestions = self._fuzzy_match_suggestions(region_keys)

        common_display = [v.replace("||", " × ") for v in sorted(list(common))[:30]]
        return {
            "datasets": dataset_info,
            "common_keys": common_display,
            "common_count": len(common),
            "composite_key": use_composite,
            "unique_per_dataset": unique_per_dataset,
            "fuzzy_suggestions": fuzzy_suggestions,
            "merge_feasible": len(common) > 0,
            "warnings": self._merge_warnings(dataset_info, common),
        }

    def _fuzzy_match_suggestions(self, dataset_keys: dict[str, set[str]]) -> list[dict]:
        suggestions: list[dict] = []
        dataset_ids = list(dataset_keys.keys())
        if len(dataset_ids) < 2:
            return suggestions

        keys_a = dataset_keys[dataset_ids[0]]
        keys_b = dataset_keys[dataset_ids[1]]
        common = keys_a & keys_b
        unmatched_a = keys_a - common
        unmatched_b = keys_b - common

        for val_a in list(unmatched_a)[:50]:
            norm_a = _normalize_region(val_a)
            best_match = None
            best_score = 0.0
            for val_b in list(unmatched_b)[:50]:
                norm_b = _normalize_region(val_b)
                score = _similarity(norm_a, norm_b)
                if score > best_score:
                    best_score = score
                    best_match = val_b
            if best_match and best_score >= SIMILARITY_THRESHOLD:
                suggestions.append(
                    {
                        "value_a": val_a,
                        "value_b": best_match,
                        "similarity": round(best_score, 3),
                        "dataset_a": dataset_ids[0],
                        "dataset_b": dataset_ids[1],
                    }
                )

        suggestions.sort(key=lambda s: s["similarity"], reverse=True)
        return suggestions[:30]

    def _merge_warnings(self, dataset_info: list[dict], common: set[str]) -> list[str]:
        warnings: list[str] = []
        if not common:
            warnings.append("공통 키가 없습니다. 키 정규화를 먼저 수행하거나, 다른 기준 컬럼을 선택해 주세요.")
        total_rows = sum(d["row_count"] for d in dataset_info)
        if total_rows > 15000:
            warnings.append(f"전체 {total_rows:,}행이므로 결합 후 자료가 클 수 있습니다.")
        return warnings

    def harmonize_keys(
        self,
        dataset_id: str,
        key_column: str,
        rename_map: dict[str, str],
        *,
        owner_user_id: str,
    ) -> dict:
        dataset = self.datasets.get_dataset(dataset_id)
        if not dataset.uploaded:
            raise AppError(
                "MERGE_HARMONIZE_NOT_UPLOADED",
                "기본 자료는 수정할 수 없습니다.",
                "업로드 또는 KOSIS에서 가져온 자료만 키 정규화할 수 있습니다.",
            )
        df = self.datasets.read_dataframe(dataset_id)
        if key_column not in df.columns:
            raise AppError(
                "MERGE_KEY_COLUMN_NOT_FOUND",
                f"'{key_column}' 컬럼을 찾을 수 없습니다.",
                "자료 표를 새로고침한 뒤 다시 시도해 주세요.",
            )
        if not rename_map:
            return {"changed": 0, "dataset_id": dataset_id}

        changed = 0
        series = df[key_column].astype(str)
        for old_val, new_val in rename_map.items():
            mask = series == str(old_val)
            count = int(mask.sum())
            if count > 0:
                df.loc[mask, key_column] = str(new_val)
                changed += count

        if changed > 0:
            path = self.datasets.csv_path(dataset_id)
            df.to_csv(path, index=False, encoding="utf-8-sig")
            self.datasets._refresh_uploaded_dataset(dataset, df.copy())

        return {
            "changed": changed,
            "dataset_id": dataset_id,
            "key_column": key_column,
        }

    def ai_harmonize_suggestions(
        self,
        dataset_ids: list[str],
        key_column_mappings: dict[str, str],
    ) -> list[dict]:
        try:
            from app.services.ai_guide_service import get_guide_service

            service = get_guide_service()
        except Exception:
            service = None

        key_values: dict[str, list[str]] = {}
        for did in dataset_ids:
            col = key_column_mappings.get(did, "")
            if not col:
                continue
            df = self.datasets.read_dataframe(did)
            if col in df.columns:
                vals = [str(v) for v in df[col].dropna().unique()[:100]]
                key_values[did] = vals

        if len(key_values) < 2:
            return []

        dids = list(key_values.keys())
        vals_a = key_values[dids[0]]
        vals_b = key_values[dids[1]]

        if service and hasattr(service, "harmonize_region_names"):
            try:
                return service.harmonize_region_names(vals_a, vals_b)
            except Exception:
                pass

        suggestions: list[dict] = []
        matched_b: set[str] = set()
        for va in vals_a:
            norm_a = _normalize_region(va)
            best = None
            best_score = 0.0
            for vb in vals_b:
                if vb in matched_b:
                    continue
                norm_b = _normalize_region(vb)
                if norm_a == norm_b:
                    best = vb
                    best_score = 1.0
                    break
                score = _similarity(norm_a, norm_b)
                if score > best_score:
                    best_score = score
                    best = vb
            if best and best_score >= SIMILARITY_THRESHOLD:
                matched_b.add(best)
                suggestions.append(
                    {
                        "value_a": va,
                        "value_b": best,
                        "suggested_unified": va if len(va) <= len(best) else best,
                        "similarity": round(best_score, 3),
                        "method": "fuzzy",
                    }
                )
        return suggestions

    def available_time_points(
        self,
        dataset_ids: list[str],
        time_column_mappings: dict[str, str],
    ) -> dict:
        per_dataset: dict[str, list[str]] = {}
        for did in dataset_ids:
            col = time_column_mappings.get(did)
            if not col:
                continue
            df = self.datasets.read_dataframe(did)
            if col not in df.columns:
                continue
            values = sorted(
                [str(v) for v in df[col].dropna().unique()],
                reverse=True,
            )
            per_dataset[did] = values

        all_sets = [set(v) for v in per_dataset.values()]
        common = sorted(set.intersection(*all_sets)) if all_sets else []
        union = sorted(set.union(*all_sets)) if all_sets else []

        return {
            "per_dataset": per_dataset,
            "common": common,
            "union": union,
            "common_count": len(common),
            "union_count": len(union),
        }

    def execute_merge(
        self,
        *,
        dataset_ids: list[str],
        key_column_mappings: dict[str, str],
        join_type: str = "inner",
        time_column_mappings: dict[str, str] | None = None,
        selected_time_points: list[str] | None = None,
        topic_id: str,
        owner_user_id: str,
        dataset_name: str | None = None,
    ) -> dict:
        if join_type not in ("inner", "outer"):
            join_type = "inner"

        merged, source_info, final_key_name = build_merged_dataframe(
            self.datasets,
            dataset_ids=dataset_ids,
            key_column_mappings=key_column_mappings,
            join_type=join_type,
            time_column_mappings=time_column_mappings,
            selected_time_points=selected_time_points,
        )

        csv_bytes = merged.to_csv(index=False).encode("utf-8-sig")
        names = [self.datasets.get_dataset(did).name for did in dataset_ids]
        auto_name = dataset_name or f"결합: {' × '.join(names[:3])}"
        auto_name = auto_name[:80]

        result = self.datasets.create_uploaded_dataset(
            filename=f"merged_{uuid4().hex[:8]}.csv",
            content=csv_bytes,
            topic_id=topic_id,
            owner_user_id=owner_user_id,
            dataset_name=auto_name,
            source="자료 결합",
            source_note=f"{len(dataset_ids)}개 자료를 {join_type} join으로 결합 ({now_utc().strftime('%Y-%m-%d')})",
            description=(
                f"{', '.join(names[:3])} 자료를 '{final_key_name}' 기준으로 결합한 자료입니다. "
                f"전체 {len(merged)}행, {len(merged.columns)}열."
            ),
            time_range="결합 자료",
        )

        created = result.get("dataset", {})
        created_id = created.get("dataset_id")
        if created_id:
            from app.services.dataset_service import _load_uploaded_datasets, _upload_lock, _write_uploaded_datasets

            with _upload_lock:
                datasets = _load_uploaded_datasets()
                for ds in datasets:
                    if ds.dataset_id == created_id:
                        ds.merged = True
                        ds.merge_sources = source_info
                        ds.merge_key_column = final_key_name
                        break
                _write_uploaded_datasets(datasets)

        return {
            **result,
            "merge_info": {
                "source_datasets": source_info,
                "join_type": join_type,
                "key_column": final_key_name,
                "result_rows": len(merged),
                "result_columns": len(merged.columns),
                "selected_time_points": selected_time_points,
            },
        }
