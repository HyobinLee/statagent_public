import ast
import json
import keyword
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi.encoders import jsonable_encoder

from app.config import get_settings
from app.core.errors import AppError
from app.core.time import now_utc
from app.models.dataset import (
    COLUMN_ROLE_LABELS,
    Dataset,
    DatasetColumn,
    DatasetNote,
    RecommendedAnalysis,
)
from app.services.dataset_storage import DatasetObjectStorage, is_gcs_uri

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_ROWS = 20000
MAX_UPLOAD_COLUMNS = 40
SHEET_MAX_LIMIT = 200
MAX_ANALYSIS_SELECTED_ROWS = 5000
MAX_ROW_FILTERS = 8
MAX_ROW_FILTER_VALUES = 50
UPLOAD_MANIFEST = "uploaded_datasets.json"
UPLOAD_DIR = "uploads"
UPLOAD_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")

_upload_lock = RLock()
_analysis_row_selection: ContextVar[dict[str, tuple[int, ...]] | None] = ContextVar(
    "analysis_row_selection",
    default=None,
)


@lru_cache
def _load_datasets() -> list[Dataset]:
    path = get_settings().data_dir / "datasets.json"
    with path.open("r", encoding="utf-8") as file:
        return [Dataset(**item) for item in json.load(file)]


def _upload_manifest_path() -> Path:
    return get_settings().local_data_dir / UPLOAD_MANIFEST


def _load_uploaded_datasets() -> list[Dataset]:
    from app.repositories.factory import get_repository

    setting = get_repository().get_setting(UPLOAD_MANIFEST)
    if setting:
        value = setting.get("value", {})
        raw_items = value.get("datasets", []) if isinstance(value, dict) else []
        return [Dataset(**item) for item in raw_items]

    path = _upload_manifest_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        return [Dataset(**item) for item in json.load(file)]


