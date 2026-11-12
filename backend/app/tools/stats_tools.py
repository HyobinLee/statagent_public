import math

import numpy as np
import pandas as pd

from app.core.errors import AppError
from app.services.dataset_service import DatasetService
from app.tools.schemas import start_timer, tool_failure, tool_success

MIDDLE_STATS = {
    "mean",
    "median",
    "mode",
    "range",
    "min",
    "max",
    "frequency",
    "relative_frequency",
    "cumulative_frequency",
}
HIGH_STATS = {"variance", "std", "q1", "q3", "iqr", "pearson_correlation"}
ALLOWED_STATS = MIDDLE_STATS | HIGH_STATS
NON_NUMERIC_STATS = {"frequency", "relative_frequency", "cumulative_frequency", "mode"}
MAX_STAT_GROUPS = 8
FORBIDDEN_STATS = {
    "regression_coefficient",
    "p_value",
    "confidence_interval",
    "hypothesis_test",
    "spearman_correlation",
    "kendall_correlation",
    "bayesian_statistics",
}

RESAMPLE_DEFAULT_COUNT = 1000
MAX_RESAMPLE_COUNT = 5000
MIN_RESAMPLE_GROUP_SIZE = 5


def _scope_error() -> AppError:
    return AppError(
        "OUT_OF_CURRICULUM_SCOPE",
        "이 분석은 v0.1의 중·고등 통계 탐구 범위를 벗어납니다.",
        "평균, 중앙값, 표준편차, 상관계수, 그래프 분석 중 하나를 선택해 주세요.",
    )


def _clean_number(value: float | int | np.floating) -> float | int | None:
    if pd.isna(value):
        return None
    number = float(value)
    if math.isclose(number, round(number)):
        return int(round(number))
    return round(number, 4)


def _column_statistics(series: pd.Series, requested: set[str]) -> dict[str, object]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    column_result: dict[str, object] = {}
    if "mean" in requested:
        column_result["mean"] = _clean_number(numeric.mean())
    if "median" in requested:
        column_result["median"] = _clean_number(numeric.median())
    if "mode" in requested:
        modes = series.mode(dropna=True).tolist()
        column_result["mode"] = modes[:5]
    if "range" in requested:
        column_result["range"] = _clean_number(numeric.max() - numeric.min())
    if "min" in requested:
        column_result["min"] = _clean_number(numeric.min())
    if "max" in requested:
        column_result["max"] = _clean_number(numeric.max())
    if "variance" in requested:
        column_result["variance"] = _clean_number(numeric.var(ddof=1))
    if "std" in requested:
        column_result["std"] = _clean_number(numeric.std(ddof=1))
    if "q1" in requested:
        column_result["q1"] = _clean_number(numeric.quantile(0.25))
    if "q3" in requested:
        column_result["q3"] = _clean_number(numeric.quantile(0.75))
    if "iqr" in requested:
        column_result["iqr"] = _clean_number(numeric.quantile(0.75) - numeric.quantile(0.25))
    if "frequency" in requested:
        column_result["frequency"] = series.value_counts().to_dict()
    if "relative_frequency" in requested:
        counts = series.value_counts(normalize=True)
        column_result["relative_frequency"] = {str(key): round(float(value), 4) for key, value in counts.items()}
    if "cumulative_frequency" in requested:
        counts = series.value_counts().sort_index().cumsum()
        column_result["cumulative_frequency"] = {str(key): int(value) for key, value in counts.items()}
    return column_result


