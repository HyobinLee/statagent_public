import math

import matplotlib.pyplot as plt
import pandas as pd

from app.core.errors import AppError
from app.tools.chart_tools import _base_figure, _save_chart
from app.tools.schemas import ToolDefinition, start_timer, tool_failure, tool_success
from app.tools.stats_tools import (
    ALLOWED_STATS,
    FORBIDDEN_STATS,
    _assert_correlation_computable,
    _clean_number,
    _constant_column_error,
    _correlation_labels,
    _scope_error,
)

MAX_COMPARISON_COLUMNS = 6
MAX_COMPARISON_SERIES = 5


def _missing_columns_error(function: str, df: pd.DataFrame, columns: list[str]) -> AppError | None:
    missing = [column for column in columns if column not in df.columns]
    if not missing:
        return None
    return AppError(
        "COLUMN_NOT_FOUND",
        f"결합한 자료에서 컬럼을 찾을 수 없습니다: {', '.join(missing)}",
        "결합 결과의 컬럼 목록을 다시 확인해 주세요.",
    )


def compute_cross_dataset_comparison(df: pd.DataFrame, value_columns: list[str], statistics: list[str]) -> dict:
    start = start_timer()
    try:
        if not value_columns or len(value_columns) < 2:
            raise AppError(
                "INVALID_ARGUMENT",
                "비교할 컬럼을 2개 이상 선택해야 합니다.",
                "결합한 자료에서 비교할 컬럼을 2개 이상 선택해 주세요.",
            )
        if len(value_columns) > MAX_COMPARISON_COLUMNS:
            raise AppError(
                "TOO_MANY_COLUMNS",
                f"비교 컬럼은 최대 {MAX_COMPARISON_COLUMNS}개까지 선택할 수 있습니다.",
                "비교할 컬럼 수를 줄여 주세요.",
            )
        missing_error = _missing_columns_error("compute_cross_dataset_comparison", df, value_columns)
        if missing_error:
            raise missing_error
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

        result: dict[str, dict] = {}
        for column in value_columns:
            series = df[column].dropna()
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            column_result: dict[str, object] = {}
            if "mean" in requested:
                column_result["mean"] = _clean_number(numeric.mean())
            if "median" in requested:
                column_result["median"] = _clean_number(numeric.median())
            if "mode" in requested:
                column_result["mode"] = series.mode(dropna=True).tolist()[:5]
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
            result[column] = column_result

        return tool_success(
            "compute_cross_dataset_comparison",
            None,
            {"statistics": result, "row_count": int(len(df))},
            "결합된 자료에서 여러 변수의 대표값을 나란히 비교할 수 있습니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("compute_cross_dataset_comparison", None, exc, start)


def compute_cross_correlation(df: pd.DataFrame, x_column: str, y_column: str) -> dict:
    start = start_timer()
    try:
        missing_error = _missing_columns_error("compute_cross_correlation", df, [x_column, y_column])
        if missing_error:
            raise missing_error
        clean = df[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(clean) < 10:
            raise AppError(
                "INSUFFICIENT_SAMPLE_SIZE",
                "상관계수를 계산하려면 결측 제거 후 표본이 10개 이상이어야 합니다.",
                "다른 컬럼을 선택하거나 결합 조건을 조정해 주세요.",
            )
        _assert_correlation_computable(clean, x_column, y_column)
        coefficient = float(clean[x_column].corr(clean[y_column], method="pearson"))
        if math.isnan(coefficient):
            raise _constant_column_error([x_column, y_column])
        return tool_success(
            "compute_cross_correlation",
            None,
            {
                "x_column": x_column,
                "y_column": y_column,
                "pearson_correlation": round(coefficient, 4),
                "sample_size": int(len(clean)),
                "interpretation_label": _correlation_labels(coefficient),
            },
            "결합한 자료에서 두 변수 사이의 상관관계를 -1부터 1 사이 값으로 나타냅니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("compute_cross_correlation", None, exc, start)


def plot_comparative_line(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str | None = None) -> dict:
    start = start_timer()
    try:
        if not y_cols or len(y_cols) < 2:
            raise AppError(
                "INVALID_ARGUMENT",
                "비교할 변수를 2개 이상 선택해야 합니다.",
                "결합한 자료에서 비교할 수치형 컬럼을 2개 이상 선택해 주세요.",
            )
        if len(y_cols) > MAX_COMPARISON_SERIES:
            raise AppError(
                "TOO_MANY_SERIES",
                f"비교 선그래프의 변수는 최대 {MAX_COMPARISON_SERIES}개까지만 가능합니다.",
                "비교할 변수 수를 줄여 주세요.",
            )
        missing_error = _missing_columns_error("plot_comparative_line", df, [x_col, *y_cols])
        if missing_error:
            raise missing_error

        working = df[[x_col, *y_cols]].copy()
        for column in y_cols:
            working[column] = pd.to_numeric(working[column], errors="coerce")
        working = working.sort_values(x_col)

        warnings = _base_figure()
        palette = ["#287c7a", "#2563eb", "#b23a48", "#5f6f52", "#7a4c9f"]
        maxima = [value for value in (working[column].abs().max() for column in y_cols) if pd.notna(value)]
        if len(maxima) >= 2 and min(maxima) > 0 and (max(maxima) / min(maxima)) >= 100:
            warnings.append("두 변수의 단위 크기가 크게 달라 함께 읽을 때 주의가 필요합니다.")
        for index, column in enumerate(y_cols):
            plt.plot(working[x_col], working[column], marker="o", label=column, color=palette[index % len(palette)])
        plt.legend()
        plt.xlabel(x_col)
        chart_title = title or f"{x_col}에 따른 {', '.join(y_cols)} 비교"
        chart = _save_chart(chart_title, f"{x_col}에 따른 {', '.join(y_cols)}의 변화를 비교한 선그래프입니다.")
        return tool_success(
            "plot_comparative_line",
            None,
            chart,
            "여러 자료의 변수를 같은 그래프에 겹쳐 그리면 시간 흐름에 따른 변화를 함께 비교할 수 있습니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_comparative_line", None, exc, start)


def plot_comparative_bar(df: pd.DataFrame, category_col: str, value_cols: list[str], title: str | None = None) -> dict:
    start = start_timer()
    try:
        if not value_cols or len(value_cols) < 2:
            raise AppError(
                "INVALID_ARGUMENT",
                "비교할 변수를 2개 이상 선택해야 합니다.",
                "결합한 자료에서 비교할 수치형 컬럼을 2개 이상 선택해 주세요.",
            )
        if len(value_cols) > MAX_COMPARISON_SERIES:
            raise AppError(
                "TOO_MANY_SERIES",
                f"비교 막대그래프의 변수는 최대 {MAX_COMPARISON_SERIES}개까지만 가능합니다.",
                "비교할 변수 수를 줄여 주세요.",
            )
        missing_error = _missing_columns_error("plot_comparative_bar", df, [category_col, *value_cols])
        if missing_error:
            raise missing_error

        category_count = df[category_col].dropna().nunique()
        if category_count > 20:
            raise AppError(
                "TOO_MANY_CATEGORIES",
                "막대그래프의 범주는 20개 이하만 사용할 수 있습니다.",
                "범주가 적은 컬럼을 선택하거나 자료를 필터링해 주세요.",
            )

        working = df[[category_col, *value_cols]].copy()
        for column in value_cols:
            working[column] = pd.to_numeric(working[column], errors="coerce")
        grouped = working.groupby(category_col, dropna=False)[value_cols].sum()

        warnings = _base_figure()
        palette = ["#287c7a", "#2563eb", "#b23a48", "#5f6f52", "#7a4c9f"]
        grouped.plot(kind="bar", color=palette[: len(value_cols)])
        plt.xlabel(category_col)
        chart_title = title or f"{category_col}별 {', '.join(value_cols)} 비교"
        chart = _save_chart(chart_title, f"{category_col}별 {', '.join(value_cols)} 값을 비교한 막대그래프입니다.")
        return tool_success(
            "plot_comparative_bar",
            None,
            chart,
            "여러 변수를 범주별로 나란히 비교하면 자료 간 차이를 한눈에 볼 수 있습니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_comparative_bar", None, exc, start)


def _schema(required: list[str], properties: dict) -> dict:
    return {"type": "object", "required": required, "properties": properties}


SYNTHESIS_TOOLS: dict[str, ToolDefinition] = {
    "compute_cross_dataset_comparison": ToolDefinition(
        "compute_cross_dataset_comparison",
        "결합한 여러 자료의 대표값을 컬럼별로 비교합니다.",
        _schema(
            ["value_columns", "statistics"],
            {
                "value_columns": {"type": "array", "items": {"type": "string"}},
                "statistics": {"type": "array", "items": {"type": "string"}},
            },
        ),
        {},
        compute_cross_dataset_comparison,
        ["high"],
    ),
    "compute_cross_correlation": ToolDefinition(
        "compute_cross_correlation",
        "결합한 자료에서 두 컬럼의 피어슨 상관계수를 계산합니다.",
        _schema(
            ["x_column", "y_column"],
            {"x_column": {"type": "string"}, "y_column": {"type": "string"}},
        ),
        {},
        compute_cross_correlation,
        ["high"],
    ),
    "plot_comparative_line": ToolDefinition(
        "plot_comparative_line",
        "결합한 자료의 여러 변수를 하나의 선그래프로 겹쳐 비교합니다.",
        _schema(
            ["x_col", "y_cols"],
            {
                "x_col": {"type": "string"},
                "y_cols": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_comparative_line,
        ["high"],
    ),
    "plot_comparative_bar": ToolDefinition(
        "plot_comparative_bar",
        "결합한 자료의 여러 변수를 범주별 막대그래프로 비교합니다.",
        _schema(
            ["category_col", "value_cols"],
            {
                "category_col": {"type": "string"},
                "value_cols": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_comparative_bar,
        ["high"],
    ),
}