def _write_uploaded_datasets(datasets: list[Dataset]) -> None:
    from app.repositories.factory import get_repository

    encoded = [jsonable_encoder(dataset) for dataset in datasets]
    get_repository().upsert_setting(UPLOAD_MANIFEST, {"datasets": encoded})
    path = _upload_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(encoded, file, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _normalize_columns(columns: list[object]) -> list[str]:
    normalized: list[str] = []
    seen: dict[str, int] = {}
    for index, raw_name in enumerate(columns, start=1):
        name = str(raw_name).replace("\ufeff", "").strip()
        if not name or name.lower().startswith("unnamed:"):
            name = f"column_{index}"
        name = " ".join(name.split())
        base = name
        count = seen.get(base, 0)
        if count:
            name = f"{base}_{count + 1}"
        seen[base] = count + 1
        normalized.append(name)
    return normalized


def _safe_column_name(value: str) -> str:
    name = _normalize_columns([value])[0]
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"[^0-9A-Za-z_\u3131-\u318e\uac00-\ud7a3]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "derived_column"


def _read_csv_bytes(content: bytes) -> tuple[pd.DataFrame, str]:
    last_error: Exception | None = None
    for encoding in UPLOAD_ENCODINGS:
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            raise AppError(
                "CSV_EMPTY_OR_UNPARSABLE",
                "CSV 파일을 표 형태로 읽을 수 없습니다.",
                "쉼표 구분 CSV인지, 첫 줄에 컬럼명이 있고 그 아래에 데이터가 있는지 확인해 주세요.",
            ) from exc
    raise AppError(
        "CSV_ENCODING_UNSUPPORTED",
        "CSV 파일의 문자 인코딩을 읽을 수 없습니다.",
        "UTF-8 또는 CP949 형식의 CSV로 저장한 뒤 다시 업로드해 주세요.",
    ) from last_error


def _infer_unit(column_name: str) -> str | None:
    lowered = column_name.lower()
    if lowered in {"year", "yyyy"} or "연도" in column_name:
        return "년"
    if "%" in column_name or "percent" in lowered or "ratio" in lowered or "비율" in column_name:
        return "%"
    if "원" in column_name or "krw" in lowered or "cost" in lowered or "price" in lowered:
        return "원"
    if "day" in lowered or "일수" in column_name:
        return "일"
    return None


def _columns_from_dataframe(
    df: pd.DataFrame,
    *,
    column_display_names: dict[str, str] | None = None,
    column_descriptions: dict[str, str] | None = None,
    column_units: dict[str, str | None] | None = None,
    column_extras: dict[str, dict] | None = None,
) -> list[DatasetColumn]:
    column_display_names = column_display_names or {}
    column_descriptions = column_descriptions or {}
    column_units = column_units or {}
    column_extras = column_extras or {}
    columns: list[DatasetColumn] = []
    for column_name in df.columns:
        series = df[column_name]
        non_missing = series.dropna()
        numeric = pd.to_numeric(non_missing, errors="coerce")
        numeric_ratio = 0 if len(non_missing) == 0 else float(numeric.notna().sum() / len(non_missing))
        dtype = "numeric" if numeric_ratio >= 0.85 and numeric.notna().sum() > 0 else "categorical"
        if dtype == "numeric":
            df[column_name] = pd.to_numeric(series, errors="coerce")
        extras = column_extras.get(column_name) or {}
        columns.append(
            DatasetColumn(
                name=column_name,
                display_name=column_display_names.get(column_name) or column_name,
                dtype=dtype,
                description=column_descriptions.get(column_name) or f"자료의 '{column_name}' 항목",
                unit=column_units.get(column_name, _infer_unit(column_name)),
                value_labels=extras.get("value_labels") or [],
                warnings=extras.get("warnings") or [],
                secondary=bool(extras.get("secondary")),
            )
        )
    return columns


def _is_likely_order_column(column: DatasetColumn) -> bool:
    lowered = column.name.lower()
    keywords = ("year", "date", "month", "time", "day", "연도", "날짜", "월", "일자", "시점")
    return any(keyword in lowered or keyword in column.display_name for keyword in keywords)


LATITUDE_KEYWORDS = ("위도", "latitude", "lat", "y좌표")
LONGITUDE_KEYWORDS = ("경도", "longitude", "lon", "lng", "x좌표")


def _match_coordinate_column(
    columns: list[DatasetColumn], keywords: tuple[str, ...], valid_range: tuple[float, float], df: pd.DataFrame
) -> DatasetColumn | None:
    for column in columns:
        if column.dtype != "numeric":
            continue
        lowered = column.name.lower()
        haystack = f"{lowered} {column.display_name.lower()}"
        if not any(keyword in haystack for keyword in keywords):
            continue
        values = pd.to_numeric(df[column.name], errors="coerce").dropna()
        if values.empty or not values.between(*valid_range).all():
            continue
        return column
    return None


def _find_coordinate_columns(
    df: pd.DataFrame, columns: list[DatasetColumn]
) -> tuple[DatasetColumn, DatasetColumn] | None:
    latitude = _match_coordinate_column(columns, LATITUDE_KEYWORDS, (-90, 90), df)
    longitude = _match_coordinate_column(columns, LONGITUDE_KEYWORDS, (-180, 180), df)
    if latitude and longitude and latitude.name != longitude.name:
        return latitude, longitude
    return None


MIN_REGION_MATCH_RATIO = 0.7


def _find_region_column(df: pd.DataFrame, columns: list[DatasetColumn]) -> DatasetColumn | None:
    from app.services.region_codes import region_name_to_code

    for column in columns:
        if column.dtype != "categorical" or column.name not in df.columns:
            continue
        values = df[column.name].dropna().astype(str).unique()
        if len(values) < 2:
            continue
        matched = sum(1 for value in values if region_name_to_code(value))
        if matched / len(values) >= MIN_REGION_MATCH_RATIO:
            return column
    return None


def _find_group_column(df: pd.DataFrame, columns: list[DatasetColumn]) -> DatasetColumn | None:
    candidates = [
        (column, int(df[column.name].dropna().nunique())) for column in columns if column.dtype == "categorical"
    ]
    valid = [(column, count) for column, count in candidates if 2 <= count <= 8]
    if not valid:
        return None
    return min(valid, key=lambda item: item[1])[0]


MAX_COMFORTABLE_CATEGORIES = 8
MAX_COMPARABLE_GROUPS = 5
DESCRIPTIVE_STATISTICS = ["mean", "median", "std", "min", "max"]


@dataclass(frozen=True)
class DatasetRoleContext:
    group_column: DatasetColumn | None
    coordinates: tuple[DatasetColumn, DatasetColumn] | None
    ordered: DatasetColumn | None
    region_column: DatasetColumn | None = None

    @property
    def coordinate_names(self) -> set[str]:
        return {self.coordinates[0].name, self.coordinates[1].name} if self.coordinates else set()


def dataset_role_context(df: pd.DataFrame, columns: list[DatasetColumn]) -> DatasetRoleContext:
    return DatasetRoleContext(
        group_column=_find_group_column(df, columns),
        coordinates=_find_coordinate_columns(df, columns),
        ordered=next((column for column in columns if _is_likely_order_column(column)), None),
        region_column=_find_region_column(df, columns),
    )


def _tool_allows_level(tool_name: str, school_level: str | None) -> bool:
    if school_level not in {"middle", "high"}:
        return True
    from app.tools.registry import get_tool

    definition = get_tool(tool_name)
    return definition is None or school_level in definition.allowed_levels


def _column_role(
    df: pd.DataFrame,
    column: DatasetColumn,
    coordinate_names: set[str],
    region_name: str | None = None,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    series = df[column.name] if column.name in df.columns else None
    unique_count = 0 if series is None else int(series.nunique(dropna=True))
    row_count = 0 if series is None else int(len(series))

    if series is not None and unique_count == 0:
        return "reference", ["값이 모두 비어 있어 분석에 쓸 수 없습니다."]
    if series is not None and unique_count == 1:
        return "reference", []

    if column.name in coordinate_names:
        return "location", warnings
    if region_name and column.name == region_name:
        return "location", warnings
    if _is_likely_order_column(column):
        return "period", warnings
    if column.dtype == "numeric":
        return "measure", warnings

    if row_count >= 2 and unique_count == row_count:
        return "identifier", warnings
    if unique_count > MAX_COMFORTABLE_CATEGORIES:
        warnings.append(f"고유값이 {unique_count}개로 많아 묶음 기준을 정하면 비교하기 쉽습니다.")
    return "group", warnings


def _column_suggestions(
    df: pd.DataFrame,
    columns: list[DatasetColumn],
    column: DatasetColumn,
    role: str,
    context: DatasetRoleContext,
    school_level: str | None,
) -> list[dict]:
    suggestions: list[dict] = []

    def add(label: str, why: str, tool_name: str, tool_args: dict) -> None:
        if not _tool_allows_level(tool_name, school_level):
            return
        suggestions.append({"label": label, "why": why, "tool_name": tool_name, "tool_args": tool_args})

    def group_size(candidate: DatasetColumn) -> int:
        if candidate.name not in df.columns:
            return 0
        return int(df[candidate.name].dropna().nunique())

    numeric = [item for item in columns if item.dtype == "numeric" and item.name not in context.coordinate_names]
    group = context.group_column

    if role == "measure":
        add(
            "요약 통계량 보기",
            "평균·중앙값과 퍼진 정도를 한 번에 확인합니다.",
            "compute_descriptive_stats",
            {"columns": [column.name], "statistics": DESCRIPTIVE_STATISTICS},
        )
        add(
            "값이 어디에 몰려 있는지 보기",
            "히스토그램으로 분포의 모양을 확인합니다.",
            "plot_histogram",
            {"column": column.name, "bins": 8, "title": f"{column.display_name} 분포"},
        )
        if group and group.name != column.name and group_size(group) <= MAX_COMPARABLE_GROUPS:
            add(
                f"{group.display_name}별로 나눠 분포 비교하기",
                "집단을 나란히 놓고 중앙값과 퍼진 정도를 비교합니다.",
                "plot_boxplot",
                {
                    "columns": [column.name],
                    "group_by": group.name,
                    "title": f"{group.display_name}별 {column.display_name} 분포",
                },
            )
            add(
                f"{group.display_name}별 요약 통계량 비교하기",
                "그림에서 본 차이를 숫자로 확인합니다.",
                "compute_descriptive_stats",
                {"columns": [column.name], "statistics": DESCRIPTIVE_STATISTICS, "group_by": group.name},
            )
    elif role == "group":
        add(
            "각 값이 몇 번 나오는지 세기",
            "도수분포표로 어떤 값이 많은지 확인합니다.",
            "create_frequency_table",
            {"column": column.name},
        )
        value_column = next((item for item in numeric if item.name != column.name), None)
        if value_column and group_size(column) <= MAX_COMPARABLE_GROUPS:
            add(
                f"이 기준으로 {value_column.display_name} 분포 비교하기",
                "집단을 나란히 놓고 중앙값과 퍼진 정도를 비교합니다.",
                "plot_boxplot",
                {
                    "columns": [value_column.name],
                    "group_by": column.name,
                    "title": f"{column.display_name}별 {value_column.display_name} 분포",
                },
            )
            add(
                f"이 기준으로 {value_column.display_name} 요약 통계량 비교하기",
                "집단별 대표값과 산포도를 표로 비교합니다.",
                "compute_descriptive_stats",
                {
                    "columns": [value_column.name],
                    "statistics": DESCRIPTIVE_STATISTICS,
                    "group_by": column.name,
                },
            )
    elif role == "period":
        value_column = next((item for item in numeric), None)
        if value_column:
            add(
                f"시간에 따른 {value_column.display_name} 변화 보기",
                "꺾은선그래프로 흐름을 확인합니다.",
                "plot_line",
                {
                    "x_col": column.name,
                    "y_col": value_column.name,
                    "title": f"{column.display_name}별 {value_column.display_name}",
                },
            )
    elif role == "location" and context.coordinates:
        latitude, longitude = context.coordinates
        value_column = next((item for item in numeric), None)
        if value_column:
            add(
                "지도 위에 값 표시하기",
                "값이 큰 지점이 한곳에 몰려 있는지 지도에서 확인합니다.",
                "plot_map",
                {
                    "lat_col": latitude.name,
                    "lon_col": longitude.name,
                    "color_col": value_column.name,
                    "title": f"지도 위 {value_column.display_name} 분포",
                },
            )
    elif role == "location" and context.region_column and column.name == context.region_column.name:
        value_column = next((item for item in numeric), None)
        if value_column:
            add(
                f"지역별 {value_column.display_name} 지도로 보기",
                "값이 높은 지역이 어디에 몰려 있는지 지도에서 확인합니다.",
                "plot_choropleth",
                {
                    "region_col": column.name,
                    "value_col": value_column.name,
                    "map_level": "sido",
                    "title": f"{column.display_name}별 {value_column.display_name}",
                },
            )
            add(
                f"지역별 {value_column.display_name} 막대그래프",
                "지도에서 본 순서를 정확한 값으로 다시 확인합니다.",
                "plot_bar",
                {
                    "category_col": column.name,
                    "value_col": value_column.name,
                    "sort_order": "desc",
                    "title": f"{column.display_name}별 {value_column.display_name}",
                },
            )
    return suggestions[:3]


def describe_columns(df: pd.DataFrame, columns: list[DatasetColumn], school_level: str | None = None) -> list[dict]:
    context = dataset_role_context(df, columns)

    described: list[dict] = []
    for column in columns:
        role, warnings = _column_role(
            df, column, context.coordinate_names, context.region_column.name if context.region_column else None
        )
        if column.secondary:
            role = "reference"
        payload = column.model_dump()
        payload["role"] = column.role or role
        payload["role_label"] = column.role_label or COLUMN_ROLE_LABELS.get(payload["role"], "기타")
        payload["warnings"] = [*column.warnings, *(item for item in warnings if item not in column.warnings)]
        payload["secondary"] = column.secondary or payload["role"] == "reference"
        payload["suggestions"] = _column_suggestions(df, columns, column, payload["role"], context, school_level)
        described.append(payload)
    return described


def _recommend_analyses(df: pd.DataFrame, columns: list[DatasetColumn]) -> list[dict]:
    numeric = [column for column in columns if column.dtype == "numeric"]
    categorical = [column for column in columns if column.dtype == "categorical"]
    context = dataset_role_context(df, columns)
    ordered = context.ordered
    recommendations: list[dict] = []

    def add(tool_name: str, label: str, tool_args: dict, description: str) -> None:
        key = (tool_name, json.dumps(tool_args, ensure_ascii=False, sort_keys=True))
        if any(item["_key"] == key for item in recommendations):
            return
        recommendations.append(
            {
                "_key": key,
                "tool_name": tool_name,
                "label": label,
                "tool_args": tool_args,
                "description": description,
            }
        )

    coordinates = context.coordinates
    group_column = context.group_column
    if coordinates:
        latitude, longitude = coordinates
        coordinate_names = context.coordinate_names
        numeric = [column for column in numeric if column.name not in coordinate_names]
        value_column = numeric[0] if numeric else None
        if value_column:
            tool_args = {
                "lat_col": latitude.name,
                "lon_col": longitude.name,
                "color_col": value_column.name,
                "title": f"지도 위 {value_column.display_name} 분포",
            }
            if group_column:
                tool_args["group_by"] = group_column.name
            add(
                "plot_map",
                f"지도 위 {value_column.display_name} 분포",
                tool_args,
                "값이 큰 지점이 특정 구역에 몰려 있는지 지도에서 확인합니다.",
            )
    elif context.region_column:
        region_column = context.region_column
        value_column = numeric[0] if numeric else None
        if value_column:
            add(
                "plot_choropleth",
                f"{region_column.display_name}별 {value_column.display_name} 지도",
                {
                    "region_col": region_column.name,
                    "value_col": value_column.name,
                    "map_level": "sido",
                    "title": f"{region_column.display_name}별 {value_column.display_name}",
                },
                "값이 높은 지역이 지도의 어디에 몰려 있는지 확인합니다.",
            )

    distribution_pair: tuple[str, str] | None = None
    if group_column and numeric and df[group_column.name].dropna().nunique() <= 5:
        distribution_pair = (group_column.name, numeric[0].name)
        add(
            "plot_boxplot",
            f"{group_column.display_name}별 {numeric[0].display_name} 분포 비교(상자그림)",
            {
                "columns": [numeric[0].name],
                "group_by": group_column.name,
                "title": f"{group_column.display_name}별 {numeric[0].display_name} 분포",
            },
            "집단을 나란히 놓고 중앙값, 사분위수, 퍼짐의 차이를 한눈에 비교합니다.",
        )
        add(
            "compute_descriptive_stats",
            f"{group_column.display_name}별 {numeric[0].display_name} 요약 통계량 비교",
            {
                "columns": [numeric[0].name],
                "statistics": ["mean", "median", "std", "min", "max"],
                "group_by": group_column.name,
            },
            "집단별 대표값과 산포도를 표로 비교해 상자그림에서 본 차이를 숫자로 확인합니다.",
        )

    if group_column and len(numeric) >= 2 and len(df) >= 10:
        add(
            "compute_grouped_correlation",
            f"{group_column.display_name}별 상관계수 비교",
            {
                "x_column": numeric[0].name,
                "y_column": numeric[1].name,
                "group_by": group_column.name,
            },
            "전체 상관계수가 모든 집단에서 똑같이 성립하는지 비교합니다.",
        )
        add(
            "plot_grouped_scatter",
            f"{group_column.display_name}별 산점도 비교",
            {
                "x_col": numeric[0].name,
                "y_col": numeric[1].name,
                "group_by": group_column.name,
                "title": f"{group_column.display_name}별 {numeric[0].display_name}와 {numeric[1].display_name}",
            },
            "집단별 추세선의 방향이 서로 다른지 눈으로 확인합니다.",
        )

    if ordered:
        y_column = next((column for column in numeric if column.name != ordered.name), None)
        if y_column:
            add(
                "plot_line",
                f"{ordered.display_name}별 {y_column.display_name} 변화",
                {
                    "x_col": ordered.name,
                    "y_col": y_column.name,
                    "title": f"{ordered.display_name}별 {y_column.display_name}",
                },
                "시간이나 순서에 따른 변화 흐름을 먼저 확인합니다.",
            )

    if len(numeric) >= 2:
        add(
            "plot_scatter",
            f"{numeric[0].display_name}와 {numeric[1].display_name} 관계",
            {
                "x_col": numeric[0].name,
                "y_col": numeric[1].name,
                "show_trendline": True,
                "title": f"{numeric[0].display_name}와 {numeric[1].display_name}의 관계",
            },
            "두 수치형 항목이 함께 움직이는지 산점도로 확인합니다.",
        )
        if len(df) >= 10:
            add(
                "compute_correlation",
                "상관계수 계산",
                {"x_column": numeric[0].name, "y_column": numeric[1].name},
                "두 수치형 항목의 선형 관계 정도를 계산합니다.",
            )

    if categorical and numeric:
        category = next(
            (column for column in categorical if df[column.name].dropna().nunique() <= 20),
            categorical[0],
        )
        if distribution_pair != (category.name, numeric[0].name):
            add(
                "plot_bar",
                f"{category.display_name}별 {numeric[0].display_name} 비교",
                {
                    "category_col": category.name,
                    "value_col": numeric[0].name,
                    "title": f"{category.display_name}별 {numeric[0].display_name}",
                },
                "범주별 합계나 크기 차이를 막대그래프로 비교합니다.",
            )
        if df[category.name].dropna().nunique() <= 5:
            add(
                "plot_boxplot",
                f"{category.display_name}별 {numeric[0].display_name} 분포",
                {
                    "columns": [numeric[0].name],
                    "group_by": category.name,
                    "title": f"{category.display_name}별 {numeric[0].display_name} 분포",
                },
                "범주별 중앙값과 퍼짐 차이를 함께 살펴봅니다.",
            )

    if numeric:
        add(
            "compute_descriptive_stats",
            f"{numeric[0].display_name} 요약 통계",
            {"columns": [numeric[0].name], "statistics": ["mean", "median", "min", "max", "std"]},
            "대표값과 산포도를 계산해 자료의 전반적인 특징을 정리합니다.",
        )
        add(
            "plot_histogram",
            f"{numeric[0].display_name} 분포",
            {"column": numeric[0].name, "bins": 8, "title": f"{numeric[0].display_name} 분포"},
            "값이 어느 구간에 많이 모여 있는지 확인합니다.",
        )

    if categorical and not numeric:
        add(
            "create_frequency_table",
            f"{categorical[0].display_name} 도수분포표",
            {"column": categorical[0].name},
            "범주가 얼마나 자주 나타나는지 표로 정리합니다.",
        )

    return [{key: value for key, value in item.items() if key != "_key"} for item in recommendations[:5]]


def _build_processing_plan(df: pd.DataFrame, columns: list[DatasetColumn], analyses: list[dict], encoding: str) -> dict:
    missing_total = int(df.isna().sum().sum())
    numeric_count = sum(1 for column in columns if column.dtype == "numeric")
    categorical_count = len(columns) - numeric_count
    cleaning_suggestions = []
    if missing_total:
        cleaning_suggestions.append(
            "결측치가 있는 행은 분석 전에 빈칸의 의미를 확인하고, 필요한 경우 제외 기준을 정합니다."
        )
    else:
        cleaning_suggestions.append("큰 결측은 보이지 않아 바로 요약 통계와 그래프 후보를 검토할 수 있습니다.")
    wide_categories = [
        column.display_name
        for column in columns
        if column.dtype == "categorical" and df[column.name].dropna().nunique() > 20
    ]
    if wide_categories:
        cleaning_suggestions.append(
            f"{', '.join(wide_categories[:3])} 항목은 범주가 많아 묶음 기준을 먼저 정하면 좋습니다."
        )
    if numeric_count == 0:
        cleaning_suggestions.append("수치형으로 읽힌 항목이 없어 도수분포표나 범주 비교 중심으로 탐구를 이어갑니다.")

    analysis_strategy = [analysis["description"] for analysis in analyses[:3]]
    if not analysis_strategy:
        analysis_strategy = ["컬럼 수나 값의 형태가 부족해 먼저 자료 구조를 점검합니다."]

    return {
        "role_name": "AI 데이터 처리 코치",
        "message": "자료의 컬럼 유형을 추정하고, 현재 탐구 주제에 이어질 분석 후보를 골랐습니다.",
        "data_profile": {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "numeric_column_count": numeric_count,
            "categorical_column_count": categorical_count,
            "missing_count": missing_total,
            "encoding": encoding,
        },
        "cleaning_suggestions": cleaning_suggestions[:4],
        "analysis_strategy": analysis_strategy,
        "recommended_analyses": analyses,
        "guardrail": "AI 제안은 처리 방향과 관찰 질문만 제공하며, 학생의 결론을 대신 작성하지 않습니다.",
    }


def _ai_recommended_analyses(
    dataset: Dataset,
    fallback: list[dict],
    school_level: str | None = None,
) -> list[dict]:
    try:
        from app.models.project import normalize_school_level
        from app.services.ai_guide_service import get_guide_service

        options = get_guide_service().analysis_options(
            dataset,
            student_level=normalize_school_level(school_level) or "middle_high",
        )
    except AppError:
        return fallback
    valid_options = []
    for option in options[:5]:
        if not isinstance(option, dict):
            continue
        tool_name = str(option.get("tool_name") or "").strip()
        label = str(option.get("label") or "").strip()
        description = str(option.get("description") or "").strip()
        tool_args = option.get("tool_args") if isinstance(option.get("tool_args"), dict) else {}
        if tool_name and label and description:
            tool_args.pop("dataset_id", None)
            valid_options.append(
                {
                    "tool_name": tool_name,
                    "label": label,
                    "tool_args": tool_args,
                    "description": description,
                }
            )
    return valid_options or fallback


def _json_safe_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    safe = df.astype(object).where(pd.notna(df), None)
    return safe.to_dict(orient="records")


def _is_identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def _replace_caret_operator(expression: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in expression:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quote:
            result.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            result.append(char)
            continue
        if char == "^" and quote is None:
            result.append("**")
        else:
            result.append(char)
    return "".join(result)


class DatasetService:
    def list_datasets(self) -> list[Dataset]:
        return _load_datasets() + _load_uploaded_datasets()

    def list_for_topic(self, topic_id: str, owner_user_id: str | None = None) -> list[Dataset]:
        uploaded = [dataset for dataset in _load_uploaded_datasets() if dataset.topic_id == topic_id]
        if owner_user_id:
            uploaded = [
                dataset for dataset in uploaded if not dataset.owner_user_id or dataset.owner_user_id == owner_user_id
            ]
        curated = [dataset for dataset in _load_datasets() if dataset.curated and dataset.topic_id == topic_id]
        return curated + uploaded

    def get_dataset(self, dataset_id: str) -> Dataset:
        for dataset in self.list_datasets():
            if dataset.dataset_id == dataset_id:
                return dataset
        raise AppError(
            "DATASET_NOT_FOUND",
            "자료를 찾을 수 없습니다.",
            "자료 목록을 다시 선택해 주세요.",
            404,
        )

    def csv_path(self, dataset_id: str) -> Path:
        dataset = self.get_dataset(dataset_id)
        if dataset.uploaded and is_gcs_uri(dataset.csv_path):
            storage = DatasetObjectStorage()
            cache_path = storage.local_cache_path(dataset.dataset_id)
            return storage.download_file(dataset.csv_path, cache_path)
        if dataset.uploaded:
            return get_settings().local_data_dir / dataset.csv_path
        return get_settings().data_dir / dataset.csv_path

    def read_dataframe(self, dataset_id: str) -> pd.DataFrame:
        path = self.csv_path(dataset_id)
        if not path.exists():
            raise AppError(
                "CSV_NOT_FOUND",
                "자료 파일을 찾을 수 없습니다.",
                "업로드 또는 KOSIS 가져오기 manifest와 저장소 경로를 확인해 주세요.",
                500,
            )
        df = pd.read_csv(path)
        active_selection = (_analysis_row_selection.get() or {}).get(dataset_id)
        if active_selection:
            return df.iloc[list(active_selection)].reset_index(drop=True)
        return df

    def normalize_analysis_row_indices(self, dataset_id: str, row_indices: list[Any] | None) -> list[int]:
        if not row_indices:
            return []
        normalized: list[int] = []
        for raw_index in row_indices:
            try:
                row_index = int(raw_index)
            except (TypeError, ValueError) as exc:
                raise AppError(
                    "ANALYSIS_ROW_INDEX_INVALID",
                    "분석할 행 번호가 올바르지 않습니다.",
                    "자료 표를 새로고침한 뒤 행을 다시 선택해 주세요.",
                ) from exc
            if row_index < 0:
                raise AppError(
                    "ANALYSIS_ROW_INDEX_INVALID",
                    "분석할 행 번호가 올바르지 않습니다.",
                    "자료 표를 새로고침한 뒤 행을 다시 선택해 주세요.",
                )
            if row_index not in normalized:
                normalized.append(row_index)
        if len(normalized) > MAX_ANALYSIS_SELECTED_ROWS:
            raise AppError(
                "ANALYSIS_ROW_SELECTION_TOO_LARGE",
                f"행 단위 분석 대상은 최대 {MAX_ANALYSIS_SELECTED_ROWS:,}행까지 선택할 수 있습니다.",
                "조건에 맞는 핵심 행만 남기거나 전체 자료 분석을 사용해 주세요.",
            )
        row_count = len(pd.read_csv(self.csv_path(dataset_id)))
        invalid = [row_index for row_index in normalized if row_index >= row_count]
        if invalid:
            raise AppError(
                "ANALYSIS_ROW_INDEX_OUT_OF_RANGE",
                f"{invalid[0] + 1}번째 행은 현재 자료 범위를 벗어났습니다.",
                "자료 표를 새로고침한 뒤 행을 다시 선택해 주세요.",
            )
        return sorted(normalized)

    def normalize_row_filters(
        self,
        dataset_id: str,
        filters: dict[str, Any] | None,
    ) -> dict[str, dict[str, list[str] | str]]:
        if not filters:
            return {}
        if not isinstance(filters, dict):
            raise AppError(
                "ANALYSIS_FILTER_INVALID",
                "자료 필터 형식이 올바르지 않습니다.",
                "자료 표의 필터를 초기화한 뒤 다시 시도해 주세요.",
            )
        dataset = self.get_dataset(dataset_id)
        available_columns = {column.name for column in dataset.columns}
        normalized: dict[str, dict[str, list[str] | str]] = {}
        for raw_column, raw_filter in list(filters.items())[:MAX_ROW_FILTERS]:
            column = str(raw_column or "").strip()
            if not column or column not in available_columns:
                raise AppError(
                    "ANALYSIS_FILTER_INVALID_COLUMN",
                    f"'{column}' 컬럼은 이 자료에 없습니다.",
                    "자료 표를 새로고침한 뒤 필터를 다시 선택해 주세요.",
                )
            values: list[str] = []
            query = ""
            if isinstance(raw_filter, dict):
                raw_values = raw_filter.get("values", [])
                query = str(raw_filter.get("query", "") or "").strip()[:120]
            else:
                raw_values = raw_filter
            if isinstance(raw_values, (str, int, float)):
                raw_values = [raw_values]
            if isinstance(raw_values, list):
                for value in raw_values[:MAX_ROW_FILTER_VALUES]:
                    text = str(value).strip()
                    if text and text not in values:
                        values.append(text)
            entry: dict[str, list[str] | str] = {}
            if values:
                entry["values"] = values
            if query:
                entry["query"] = query
            if entry:
                normalized[column] = entry
        return normalized

    def _apply_row_filters(self, df: pd.DataFrame, filters: dict[str, dict[str, list[str] | str]]) -> pd.DataFrame:
        if not filters:
            return df
        mask = pd.Series([True] * len(df), index=df.index)
        for column, criteria in filters.items():
            series = df[column].astype("string").fillna("")
            values = criteria.get("values") if isinstance(criteria, dict) else None
            query = criteria.get("query") if isinstance(criteria, dict) else None
            column_mask = pd.Series([True] * len(df), index=df.index)
            if isinstance(values, list) and values:
                allowed = {str(value).strip() for value in values}
                column_mask &= series.isin(allowed)
            if isinstance(query, str) and query.strip():
                column_mask &= series.str.contains(re.escape(query.strip()), case=False, na=False)
            mask &= column_mask
        return df[mask]

    def row_indices_for_filters(self, dataset_id: str, filters: dict[str, dict[str, list[str] | str]]) -> list[int]:
        if not filters:
            return []
        df = pd.read_csv(self.csv_path(dataset_id))
        filtered = self._apply_row_filters(df, filters)
        indices = [int(index) for index in filtered.index]
        if len(indices) > MAX_ANALYSIS_SELECTED_ROWS:
            raise AppError(
                "ANALYSIS_FILTER_TOO_BROAD",
                f"필터로 선택된 행이 {MAX_ANALYSIS_SELECTED_ROWS:,}행을 넘습니다.",
                "필터 조건을 더 좁히거나 전체 자료 분석을 사용해 주세요.",
            )
        return indices

    @contextmanager
    def analysis_row_scope(self, dataset_id: str, row_indices: list[int]):
        if not row_indices:
            yield
            return
        current = dict(_analysis_row_selection.get() or {})
        current[dataset_id] = tuple(row_indices)
        token = _analysis_row_selection.set(current)
        try:
            yield
        finally:
            _analysis_row_selection.reset(token)

    def _assert_uploaded_owner(self, dataset: Dataset, owner_user_id: str) -> None:
        if not dataset.uploaded:
            raise AppError(
                "DATASET_NOT_EDITABLE",
                "기본 예시 자료는 직접 수정할 수 없습니다.",
                "CSV를 업로드하거나 KOSIS에서 가져온 자료를 수정해 주세요.",
                403,
            )
        if dataset.owner_user_id and dataset.owner_user_id != owner_user_id:
            raise AppError(
                "FORBIDDEN_DATASET",
                "다른 학생의 자료는 수정할 수 없습니다.",
                "현재 계정에서 가져온 자료를 선택해 주세요.",
                403,
            )

    def assert_read_access(self, dataset_id: str, user: Any) -> None:
        dataset = self.get_dataset(dataset_id)
        if (
            dataset.uploaded
            and dataset.owner_user_id
            and getattr(user, "role", None) == "student"
            and dataset.owner_user_id != getattr(user, "user_id", None)
        ):
            from app.repositories.factory import get_repository

            user_projects = [
                project
                for project in get_repository().list_projects()
                if project.owner_user_id == getattr(user, "user_id", None)
            ]
            if any(dataset_id in (project.dataset_ids or []) for project in user_projects):
                return
            raise AppError(
                "FORBIDDEN_DATASET",
                "다른 학생의 자료를 볼 수 없습니다.",
                "현재 계정에서 가져온 자료를 선택해 주세요.",
                403,
            )

    def _write_dataframe(self, dataset: Dataset, df: pd.DataFrame) -> None:
        path = self.csv_path(dataset.dataset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        if dataset.uploaded and is_gcs_uri(dataset.csv_path):
            DatasetObjectStorage().upload_file(path, dataset.csv_path)

    def delete_uploaded_dataset(self, dataset_id: str, owner_user_id: str | None = None) -> bool:
        dataset = self.get_dataset(dataset_id)
        if not dataset.uploaded:
            return False
        if owner_user_id and dataset.owner_user_id and dataset.owner_user_id != owner_user_id:
            return False
        with _upload_lock:
            remaining = [item for item in _load_uploaded_datasets() if item.dataset_id != dataset_id]
            _write_uploaded_datasets(remaining)
        if is_gcs_uri(dataset.csv_path):
            try:
                DatasetObjectStorage().delete_file(dataset.csv_path)
            except Exception as exc:
                raise AppError(
                    "DATASET_OBJECT_DELETE_FAILED",
                    "자료 CSV 객체를 삭제하지 못했습니다.",
                    "관리자에게 Cloud Storage 권한과 객체 경로를 확인해 달라고 요청해 주세요.",
                    500,
                ) from exc
            cache_path = DatasetObjectStorage().local_cache_path(dataset.dataset_id)
            if cache_path.exists():
                cache_path.unlink()
        else:
            path = get_settings().local_data_dir / dataset.csv_path
            if path.exists():
                path.unlink()
        return True

    def _refresh_uploaded_dataset(
        self,
        dataset: Dataset,
        df: pd.DataFrame,
        *,
        column_display_names: dict[str, str] | None = None,
        column_descriptions: dict[str, str] | None = None,
        column_units: dict[str, str | None] | None = None,
    ) -> Dataset:
        columns = _columns_from_dataframe(
            df,
            column_display_names=column_display_names,
            column_descriptions=column_descriptions,
            column_units=column_units,
        )
        analyses = _recommend_analyses(df, columns)
        dataset.columns = columns
        dataset.recommended_analyses = [RecommendedAnalysis(**analysis) for analysis in analyses]
        with _upload_lock:
            datasets = [item for item in _load_uploaded_datasets() if item.dataset_id != dataset.dataset_id]
            datasets.append(dataset)
            _write_uploaded_datasets(datasets)
        return dataset

    def apply_column_meanings(self, dataset_id: str, meanings: list[dict], owner_user_id: str | None = None) -> Dataset:
        dataset = self.get_dataset(dataset_id)
        self._assert_uploaded_owner(dataset, owner_user_id or dataset.owner_user_id or "")
        by_name = {str(item.get("name")): item for item in meanings if isinstance(item, dict) and item.get("name")}
        updated = 0
        for column in dataset.columns:
            proposal = by_name.get(column.name)
            if not proposal:
                continue
            display_name = str(proposal.get("display_name") or "").strip()
            description = str(proposal.get("description") or "").strip()
            if not display_name and not description:
                continue
            if display_name:
                column.display_name = display_name[:80]
            if description:
                column.description = description[:300]
            unit = str(proposal.get("unit") or "").strip()
            if unit:
                column.unit = unit[:40]
            column.estimated = True
            updated += 1
        if not updated:
            raise AppError(
                "COLUMN_MEANINGS_EMPTY",
                "저장할 항목 설명이 없습니다.",
                "제안을 다시 받아 본 뒤 적용해 주세요.",
            )
        with _upload_lock:
            datasets = [item for item in _load_uploaded_datasets() if item.dataset_id != dataset_id]
            datasets.append(dataset)
            _write_uploaded_datasets(datasets)
        return dataset

    def sheet(self, dataset_id: str, limit: int = 100, offset: int = 0, filters: dict[str, Any] | None = None) -> dict:
        dataset = self.get_dataset(dataset_id)
        df = self.read_dataframe(dataset_id)
        total_row_count = int(len(df))
        normalized_filters = self.normalize_row_filters(dataset_id, filters)
        filtered_df = self._apply_row_filters(df, normalized_filters)
        safe_limit = max(1, min(limit, SHEET_MAX_LIMIT))
        safe_offset = max(0, min(offset, max(len(filtered_df) - 1, 0))) if len(filtered_df) else 0
        page = filtered_df.iloc[safe_offset : safe_offset + safe_limit].copy()
        rows = _json_safe_rows(page)
        for index, row in zip(page.index, rows, strict=False):
            row["__row_index"] = int(index)
        return {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "row_count": int(len(filtered_df)),
            "total_row_count": total_row_count,
            "offset": safe_offset,
            "limit": safe_limit,
            "editable": dataset.uploaded,
            "filters": normalized_filters,
            "columns": [column.model_dump() for column in dataset.columns],
            "rows": rows,
        }

    def update_cells(self, dataset_id: str, owner_user_id: str, updates: list[dict]) -> dict:
        dataset = self.get_dataset(dataset_id)
        self._assert_uploaded_owner(dataset, owner_user_id)
        if not updates:
            raise AppError(
                "SHEET_UPDATES_REQUIRED",
                "수정할 셀이 없습니다.",
                "자료 표에서 값을 수정한 뒤 저장해 주세요.",
            )
        df = self.read_dataframe(dataset_id)
        column_names = set(df.columns)
        columns_by_name = {column.name: column for column in dataset.columns}
        for update in updates[:1000]:
            try:
                row_index = int(update.get("row_index"))
            except (TypeError, ValueError) as exc:
                raise AppError(
                    "SHEET_ROW_INDEX_INVALID",
                    "수정할 행 번호가 올바르지 않습니다.",
                    "표를 새로고침한 뒤 다시 수정해 주세요.",
                ) from exc
            column = str(update.get("column") or "")
            if row_index < 0 or row_index >= len(df) or column not in column_names:
                raise AppError(
                    "SHEET_CELL_INVALID",
                    "수정할 셀이 자료 범위를 벗어났습니다.",
                    "표를 새로고침한 뒤 다시 수정해 주세요.",
                )
            value = update.get("value")
            if value == "":
                parsed_value = None
            elif columns_by_name.get(column) and columns_by_name[column].dtype == "numeric":
                parsed_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            else:
                parsed_value = value
            df.at[row_index, column] = parsed_value
        self._write_dataframe(dataset, df)
        refreshed = self._refresh_uploaded_dataset(dataset, df.copy())
        return {
            "dataset": refreshed.model_dump(mode="json"),
            "summary": self.summary(dataset_id),
            "sheet": self.sheet(dataset_id),
        }

    def delete_columns(self, dataset_id: str, owner_user_id: str, columns: list[str]) -> dict:
        dataset = self.get_dataset(dataset_id)
        self._assert_uploaded_owner(dataset, owner_user_id)
        requested = [str(column or "").strip() for column in columns]
        requested = [column for index, column in enumerate(requested) if column and column not in requested[:index]]
        if not requested:
            raise AppError(
                "SHEET_COLUMNS_REQUIRED",
                "삭제할 열을 선택해 주세요.",
                "자료 표에서 분석에 필요 없는 열을 고른 뒤 다시 시도해 주세요.",
            )
        df = self.read_dataframe(dataset_id)
        missing = [column for column in requested if column not in df.columns]
        if missing:
            raise AppError(
                "SHEET_COLUMN_INVALID",
                f"자료에서 '{missing[0]}' 열을 찾을 수 없습니다.",
                "표를 새로고침한 뒤 다시 시도해 주세요.",
            )
        if len(df.columns) - len(requested) < 1:
            raise AppError(
                "SHEET_COLUMN_DELETE_ALL",
                "모든 열을 삭제할 수는 없습니다.",
                "분석에 필요한 열을 하나 이상 남겨 주세요.",
            )
        df = df.drop(columns=requested)
        self._write_dataframe(dataset, df)
        column_display_names = {
            column.name: column.display_name for column in dataset.columns if column.name in df.columns
        }
        column_descriptions = {
            column.name: column.description for column in dataset.columns if column.name in df.columns
        }
        column_units = {column.name: column.unit for column in dataset.columns if column.name in df.columns}
        refreshed = self._refresh_uploaded_dataset(
            dataset,
            df.copy(),
            column_display_names=column_display_names,
            column_descriptions=column_descriptions,
            column_units=column_units,
        )
        return {
            "dataset": refreshed.model_dump(mode="json"),
            "summary": self.summary(dataset_id),
            "sheet": self.sheet(dataset_id),
            "deleted_columns": requested,
        }

    def add_derived_column(
        self,
        dataset_id: str,
        owner_user_id: str,
        *,
        new_column: str,
        formula: str,
        display_name: str | None = None,
        description: str | None = None,
    ) -> dict:
        dataset = self.get_dataset(dataset_id)
        self._assert_uploaded_owner(dataset, owner_user_id)
        df = self.read_dataframe(dataset_id)
        column_name = _safe_column_name(new_column)
        if column_name in df.columns:
            raise AppError(
                "DERIVED_COLUMN_EXISTS",
                "이미 같은 이름의 자료 항목이 있습니다.",
                "새 파생변수 이름을 다르게 입력해 주세요.",
            )
        if len(df.columns) + 1 > MAX_UPLOAD_COLUMNS:
            raise AppError(
                "CSV_TOO_MANY_COLUMNS",
                f"자료 항목은 최대 {MAX_UPLOAD_COLUMNS}개까지 처리할 수 있습니다.",
                "사용하지 않는 항목을 줄인 뒤 다시 시도해 주세요.",
            )
        result = self._evaluate_formula(df, formula, dataset)
        df[column_name] = result
        self._write_dataframe(dataset, df)
        column_display_names = {column.name: column.display_name for column in dataset.columns}
        column_descriptions = {column.name: column.description for column in dataset.columns}
        column_units = {column.name: column.unit for column in dataset.columns}
        column_display_names[column_name] = (display_name or column_name).strip() or column_name
        column_descriptions[column_name] = (description or f"수식으로 만든 파생변수: {formula}").strip()
        refreshed = self._refresh_uploaded_dataset(
            dataset,
            df.copy(),
            column_display_names=column_display_names,
            column_descriptions=column_descriptions,
            column_units=column_units,
        )
        return {
            "dataset": refreshed.model_dump(mode="json"),
            "summary": self.summary(dataset_id),
            "sheet": self.sheet(dataset_id),
            "derived_column": {
                "name": column_name,
                "display_name": column_display_names[column_name],
                "formula": formula,
            },
        }

    def _evaluate_formula(self, df: pd.DataFrame, formula: str, dataset: Dataset | None = None) -> pd.Series:
        expression = formula.strip()
        if not expression or len(expression) > 500:
            raise AppError(
                "DERIVED_FORMULA_INVALID",
                "파생변수 수식이 비어 있거나 너무 깁니다.",
                "예: {value} / {population} * 100 처럼 입력해 주세요.",
            )
        values: dict[str, Any] = {}
        transformed = expression
        columns_by_name = {column.name: column for column in dataset.columns} if dataset else {}
        for index, column in enumerate(df.columns, start=1):
            alias = f"c{index}"
            dataset_column = columns_by_name.get(column)
            values[alias] = self._formula_column_value(df[column], dataset_column.dtype if dataset_column else "")
            transformed = transformed.replace("{" + column + "}", alias)
            display_name = dataset_column.display_name if dataset_column else column
            transformed = transformed.replace("{" + display_name + "}", alias)
            if _is_identifier(column):
                values[column] = values[alias]
        try:
            tree = ast.parse(_replace_caret_operator(transformed), mode="eval")
            result = self._eval_formula_node(tree.body, values)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "DERIVED_FORMULA_INVALID",
                "파생변수 수식을 계산할 수 없습니다.",
                "컬럼명은 {컬럼명}처럼 감싸고, + - * / ^ &, left(), right(), mid(), sqrt() 등을 사용해 주세요.",
            ) from exc
        series = result if isinstance(result, pd.Series) else pd.Series([result] * len(df))
        series = series.reset_index(drop=True)
        numeric = pd.to_numeric(series, errors="coerce")
        non_missing = series.dropna()
        numeric_ratio = 0 if len(non_missing) == 0 else float(numeric.notna().sum() / len(non_missing))
        if numeric_ratio >= 0.85 and numeric.notna().sum() > 0:
            return numeric.replace([float("inf"), float("-inf")], pd.NA)
        return series.astype(object).where(pd.notna(series), None)

    def _formula_column_value(self, series: pd.Series, dtype: str) -> pd.Series:
        if dtype == "numeric":
            return pd.to_numeric(series, errors="coerce")
        numeric = pd.to_numeric(series, errors="coerce")
        non_missing = series.dropna()
        numeric_ratio = 0 if len(non_missing) == 0 else float(numeric.notna().sum() / len(non_missing))
        if numeric_ratio >= 0.85 and numeric.notna().sum() > 0:
            return numeric
        return series.astype(object).where(pd.notna(series), None)

    def _as_numeric(self, value: Any) -> Any:
        if isinstance(value, pd.Series):
            return pd.to_numeric(value, errors="coerce")
        if isinstance(value, (int, float)):
            return value
        converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        return converted

    def _as_text(self, value: Any) -> Any:
        if isinstance(value, pd.Series):
            return value.astype("string").fillna("")
        if value is None or pd.isna(value):
            return ""
        return str(value)

    def _as_int_scalar(self, value: Any) -> int:
        if isinstance(value, pd.Series):
            numeric = pd.to_numeric(value.dropna(), errors="coerce").dropna()
            unique_values = numeric.unique()
            if len(unique_values) == 1:
                return int(unique_values[0])
            raise AppError(
                "DERIVED_FORMULA_UNSUPPORTED",
                "left, right, mid 함수의 위치와 글자 수에는 하나의 숫자를 넣어 주세요.",
                "예: left({name}, 2), mid({code}, 2, 3)처럼 입력해 주세요.",
            )
        return int(self._as_numeric(value))

    def _slice_left(self, value: Any, count: Any) -> Any:
        text = self._as_text(value)
        length = max(self._as_int_scalar(count), 0)
        if isinstance(text, pd.Series):
            return text.str.slice(0, length)
        return text[:length]

    def _slice_right(self, value: Any, count: Any) -> Any:
        text = self._as_text(value)
        length = max(self._as_int_scalar(count), 0)
        if length == 0:
            return text.str.slice(0, 0) if isinstance(text, pd.Series) else ""
        if isinstance(text, pd.Series):
            return text.str.slice(-length)
        return text[-length:]

    def _slice_mid(self, value: Any, start: Any, count: Any) -> Any:
        text = self._as_text(value)
        start_index = max(self._as_int_scalar(start) - 1, 0)
        length = max(self._as_int_scalar(count), 0)
        if isinstance(text, pd.Series):
            return text.str.slice(start_index, start_index + length)
        return text[start_index : start_index + length]

    def _eval_formula_node(self, node: ast.AST, values: dict[str, Any]) -> Any:
        if isinstance(node, ast.BinOp):
            left = self._eval_formula_node(node.left, values)
            right = self._eval_formula_node(node.right, values)
            if isinstance(node.op, ast.BitAnd):
                return self._as_text(left) + self._as_text(right)
            left_number = self._as_numeric(left)
            right_number = self._as_numeric(right)
            if isinstance(node.op, ast.Add):
                return left_number + right_number
            if isinstance(node.op, ast.Sub):
                return left_number - right_number
            if isinstance(node.op, ast.Mult):
                return left_number * right_number
            if isinstance(node.op, ast.Div):
                return left_number / right_number
            if isinstance(node.op, ast.FloorDiv):
                return left_number // right_number
            if isinstance(node.op, ast.Mod):
                return left_number % right_number
            if isinstance(node.op, ast.Pow):
                return left_number**right_number
            if isinstance(node.op, ast.BitXor):
                return left_number**right_number
        if isinstance(node, ast.UnaryOp):
            value = self._as_numeric(self._eval_formula_node(node.operand, values))
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
        if isinstance(node, ast.Name):
            if node.id in values:
                return values[node.id]
            raise AppError(
                "DERIVED_FORMULA_UNKNOWN_COLUMN",
                f"수식에서 '{node.id}' 항목을 찾을 수 없습니다.",
                "컬럼명은 {컬럼명}처럼 중괄호로 감싸 입력해 주세요.",
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
            return node.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args = [self._eval_formula_node(arg, values) for arg in node.args]
            func_name = node.func.id.lower()
            if func_name == "abs" and len(args) == 1:
                return abs(self._as_numeric(args[0]))
            if func_name == "round" and 1 <= len(args) <= 2:
                value = self._as_numeric(args[0])
                digits = self._as_int_scalar(args[1]) if len(args) == 2 else 0
                return value.round(digits) if isinstance(value, pd.Series) else round(value, digits)
            if func_name == "sqrt" and len(args) == 1:
                return self._as_numeric(args[0]) ** 0.5
            if func_name == "left" and len(args) == 2:
                return self._slice_left(args[0], args[1])
            if func_name == "right" and len(args) == 2:
                return self._slice_right(args[0], args[1])
            if func_name == "mid" and len(args) == 3:
                return self._slice_mid(args[0], args[1], args[2])
        raise AppError(
            "DERIVED_FORMULA_UNSUPPORTED",
            "지원하지 않는 파생변수 수식입니다.",
            "+, -, *, /, ^, &, 괄호, abs(), round(), sqrt(), left(), right(), mid()를 사용해 주세요.",
        )

    def get_column(self, dataset_id: str, column_name: str) -> DatasetColumn:
        dataset = self.get_dataset(dataset_id)
        for column in dataset.columns:
            if column.name == column_name:
                return column
        raise AppError(
            "INVALID_COLUMN",
            f"'{column_name}' 컬럼은 이 자료에 없습니다.",
            "자료 설명의 컬럼명 중 하나를 선택해 주세요.",
        )

    def require_columns(self, dataset_id: str, columns: list[str]) -> None:
        for column in columns:
            self.get_column(dataset_id, column)

    def require_numeric_columns(self, dataset_id: str, columns: list[str]) -> None:
        for column_name in columns:
            column = self.get_column(dataset_id, column_name)
            if column.dtype != "numeric":
                raise AppError(
                    "INVALID_COLUMN_TYPE",
                    f"'{column_name}' 컬럼은 수치형 분석에 사용할 수 없습니다.",
                    "수치형 컬럼을 선택해 주세요.",
                )

    def schema(self, dataset_id: str, school_level: str | None = None) -> dict:
        dataset = self.get_dataset(dataset_id)
        try:
            columns = describe_columns(self.read_dataframe(dataset_id), dataset.columns, school_level=school_level)
        except AppError:
            columns = [column.model_dump() for column in dataset.columns]
        return {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "source": dataset.source,
            "source_note": dataset.source_note,
            "source_notes": [note.model_dump() for note in dataset.source_notes],
            "uploaded": dataset.uploaded,
            "columns": columns,
            "recommended_analyses": [analysis.model_dump() for analysis in dataset.recommended_analyses],
        }

    def summary(self, dataset_id: str) -> dict:
        dataset = self.get_dataset(dataset_id)
        df = self.read_dataframe(dataset_id)
        columns: dict[str, dict] = {}
        for column in dataset.columns:
            series = df[column.name]
            summary = {
                "display_name": column.display_name,
                "dtype": column.dtype,
                "missing_count": int(series.isna().sum()),
            }
            unique_values = [str(value) for value in series.dropna().unique()[:MAX_ROW_FILTER_VALUES]]
            unique_count = int(series.nunique(dropna=True))
            if column.dtype == "numeric":
                numeric = pd.to_numeric(series, errors="coerce")
                min_value = numeric.min()
                max_value = numeric.max()
                mean_value = numeric.mean()
                summary.update(
                    {
                        "min": None if pd.isna(min_value) else float(min_value),
                        "max": None if pd.isna(max_value) else float(max_value),
                        "mean": None if pd.isna(mean_value) else float(mean_value),
                        "unique_count": unique_count,
                        "unique_values": unique_values,
                        "unique_values_truncated": unique_count > len(unique_values),
                    }
                )
            else:
                summary.update(
                    {
                        "unique_count": unique_count,
                        "examples": unique_values[:5],
                        "unique_values": unique_values,
                        "unique_values_truncated": unique_count > len(unique_values),
                    }
                )
            columns[column.name] = summary
        return {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "row_count": int(len(df)),
            "columns": columns,
        }

    def create_uploaded_dataset(
        self,
        *,
        filename: str,
        content: bytes,
        topic_id: str,
        owner_user_id: str,
        dataset_name: str | None = None,
        source: str = "학생 업로드 CSV",
        source_note: str | None = None,
        description: str | None = None,
        time_range: str = "업로드 자료",
        geographic_unit: str | None = None,
        column_display_names: dict[str, str] | None = None,
        column_descriptions: dict[str, str] | None = None,
        column_units: dict[str, str | None] | None = None,
        column_extras: dict[str, dict] | None = None,
        source_notes: list[DatasetNote] | None = None,
        school_level: str | None = None,
    ) -> dict:
        if not filename.lower().endswith(".csv"):
            raise AppError(
                "INVALID_FILE_TYPE",
                "CSV 파일만 업로드할 수 있습니다.",
                ".csv 확장자의 파일을 선택해 주세요.",
            )
        if len(content) > MAX_UPLOAD_BYTES:
            raise AppError(
                "CSV_TOO_LARGE",
                f"CSV 파일 크기는 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하만 가능합니다.",
                "필요한 행과 컬럼만 남긴 뒤 다시 업로드해 주세요.",
            )
        if not content.strip():
            raise AppError(
                "CSV_EMPTY",
                "CSV 파일이 비어 있습니다.",
                "컬럼명과 데이터 행이 있는 파일을 업로드해 주세요.",
            )

        df, encoding = _read_csv_bytes(content)
        if df.empty:
            raise AppError(
                "CSV_EMPTY_TABLE",
                "CSV에서 데이터 행을 찾을 수 없습니다.",
                "첫 줄은 컬럼명, 그 아래에는 데이터가 오도록 확인해 주세요.",
            )
        if len(df) > MAX_UPLOAD_ROWS:
            raise AppError(
                "CSV_TOO_MANY_ROWS",
                f"업로드 CSV는 최대 {MAX_UPLOAD_ROWS}행까지 처리할 수 있습니다.",
                "탐구에 필요한 표본만 남긴 파일을 업로드해 주세요.",
            )
        if len(df.columns) > MAX_UPLOAD_COLUMNS:
            raise AppError(
                "CSV_TOO_MANY_COLUMNS",
                f"업로드 CSV는 최대 {MAX_UPLOAD_COLUMNS}개 컬럼까지 처리할 수 있습니다.",
                "분석에 필요한 컬럼만 남긴 파일을 업로드해 주세요.",
            )

        df.columns = _normalize_columns(list(df.columns))
        columns = _columns_from_dataframe(
            df,
            column_display_names=column_display_names,
            column_descriptions=column_descriptions,
            column_units=column_units,
            column_extras=column_extras,
        )

        analyses = _recommend_analyses(df, columns)
        if not analyses:
            raise AppError(
                "CSV_NO_ANALYSIS_CANDIDATE",
                "이 CSV에서 바로 실행할 수 있는 분석 후보를 찾지 못했습니다.",
                "수치형 컬럼이나 반복되는 범주형 컬럼이 있는 표인지 확인해 주세요.",
            )

        dataset_id = f"uploaded_{uuid4().hex[:12]}"
        safe_source_name = Path(filename).name
        display_name = (dataset_name or safe_source_name).strip() or safe_source_name
        storage = DatasetObjectStorage()
        if storage.enabled():
            local_path = storage.local_cache_path(dataset_id)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(local_path, index=False, encoding="utf-8-sig")
            csv_path = storage.uri_for(owner_user_id, dataset_id)
            storage.upload_file(local_path, csv_path)
        else:
            upload_dir = get_settings().local_data_dir / UPLOAD_DIR
            upload_dir.mkdir(parents=True, exist_ok=True)
            csv_path = f"{UPLOAD_DIR}/{dataset_id}.csv"
            df.to_csv(get_settings().local_data_dir / csv_path, index=False, encoding="utf-8-sig")

        dataset = Dataset(
            dataset_id=dataset_id,
            topic_id=topic_id,
            name=display_name[:80],
            source=source,
            source_note=source_note or f"{safe_source_name}에서 {now_utc().strftime('%Y-%m-%d')} 등록",
            csv_path=csv_path,
            description=description
            or f"학생이 업로드한 CSV 자료입니다. 전체 {len(df)}행, {len(df.columns)}개 항목입니다.",
            time_range=time_range,
            geographic_unit=geographic_unit,
            columns=columns,
            recommended_analyses=analyses,
            source_notes=source_notes or [],
            uploaded=True,
            owner_user_id=owner_user_id,
        )
        analyses = _ai_recommended_analyses(dataset, analyses, school_level=school_level)
        dataset.recommended_analyses = [RecommendedAnalysis(**analysis) for analysis in analyses]
        processing_plan = _build_processing_plan(df, columns, analyses, encoding)

        with _upload_lock:
            datasets = [item for item in _load_uploaded_datasets() if item.dataset_id != dataset_id]
            datasets.append(dataset)
            _write_uploaded_datasets(datasets)

        return {
            "dataset": dataset.model_dump(mode="json"),
            "summary": self.summary(dataset.dataset_id),
            "processing_plan": processing_plan,
        }