def _grouped_statistics(
    df: pd.DataFrame,
    columns: list[str],
    requested: set[str],
    group_by: str,
) -> tuple[list[dict], list[str]]:
    labels = df[group_by].astype(str).where(df[group_by].notna())
    group_names = list(labels.dropna().unique())
    if len(group_names) < 2:
        raise AppError(
            "INSUFFICIENT_GROUPS",
            f"'{group_by}' 항목의 그룹이 2개 이상이어야 집단별로 비교할 수 있습니다.",
            "값이 여러 가지로 나뉘는 범주형 컬럼을 선택해 주세요.",
        )
    if len(group_names) > MAX_STAT_GROUPS:
        raise AppError(
            "TOO_MANY_GROUPS",
            f"집단별 요약 통계량은 최대 {MAX_STAT_GROUPS}개 집단까지 비교할 수 있습니다.",
            "그룹 수가 적은 컬럼을 선택하거나 비슷한 그룹을 묶어 주세요.",
        )
    groups: list[dict] = []
    empty_groups: list[str] = []
    numeric_needed = bool(requested - NON_NUMERIC_STATS)
    for name in group_names:
        subset = df[labels == name]
        statistics = {column: _column_statistics(subset[column].dropna(), requested) for column in columns}
        sample_sizes = {
            column: int(
                pd.to_numeric(subset[column], errors="coerce").notna().sum()
                if numeric_needed
                else subset[column].notna().sum()
            )
            for column in columns
        }
        if all(size == 0 for size in sample_sizes.values()):
            empty_groups.append(name)
            continue
        groups.append(
            {
                "group": name,
                "row_count": int(len(subset)),
                "sample_size": max(sample_sizes.values()),
                "sample_sizes": sample_sizes,
                "statistics": statistics,
            }
        )
    warnings: list[str] = []
    if empty_groups:
        warnings.append(f"{', '.join(empty_groups)} 집단은 선택한 항목의 값이 없어 표에서 제외했습니다.")
    if len(groups) < 2:
        raise AppError(
            "INSUFFICIENT_GROUPS",
            f"'{group_by}'로 나눈 집단 중 값이 있는 집단이 2개 미만입니다.",
            "빈칸이 적은 항목을 고르거나 다른 범주형 컬럼으로 나눠 주세요.",
        )
    return groups, warnings


def compute_descriptive_stats(
    dataset_id: str,
    columns: list[str],
    statistics: list[str],
    group_by: str | None = None,
) -> dict:
    start = start_timer()
    try:
        if not columns:
            raise AppError(
                "INVALID_ARGUMENT",
                "분석할 컬럼을 하나 이상 선택해야 합니다.",
                "수치형 컬럼을 선택해 주세요.",
            )
        if not statistics:
            raise AppError(
                "INVALID_ARGUMENT",
                "계산할 통계량을 하나 이상 선택해야 합니다.",
                "평균, 중앙값, 최솟값 같은 통계량을 선택해 주세요.",
            )
        requested = set(statistics)
        if requested & FORBIDDEN_STATS:
            raise _scope_error()
        unknown = requested - ALLOWED_STATS
        if unknown:
            raise AppError(
                "INVALID_STATISTIC",
                f"지원하지 않는 통계량입니다: {', '.join(sorted(unknown))}",
                "허용된 통계량 목록에서 다시 선택해 주세요.",
            )

        service = DatasetService()
        numeric_stats = requested - NON_NUMERIC_STATS
        if numeric_stats:
            service.require_numeric_columns(dataset_id, columns)
        else:
            service.require_columns(dataset_id, columns)
        if group_by:
            service.require_columns(dataset_id, [group_by])
        df = service.read_dataframe(dataset_id)

        result = {column: _column_statistics(df[column].dropna(), requested) for column in columns}
        data: dict[str, object] = {"statistics": result}
        warnings: list[str] = []
        hint = "대표값과 산포도를 비교하면 자료의 전반적인 특징을 말할 수 있습니다."
        if group_by:
            groups, warnings = _grouped_statistics(df, columns, requested, group_by)
            data["group_by"] = group_by
            data["groups"] = groups
            data["columns"] = columns
            data["overall"] = {
                "group": "전체",
                "row_count": int(len(df)),
                "sample_size": max(int(pd.to_numeric(df[column], errors="coerce").notna().sum()) for column in columns),
                "statistics": result,
            }
            hint = (
                "집단별 대표값(평균·중앙값)과 산포도(표준편차·사분위수)를 나란히 비교하면 "
                "두 집단의 분포가 어떻게 다른지 말할 수 있습니다."
            )

        return tool_success(
            "compute_descriptive_stats",
            dataset_id,
            data,
            hint,
            start,
            warnings,
        )
    except AppError as exc:
        return tool_failure("compute_descriptive_stats", dataset_id, exc, start)


