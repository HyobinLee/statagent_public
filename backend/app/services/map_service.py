from __future__ import annotations

import math

import pandas as pd

from app.core.errors import AppError
from app.services.color_scales import MAX_CLASSES, MIN_CLASSES, known_scale, scale_info
from app.services.dataset_service import DatasetService

from app.services.region_codes import SIDO_REGIONS, region_info, region_name_to_code
from app.services.sgis_boundary import (
    LEVEL_LABELS as SGIS_LEVEL_LABELS,
)
from app.services.sgis_boundary import (
    PARENT_LEVEL,
    boundaries_enabled,
    fetch_regions,
    sido_sgis_code,
    sigungu_sgis_code,
)

__all__ = ["SIDO_REGIONS", "MapService", "region_name_to_code"]


def _quantile_breaks(values: list[float], n_classes: int = 5) -> list[float]:
    sorted_vals = sorted(v for v in values if math.isfinite(v))
    if not sorted_vals:
        return []
    breaks = []
    for i in range(1, n_classes):
        idx = int(len(sorted_vals) * i / n_classes)
        idx = min(idx, len(sorted_vals) - 1)
        breaks.append(sorted_vals[idx])
    return breaks


class MapService:
    def __init__(self, dataset_service: DatasetService | None = None) -> None:
        self.datasets = dataset_service or DatasetService()

    def available_map_levels(self) -> list[dict]:
        ready = boundaries_enabled()
        return [
            {
                "level": "sido",
                "display_name": "시도 (17개)",
                "description": "서울, 부산, 경기 등 광역자치단체 단위입니다.",
                "requires_level": None,
                "requires_label": None,
                "available": True,
                "unavailable_reason": None if ready else "경계 자료가 없어 지역 중심점에 원으로 표시합니다.",
            },
            {
                "level": "sigungu",
                "display_name": "시군구 (약 250개)",
                "description": "○○구, ○○시, ○○군 단위입니다. 광역자치단체를 하나 고른 뒤에 그립니다.",
                "requires_level": "sido",
                "requires_label": "시도",
                "available": ready,
                "unavailable_reason": None if ready else "SGIS 경계 연결이 설정되지 않았습니다.",
            },
            {
                "level": "emd",
                "display_name": "읍면동",
                "description": "○○동, ○○읍, ○○면 단위입니다. 기초자치단체를 하나 고른 뒤에 그립니다.",
                "requires_level": "sigungu",
                "requires_label": "시군구",
                "available": ready,
                "unavailable_reason": None if ready else "SGIS 경계 연결이 설정되지 않았습니다.",
            },
        ]

    def child_regions(self, level: str, parent_region: str | None = None) -> list[dict]:
        if level == "sido":
            return [{"name": region["name"], "short_name": region["short"]} for region in SIDO_REGIONS]
        if level != "sigungu":
            raise AppError(
                "MAP_LEVEL_UNSUPPORTED",
                "상위 지역 목록은 시도와 시군구까지만 제공합니다.",
                "시도 또는 시군구를 선택해 주세요.",
            )
        parent_code, _ = self.resolve_parent("sigungu", parent_region)
        return [
            {"name": record["name"], "short_name": record["short_name"]}
            for record in self.region_universe("sigungu", parent_code)
        ]

    def region_code_lookup(
        self,
        region_names: list[str],
        level: str = "sido",
    ) -> dict:
        results: list[dict] = []
        for name in region_names:
            code = region_name_to_code(name)
            info = region_info(code)
            results.append(
                {
                    "input_name": name,
                    "matched_code": code,
                    "matched_name": info["name"] if info else None,
                    "lat": info["lat"] if info else None,
                    "lng": info["lng"] if info else None,
                    "matched": code is not None,
                }
            )
        matched_count = sum(1 for r in results if r["matched"])
        return {
            "results": results,
            "matched_count": matched_count,
            "total_count": len(region_names),
            "match_rate": round(matched_count / len(region_names), 2) if region_names else 0,
        }

    def resolve_parent(self, level: str, parent_region: str | None) -> tuple[str | None, str]:
        if level == "sido":
            return None, ""

        parent_label = SGIS_LEVEL_LABELS.get(PARENT_LEVEL.get(level, ""), "상위 지역")
        name = str(parent_region or "").strip()
        if not name:
            raise AppError(
                "MAP_PARENT_REGION_REQUIRED",
                f"{SGIS_LEVEL_LABELS[level]} 지도는 {parent_label}를 먼저 정해야 그릴 수 있습니다.",
                f"어느 {parent_label}의 {SGIS_LEVEL_LABELS[level]}를 볼지 선택해 주세요.",
            )
        parts = name.split()
        if level == "emd" and len(parts) < 2:
            raise AppError(
                "MAP_PARENT_REGION_INVALID",
                f"읍면동 지도는 '시도 시군구' 형태로 {parent_label}를 정해야 합니다.",
                "예: '서울특별시 종로구'처럼 시도와 시군구를 함께 선택해 주세요.",
            )
        if not boundaries_enabled():
            raise AppError(
                "MAP_BOUNDARY_UNAVAILABLE",
                f"{SGIS_LEVEL_LABELS[level]} 경계 자료를 가져올 수 없습니다.",
                "시도 단위 지도를 사용하거나, 관리자에게 SGIS 연결 설정을 확인해 달라고 요청해 주세요.",
            )

        if level == "sigungu":
            code = sido_sgis_code(name)
        else:
            code = sigungu_sgis_code(parts[0], " ".join(parts[1:]))
        if not code:
            raise AppError(
                "MAP_PARENT_REGION_NOT_FOUND",
                f"'{name}'에 해당하는 {parent_label}를 찾지 못했습니다.",
                f"{parent_label} 이름을 목록에서 다시 선택해 주세요.",
            )
        return code, name

    def region_universe(self, level: str, parent_code: str | None) -> list[dict]:
        if level == "sido":
            regions = fetch_regions("sido") or []
            by_code = {record.get("region_code"): record for record in regions}
            return [
                {
                    "code": region["code"],
                    "name": region["name"],
                    "short_name": region["short"],
                    "lat": region["lat"],
                    "lng": region["lng"],
                    "has_boundary": region["code"] in by_code,
                }
                for region in SIDO_REGIONS
            ]

        records = fetch_regions(level, parent_code) or []
        return [
            {
                "code": record["sgis_code"],
                "name": record["name"],
                "short_name": record["short_name"],
                "lat": record.get("lat"),
                "lng": record.get("lng"),
                "has_boundary": True,
            }
            for record in records
        ]

    def _matcher(self, level: str, universe: list[dict]):
        if level == "sido":
            return lambda name: region_name_to_code(name)

        lookup: dict[str, str] = {}
        for region in universe:
            for key in (region["name"], region["short_name"]):
                lookup.setdefault(str(key).replace(" ", ""), region["code"])

        def match(name: str) -> str | None:
            return lookup.get(str(name or "").replace(" ", ""))

        return match

    def generate_choropleth(
        self,
        dataset_id: str,
        region_column: str,
        value_column: str,
        *,
        level: str = "sido",
        parent_region: str | None = None,
        time_column: str | None = None,
        time_point: str | None = None,
        n_classes: int = 5,
        color_scale: str | None = None,
        title: str | None = None,
    ) -> dict:
        if level not in SGIS_LEVEL_LABELS:
            raise AppError(
                "MAP_LEVEL_UNSUPPORTED",
                f"'{level}'는 지원하지 않는 지도 단위입니다.",
                "시도, 시군구, 읍면동 중에서 골라 주세요.",
            )
        parent_code, parent_name = self.resolve_parent(level, parent_region)
        universe = self.region_universe(level, parent_code)
        if not universe:
            raise AppError(
                "MAP_BOUNDARY_UNAVAILABLE",
                f"{SGIS_LEVEL_LABELS[level]} 경계 자료를 가져오지 못했습니다.",
                "잠시 후 다시 시도하거나 시도 단위 지도를 사용해 주세요.",
            )
        match_region = self._matcher(level, universe)
        by_code = {region["code"]: region for region in universe}

        dataset = self.datasets.get_dataset(dataset_id)
        df = self.datasets.read_dataframe(dataset_id)

        if region_column not in df.columns:
            raise AppError(
                "MAP_REGION_COLUMN_NOT_FOUND",
                f"'{region_column}' 컬럼을 찾을 수 없습니다.",
                "자료의 지역 컬럼을 확인해 주세요.",
            )
        if value_column not in df.columns:
            raise AppError(
                "MAP_VALUE_COLUMN_NOT_FOUND",
                f"'{value_column}' 컬럼을 찾을 수 없습니다.",
                "수치형 컬럼을 선택해 주세요.",
            )

        if time_column and time_point and time_column in df.columns:
            df = df[df[time_column].astype(str) == str(time_point)].copy()

        df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
        grouped = df.groupby(region_column, dropna=True)[value_column].mean().reset_index()

        regions_data: list[dict] = []
        values: list[float] = []
        for _, row in grouped.iterrows():
            region_name = str(row[region_column])
            value = row[value_column]
            if pd.isna(value):
                continue
            code = match_region(region_name)
            info = by_code.get(code) if code else None

            entry = {
                "region_name": region_name,
                "region_code": code,
                "value": round(float(value), 4),
                "lat": info["lat"] if info else None,
                "lng": info["lng"] if info else None,
                "matched": code is not None,
            }
            regions_data.append(entry)
            if math.isfinite(float(value)):
                values.append(float(value))

        if not regions_data:
            raise AppError(
                "MAP_NO_DATA",
                "지도에 표시할 데이터가 없습니다.",
                "지역 컬럼과 값 컬럼을 확인해 주세요.",
            )

        n_classes = min(max(n_classes, MIN_CLASSES), MAX_CLASSES)
        scale = scale_info(known_scale(color_scale), n_classes)
        colors = scale["colors"]
        breaks = _quantile_breaks(values, n_classes)
        for entry in regions_data:
            val = entry["value"]
            class_idx = 0
            for brk in breaks:
                if val > brk:
                    class_idx += 1
            entry["class_index"] = class_idx
            entry["color"] = colors[min(class_idx, len(colors) - 1)]

        legend: list[dict] = []
        all_breaks = [min(values)] + breaks + [max(values)]
        for i in range(n_classes):
            lo = all_breaks[i] if i < len(all_breaks) else 0
            hi = all_breaks[i + 1] if i + 1 < len(all_breaks) else 0
            legend.append(
                {
                    "class_index": i,
                    "min_value": round(lo, 2),
                    "max_value": round(hi, 2),
                    "color": colors[i],
                    "label": f"{round(lo, 1)} ~ {round(hi, 1)}",
                }
            )

        auto_title = title or f"{dataset.name} - {value_column} 지역별 분포"
        matched_count = sum(1 for r in regions_data if r["matched"])

        return {
            "success": True,
            "choropleth": {
                "title": auto_title,
                "level": level,
                "level_label": SGIS_LEVEL_LABELS[level],
                "parent_region": parent_name or None,
                "region_column": region_column,
                "value_column": value_column,
                "time_point": time_point,
                "regions": regions_data,
                "legend": legend,
                "n_classes": n_classes,
                "color_scale": scale,
                "dataset_id": dataset_id,
                "dataset_name": dataset.name,
            },
            "statistics": {
                "region_count": len(regions_data),
                "matched_count": matched_count,
                "unmatched_count": len(regions_data) - matched_count,
                "min_value": round(min(values), 4) if values else None,
                "max_value": round(max(values), 4) if values else None,
                "mean_value": round(sum(values) / len(values), 4) if values else None,
            },
            "warnings": self._choropleth_warnings(regions_data, matched_count),
        }

    def _choropleth_warnings(self, regions_data: list[dict], matched_count: int) -> list[str]:
        warnings: list[str] = []
        unmatched = [r for r in regions_data if not r["matched"]]
        if unmatched:
            names = ", ".join(r["region_name"] for r in unmatched[:5])
            warnings.append(f"지도에 매핑되지 않은 지역이 {len(unmatched)}개 있습니다: {names}")
        if matched_count < 5:
            warnings.append(
                "매핑된 지역이 5개 미만입니다. 지역명을 정규화하면 더 많은 데이터를 지도에 표시할 수 있습니다."
            )
        return warnings