MAX_CORRELATION_GROUPS = 8
MIN_GROUP_SAMPLE_SIZE = 5


def _constant_column_error(columns: list[str]) -> AppError:
    return AppError(
        "CONSTANT_COLUMN",
        f"{', '.join(columns)} 항목의 값이 모두 같아 상관계수를 계산할 수 없습니다.",
        "값이 여러 가지로 변하는 수치형 항목을 선택해 주세요.",
    )


def _assert_correlation_computable(clean: pd.DataFrame, x_column: str, y_column: str) -> None:
    constant = [column for column in (x_column, y_column) if float(clean[column].std(ddof=1) or 0) == 0]
    if constant:
        raise _constant_column_error(constant)


def _correlation_labels(coefficient: float) -> str:
    strength = "강한" if abs(coefficient) >= 0.7 else "중간 정도의" if abs(coefficient) >= 0.4 else "약한"
    direction = "양의" if coefficient > 0 else "음의" if coefficient < 0 else "거의 없는"
    return f"{strength} {direction} 관계"


def compute_correlation(dataset_id: str, x_column: str, y_column: str) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [x_column, y_column])
        df = service.read_dataframe(dataset_id)
        clean = df[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(clean) < 10:
            raise AppError(
                "INSUFFICIENT_SAMPLE_SIZE",
                "상관계수를 계산하려면 결측 제거 후 표본이 10개 이상이어야 합니다.",
                "행이 더 많은 자료를 선택하거나 다른 컬럼을 선택해 주세요.",
            )
        _assert_correlation_computable(clean, x_column, y_column)
        coefficient = float(clean[x_column].corr(clean[y_column], method="pearson"))
        if math.isnan(coefficient):
            raise _constant_column_error([x_column, y_column])
        return tool_success(
            "compute_correlation",
            dataset_id,
            {
                "x_column": x_column,
                "y_column": y_column,
                "pearson_correlation": round(coefficient, 4),
                "sample_size": int(len(clean)),
                "interpretation_label": _correlation_labels(coefficient),
            },
            "상관계수는 두 수치형 변수가 함께 움직이는 정도를 -1부터 1 사이로 나타냅니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("compute_correlation", dataset_id, exc, start)


def prepare_grouped_correlation(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    group_by: str,
) -> dict:
    clean = df[[x_column, y_column, group_by]].copy()
    clean[x_column] = pd.to_numeric(clean[x_column], errors="coerce")
    clean[y_column] = pd.to_numeric(clean[y_column], errors="coerce")
    clean = clean.dropna(subset=[x_column, y_column, group_by])
    if len(clean) < 10:
        raise AppError(
            "INSUFFICIENT_SAMPLE_SIZE",
            "상관계수를 계산하려면 결측 제거 후 표본이 10개 이상이어야 합니다.",
            "행이 더 많은 자료를 선택하거나 다른 컬럼을 선택해 주세요.",
        )

    group_names = [str(name) for name in clean[group_by].astype(str).unique()]
    if len(group_names) < 2:
        raise AppError(
            "INSUFFICIENT_GROUPS",
            f"'{group_by}' 항목의 그룹이 2개 이상이어야 층화분석을 할 수 있습니다.",
            "값이 여러 가지로 나뉘는 범주형 컬럼을 선택해 주세요.",
        )
    if len(group_names) > MAX_CORRELATION_GROUPS:
        raise AppError(
            "TOO_MANY_GROUPS",
            f"층화분석의 그룹은 최대 {MAX_CORRELATION_GROUPS}개까지만 비교할 수 있습니다.",
            "그룹 수가 적은 컬럼을 선택하거나 비슷한 그룹을 묶어 주세요.",
        )

    _assert_correlation_computable(clean, x_column, y_column)
    overall_coefficient = float(clean[x_column].corr(clean[y_column], method="pearson"))
    if math.isnan(overall_coefficient):
        raise _constant_column_error([x_column, y_column])
    labels = clean[group_by].astype(str)

    groups: list[dict] = []
    for name in group_names:
        subset = clean[labels == name]
        size = int(len(subset))
        if size < MIN_GROUP_SAMPLE_SIZE:
            groups.append({"group": name, "sample_size": size, "pearson_correlation": None, "note": "표본 부족"})
            continue
        if subset[x_column].std(ddof=1) == 0 or subset[y_column].std(ddof=1) == 0:
            groups.append({"group": name, "sample_size": size, "pearson_correlation": None, "note": "값이 모두 같음"})
            continue
        coefficient = float(subset[x_column].corr(subset[y_column], method="pearson"))
        groups.append(
            {
                "group": name,
                "sample_size": size,
                "pearson_correlation": round(coefficient, 4),
                "interpretation_label": _correlation_labels(coefficient),
                "note": None,
            }
        )

    computed = [item["pearson_correlation"] for item in groups if item["pearson_correlation"] is not None]
    notable = [value for value in computed if abs(value) >= 0.3]
    sign_contrast = any(value > 0 for value in notable) and any(value < 0 for value in notable)

    skipped = [item["group"] for item in groups if item["pearson_correlation"] is None]
    warnings = []
    if skipped:
        warnings.append(
            f"{', '.join(skipped)} 그룹은 표본이 {MIN_GROUP_SAMPLE_SIZE}개 미만이거나 "
            "값이 모두 같아 상관계수를 계산하지 않았습니다."
        )

    return {
        "clean": clean,
        "labels": labels,
        "group_names": group_names,
        "warnings": warnings,
        "data": {
            "x_column": x_column,
            "y_column": y_column,
            "group_by": group_by,
            "overall": {
                "pearson_correlation": round(overall_coefficient, 4),
                "sample_size": int(len(clean)),
                "interpretation_label": _correlation_labels(overall_coefficient),
            },
            "groups": groups,
            "sign_contrast": sign_contrast,
        },
    }


def compute_grouped_correlation(dataset_id: str, x_column: str, y_column: str, group_by: str) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [x_column, y_column])
        service.require_columns(dataset_id, [group_by])
        prepared = prepare_grouped_correlation(service.read_dataframe(dataset_id), x_column, y_column, group_by)
        if prepared["data"]["sign_contrast"]:
            hint = (
                "전체 상관계수와 집단별 상관계수의 방향이 서로 다릅니다. "
                "왜 집단마다 관계가 다르게 나타나는지, 어떤 집단을 기준으로 봐야 할지 생각해 보세요."
            )
        else:
            hint = "집단을 나눠 상관계수를 비교하면 전체 상관계수가 모든 집단에서 성립하는지 확인할 수 있습니다."
        return tool_success(
            "compute_grouped_correlation",
            dataset_id,
            prepared["data"],
            hint,
            start,
            prepared["warnings"],
        )
    except AppError as exc:
        return tool_failure("compute_grouped_correlation", dataset_id, exc, start)


def resample_compare(
    dataset_id: str,
    value_column: str,
    group_column: str,
    n_resamples: int = RESAMPLE_DEFAULT_COUNT,
    seed: int = 261026,
) -> dict:
    start = start_timer()
    try:
        if not 100 <= n_resamples <= MAX_RESAMPLE_COUNT:
            raise AppError(
                "INVALID_ARGUMENT",
                f"재표집 횟수는 100 이상 {MAX_RESAMPLE_COUNT} 이하만 가능합니다.",
                "n_resamples 값을 조정해 주세요.",
            )
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [value_column])
        service.require_columns(dataset_id, [group_column])
        df = service.read_dataframe(dataset_id)
        values_series = pd.to_numeric(df[value_column], errors="coerce")
        groups_series = df[group_column].astype(str).str.strip()
        mask = values_series.notna() & groups_series.notna() & (groups_series != "")
        values = values_series[mask].to_numpy(dtype=float)
        groups = groups_series[mask]
        names = sorted(groups.unique())
        if len(names) != 2:
            raise AppError(
                "RESAMPLE_NEEDS_TWO_GROUPS",
                f"이 도구는 정확히 두 집단을 비교합니다. '{group_column}'에는 집단이 {len(names)}개 있습니다.",
                "두 집단으로 나뉘는 열을 고르거나 자료를 두 집단으로 줄여 주세요.",
            )
        first_mask = (groups == names[0]).to_numpy()
        n_first = int(first_mask.sum())
        n_second = int(len(values) - n_first)
        if min(n_first, n_second) < MIN_RESAMPLE_GROUP_SIZE:
            raise AppError(
                "RESAMPLE_GROUP_TOO_SMALL",
                f"집단별 표본이 {MIN_RESAMPLE_GROUP_SIZE}개 미만이면 재표집 분포가 의미를 갖기 어렵습니다.",
                "표본이 더 많은 자료로 시도해 주세요.",
            )
        mean_first = float(values[first_mask].mean())
        mean_second = float(values[~first_mask].mean())
        observed = mean_first - mean_second

        rng = np.random.default_rng(seed)
        diffs = np.empty(n_resamples, dtype=float)
        for index in range(n_resamples):
            shuffled = rng.permutation(values)
            diffs[index] = shuffled[:n_first].mean() - shuffled[n_first:].mean()

        import matplotlib.pyplot as plt

        from app.tools.chart_tools import _base_figure, _save_chart

        warnings = _base_figure()
        plt.hist(diffs, bins=30, color="#8d99ae", edgecolor="white")
        plt.axvline(observed, color="#d62828", linewidth=2, label=f"관찰된 차이 {observed:+.2f}")
        plt.legend()
        plt.xlabel(f"{group_column} 라벨을 무작위로 섞었을 때 {value_column} 평균 차이")
        plt.ylabel("횟수")
        chart = _save_chart(
            f"평균 차이의 재표집 분포 ({names[0]} - {names[1]})",
            f"{group_column} 라벨을 {n_resamples}번 무작위로 섞어 얻은 {value_column} 평균 차이의 분포이고,"
            f" 관찰된 차이 {round(observed, 2)}의 위치가 세로선으로 표시되어 있습니다.",
        )
        data = {
            **chart,
            "value_column": value_column,
            "group_column": group_column,
            "n_resamples": n_resamples,
            "groups": [
                {"name": names[0], "size": n_first, "mean": _clean_number(round(mean_first, 2))},
                {"name": names[1], "size": n_second, "mean": _clean_number(round(mean_second, 2))},
            ],
            "observed_diff": _clean_number(round(observed, 2)),
            "reading_guide": (
                "세로선(관찰된 차이)이 분포의 가운데 가까이에 있으면 우연만으로도 흔히 나는 크기의 차이이고, "
                "분포의 끝자락이나 바깥에 있으면 우연만으로는 드문 크기의 차이입니다. "
                "이 그림은 우연의 범위를 보여 줄 뿐, 어느 쪽인지 판정해 주지 않습니다."
            ),
        }
        return tool_success(
            "resample_compare",
            dataset_id,
            data,
            "재표집 분포는 '집단 구분이 값과 무관하다면'이라는 가정 아래에서 평균 차이가 얼마나 흔들리는지 보여줍니다.",
            start,
            warnings,
        )
    except AppError as exc:
        try:
            import matplotlib.pyplot as plt

            plt.close()
        except ImportError:
            pass
        return tool_failure("resample_compare", dataset_id, exc, start)
