from uuid import uuid4

import matplotlib

matplotlib.use("Agg")

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.errors import AppError
from app.core.time import now_utc
from app.services.chart_storage import get_chart_storage
from app.services.dataset_service import DatasetService
from app.tools.schemas import start_timer, tool_failure, tool_success

CHART_WIDTH = 900
CHART_HEIGHT = 540
MAX_BOXPLOT_GROUPS = 5


def _configure_font() -> list[str]:
    warnings: list[str] = []
    font_names = {font.name for font in font_manager.fontManager.ttflist}
    if "NanumGothic" in font_names:
        plt.rcParams["font.family"] = "NanumGothic"
    elif "Malgun Gothic" in font_names:
        plt.rcParams["font.family"] = "Malgun Gothic"
        warnings.append("NanumGothic이 없어 Malgun Gothic으로 대체했습니다.")
    else:
        warnings.append("한글 폰트를 찾지 못해 matplotlib 기본 폰트로 표시했습니다.")
    plt.rcParams["axes.unicode_minus"] = False
    return warnings


def _save_chart(title: str, alt_text: str) -> dict:
    settings = get_settings()
    settings.local_chart_dir.mkdir(parents=True, exist_ok=True)
    chart_id = f"chart_{now_utc().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    png_path = settings.local_chart_dir / f"{chart_id}.png"
    svg_path = settings.local_chart_dir / f"{chart_id}.svg"
    plt.title(title)
    plt.tight_layout()
    plt.savefig(png_path, format="png", dpi=120)
    plt.savefig(svg_path, format="svg")
    plt.close()
    storage_payload = get_chart_storage().publish_chart(chart_id, png_path, svg_path)
    return {
        "chart_id": chart_id,
        "png_url": storage_payload["png_url"],
        "svg_url": storage_payload["svg_url"],
        "storage_backend": storage_payload["storage_backend"],
        "gcs_png_uri": storage_payload.get("gcs_png_uri"),
        "gcs_svg_uri": storage_payload.get("gcs_svg_uri"),
        "alt_text": alt_text,
        "dimensions": {"width": CHART_WIDTH, "height": CHART_HEIGHT},
    }


def _base_figure() -> list[str]:
    warnings = _configure_font()
    plt.figure(figsize=(CHART_WIDTH / 120, CHART_HEIGHT / 120), dpi=120)
    return warnings


def plot_bar(
    dataset_id: str,
    category_col: str,
    value_col: str,
    group_col: str | None = None,
    sort_order: str | None = None,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_columns(dataset_id, [category_col])
        service.require_numeric_columns(dataset_id, [value_col])
        if group_col:
            service.require_columns(dataset_id, [group_col])
        df = service.read_dataframe(dataset_id)
        if group_col:
            category_count = df[category_col].dropna().nunique()
            group_count = df[group_col].dropna().nunique()
            if category_count > 20:
                raise AppError(
                    "TOO_MANY_CATEGORIES",
                    "막대그래프의 범주는 20개 이하만 사용할 수 있습니다.",
                    "범주가 적은 컬럼을 선택하거나 자료를 필터링해 주세요.",
                )
            if group_count > 5:
                raise AppError(
                    "TOO_MANY_SERIES",
                    "다중 막대그래프의 추가 범주는 최대 5개까지만 가능합니다.",
                    "추가 범주 값을 줄이거나 자료를 필터링해 주세요.",
                )
            grouped = df.groupby([category_col, group_col], dropna=False)[value_col].sum().unstack(fill_value=0)
            first_seen = [group for group in pd.unique(df[group_col].dropna()) if group in grouped.columns]
            rest = [group for group in grouped.columns if group not in first_seen]
            grouped = grouped[first_seen + rest]
            if sort_order == "asc":
                grouped = grouped.loc[grouped.sum(axis=1).sort_values().index]
            elif sort_order == "desc":
                grouped = grouped.loc[grouped.sum(axis=1).sort_values(ascending=False).index]
        else:
            grouped = df.groupby(category_col, dropna=False)[value_col].sum()
            if sort_order == "asc":
                grouped = grouped.sort_values()
            elif sort_order == "desc":
                grouped = grouped.sort_values(ascending=False)
        if len(grouped) > 20:
            raise AppError(
                "TOO_MANY_CATEGORIES",
                "막대그래프의 범주는 20개 이하만 사용할 수 있습니다.",
                "범주가 적은 컬럼을 선택하거나 자료를 필터링해 주세요.",
            )
        warnings = _base_figure()
        palette = ["#287c7a", "#2563eb", "#b23a48", "#5f6f52", "#7a4c9f"]
        grouped.plot(kind="bar", color=palette if group_col else "#287c7a")
        plt.xlabel(category_col)
        plt.ylabel(value_col)
        chart_title = title or (
            f"{category_col}·{group_col}별 {value_col}" if group_col else f"{category_col}별 {value_col}"
        )
        chart = _save_chart(chart_title, f"{category_col}별 {value_col} 값을 막대그래프로 표시했습니다.")
        return tool_success(
            "plot_bar",
            dataset_id,
            chart,
            "막대그래프는 범주별 크기를 비교할 때 유용합니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_bar", dataset_id, exc, start)


def plot_histogram(dataset_id: str, column: str, bins: int = 10, title: str | None = None) -> dict:
    start = start_timer()
    try:
        if bins < 5 or bins > 20:
            raise AppError(
                "INVALID_BINS",
                "히스토그램 구간 수는 5개 이상 20개 이하만 가능합니다.",
                "bins 값을 5에서 20 사이로 조정해 주세요.",
            )
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [column])
        df = service.read_dataframe(dataset_id)
        warnings = _base_figure()
        plt.hist(pd.to_numeric(df[column], errors="coerce").dropna(), bins=bins, color="#5f6f52")
        plt.xlabel(column)
        plt.ylabel("frequency")
        chart_title = title or f"{column} 분포"
        chart = _save_chart(chart_title, f"{column} 값의 분포를 히스토그램으로 표시했습니다.")
        return tool_success(
            "plot_histogram",
            dataset_id,
            chart,
            "히스토그램은 값이 어느 구간에 많이 모여 있는지 보여줍니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_histogram", dataset_id, exc, start)


def plot_boxplot(
    dataset_id: str,
    columns: list[str],
    group_by: str | None = None,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        if not columns:
            raise AppError(
                "INVALID_ARGUMENT",
                "상자그림에는 수치형 컬럼이 하나 이상 필요합니다.",
                "분석할 수치형 컬럼을 선택해 주세요.",
            )
        service = DatasetService()
        service.require_numeric_columns(dataset_id, columns)
        df = service.read_dataframe(dataset_id)
        warnings = _base_figure()
        if group_by:
            service.require_columns(dataset_id, [group_by])
            if len(columns) > 1:
                warnings.append(
                    f"범주별 상자그림은 '{columns[0]}' 항목 하나만 사용합니다. "
                    f"나머지 항목({', '.join(columns[1:])})은 그리지 않았습니다."
                )
            groups = df[group_by].dropna().unique()
            if len(groups) > MAX_BOXPLOT_GROUPS:
                raise AppError(
                    "TOO_MANY_GROUPS",
                    f"상자그림의 그룹은 최대 {MAX_BOXPLOT_GROUPS}개까지만 비교할 수 있습니다.",
                    "그룹 수가 적은 컬럼을 선택해 주세요.",
                )
            series_by_group = [
                (
                    str(group),
                    pd.to_numeric(df[df[group_by] == group][columns[0]], errors="coerce").dropna(),
                )
                for group in groups
            ]
            empty_groups = [name for name, values in series_by_group if values.empty]
            series_by_group = [(name, values) for name, values in series_by_group if not values.empty]
            if empty_groups:
                warnings.append(f"{', '.join(empty_groups)} 그룹은 '{columns[0]}' 값이 없어 상자그림에서 제외했습니다.")
            if not series_by_group:
                raise AppError(
                    "NO_VALID_GROUP_VALUES",
                    f"'{group_by}'로 나눈 어느 그룹에도 '{columns[0]}'의 값이 없습니다.",
                    "빈칸이 적은 항목을 고르거나 다른 범주 컬럼으로 나눠 주세요.",
                )
            plt.boxplot([values for _, values in series_by_group])
            plt.xticks(
                range(1, len(series_by_group) + 1),
                [name for name, _ in series_by_group],
            )
            plt.xlabel(group_by)
            plt.ylabel(columns[0])
            chart_title = title or f"{group_by}별 {columns[0]} 상자그림"
        else:
            df[columns].apply(pd.to_numeric, errors="coerce").plot(kind="box")
            chart_title = title or f"{', '.join(columns)} 상자그림"
        chart = _save_chart(chart_title, "선택한 수치형 컬럼의 분포를 상자그림으로 표시했습니다.")
        return tool_success(
            "plot_boxplot",
            dataset_id,
            chart,
            "상자그림은 중앙값, 사분위수, 전체 퍼짐을 함께 살펴볼 때 유용합니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_boxplot", dataset_id, exc, start)


def plot_scatter(
    dataset_id: str,
    x_col: str,
    y_col: str,
    show_trendline: bool = False,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [x_col, y_col])
        df = service.read_dataframe(dataset_id)
        clean = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(clean) > 500:
            raise AppError(
                "TOO_MANY_POINTS",
                "산점도는 점 500개 이하만 표시할 수 있습니다.",
                "자료를 줄이거나 다른 분석 방법을 선택해 주세요.",
            )
        warnings = _base_figure()
        plt.scatter(clean[x_col], clean[y_col], color="#7a4c9f", alpha=0.82)
        if show_trendline and len(clean) >= 2:
            if clean[x_col].std(ddof=1) > 0:
                slope, intercept = np.polyfit(clean[x_col], clean[y_col], 1)
                xs = np.linspace(clean[x_col].min(), clean[x_col].max(), 100)
                plt.plot(xs, slope * xs + intercept, color="#b23a48", linewidth=2)
            else:
                warnings.append(f"'{x_col}' 값이 모두 같아 추세선은 그리지 않았습니다.")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        chart_title = title or f"{x_col}와 {y_col} 산점도"
        chart = _save_chart(chart_title, f"{x_col}와 {y_col}의 관계를 산점도로 표시했습니다.")
        return tool_success(
            "plot_scatter",
            dataset_id,
            chart,
            "산점도는 두 수치형 변수 사이의 관계를 눈으로 확인할 때 유용합니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_scatter", dataset_id, exc, start)


GROUP_COLORS = ["#4C72B0", "#C44E52", "#55A868", "#8172B2", "#CCB974", "#64B5CD", "#E17C05", "#777777"]
GROUP_MARKERS = ["o", "s", "^", "D", "P", "X", "v", "*"]


def plot_grouped_scatter(
    dataset_id: str,
    x_col: str,
    y_col: str,
    group_by: str,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        from app.tools.stats_tools import prepare_grouped_correlation

        service = DatasetService()
        service.require_numeric_columns(dataset_id, [x_col, y_col])
        service.require_columns(dataset_id, [group_by])
        prepared = prepare_grouped_correlation(service.read_dataframe(dataset_id), x_col, y_col, group_by)
        clean = prepared["clean"]
        labels = prepared["labels"]
        if len(clean) > 500:
            raise AppError(
                "TOO_MANY_POINTS",
                "산점도는 점 500개 이하만 표시할 수 있습니다.",
                "자료를 줄이거나 다른 분석 방법을 선택해 주세요.",
            )

        warnings = _base_figure()
        group_names = prepared["group_names"]
        colors = {name: GROUP_COLORS[index % len(GROUP_COLORS)] for index, name in enumerate(group_names)}
        markers = {name: GROUP_MARKERS[index % len(GROUP_MARKERS)] for index, name in enumerate(group_names)}
        axes = plt.gca()

        for name in group_names:
            subset = clean[labels == name]
            axes.scatter(
                subset[x_col],
                subset[y_col],
                color=colors[name],
                marker=markers[name],
                s=48,
                alpha=0.85,
                edgecolor="white",
                linewidth=0.5,
                label=name,
                zorder=3,
            )
            if len(subset) >= 2 and subset[x_col].std(ddof=1) > 0:
                slope, intercept = np.polyfit(subset[x_col], subset[y_col], 1)
                xs = np.linspace(subset[x_col].min(), subset[x_col].max(), 50)
                axes.plot(xs, slope * xs + intercept, color=colors[name], linewidth=1.8, zorder=2)

        if clean[x_col].std(ddof=1) > 0:
            slope, intercept = np.polyfit(clean[x_col], clean[y_col], 1)
            xs = np.linspace(clean[x_col].min(), clean[x_col].max(), 50)
            axes.plot(xs, slope * xs + intercept, color="black", linestyle="--", linewidth=1.8, zorder=2)

        overall = prepared["data"]["overall"]
        summary_lines = [f"전체(n={overall['sample_size']}): r={overall['pearson_correlation']:.3f}"]
        for item in prepared["data"]["groups"]:
            if item["pearson_correlation"] is None:
                summary_lines.append(f"{item['group']}(n={item['sample_size']}): {item['note']}")
            else:
                summary_lines.append(f"{item['group']}(n={item['sample_size']}): r={item['pearson_correlation']:.3f}")
        for index, line in enumerate(summary_lines):
            color = "black" if index == 0 else colors[group_names[index - 1]]
            axes.text(
                0.02,
                0.98 - index * 0.055,
                line,
                transform=axes.transAxes,
                color=color,
                fontsize=8,
                fontweight="bold",
                va="top",
                bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none", "pad": 1.5},
            )

        axes.set_xlabel(x_col)
        axes.set_ylabel(y_col)
        axes.legend(title=group_by, fontsize=7, loc="lower right")
        chart_title = title or f"{group_by}별 {x_col}와 {y_col} 관계"
        chart = _save_chart(
            chart_title,
            f"{group_by} 집단별로 {x_col}와 {y_col}의 관계를 산점도와 추세선으로 표시했습니다.",
        )
        chart["sign_contrast"] = prepared["data"]["sign_contrast"]
        return tool_success(
            "plot_grouped_scatter",
            dataset_id,
            chart,
            "집단별 추세선의 기울기 방향이 서로 다른지 확인해 보세요. 검정 점선은 전체 추세선입니다.",
            start,
            warnings + prepared["warnings"],
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_grouped_scatter", dataset_id, exc, start)


def plot_line(
    dataset_id: str,
    x_col: str,
    y_col: str,
    multi_series: str | None = None,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_columns(dataset_id, [x_col])
        service.require_numeric_columns(dataset_id, [y_col])
        if multi_series:
            service.require_columns(dataset_id, [multi_series])
        df = service.read_dataframe(dataset_id).sort_values(x_col)
        warnings = _base_figure()
        if multi_series:
            groups = df[multi_series].dropna().unique()
            if len(groups) > 5:
                raise AppError(
                    "TOO_MANY_SERIES",
                    "선그래프의 다중 계열은 최대 5개까지만 가능합니다.",
                    "계열 수가 적은 컬럼을 선택해 주세요.",
                )
            for group in groups:
                subset = df[df[multi_series] == group]
                plt.plot(subset[x_col], subset[y_col], marker="o", label=str(group))
            plt.legend()
        else:
            plt.plot(df[x_col], df[y_col], marker="o", color="#2563eb")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        chart_title = title or f"{x_col}별 {y_col}"
        chart = _save_chart(chart_title, f"{x_col}에 따른 {y_col} 변화를 선그래프로 표시했습니다.")
        return tool_success(
            "plot_line",
            dataset_id,
            chart,
            "선그래프는 시간이나 순서에 따른 변화를 살펴볼 때 유용합니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_line", dataset_id, exc, start)


MAX_FREQUENCY_POLYGON_GROUPS = 5
FREQUENCY_POLYGON_COLORS = ["#287c7a", "#b23a48", "#2563eb", "#5f6f52", "#7a4c9f"]


def plot_frequency_polygon(
    dataset_id: str,
    column: str,
    bins: int = 10,
    group_by: str | None = None,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        if bins < 5 or bins > 20:
            raise AppError(
                "INVALID_BINS",
                "도수분포다각형 구간 수는 5개 이상 20개 이하만 가능합니다.",
                "bins 값을 5에서 20 사이로 조정해 주세요.",
            )
        service = DatasetService()
        service.require_numeric_columns(dataset_id, [column])
        df = service.read_dataframe(dataset_id)
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        if values.empty:
            raise AppError(
                "NO_VALID_VALUES",
                f"'{column}'에 유효한 값이 없습니다.",
                "다른 컬럼을 선택해 주세요.",
            )
        edges = np.histogram_bin_edges(values, bins=bins)
        midpoints = (edges[:-1] + edges[1:]) / 2
        bin_width = edges[1] - edges[0]
        extended_midpoints = np.concatenate(([midpoints[0] - bin_width], midpoints, [midpoints[-1] + bin_width]))
        inner_markers = list(range(1, len(extended_midpoints) - 1))
        warnings = _base_figure()

        if group_by:
            service.require_columns(dataset_id, [group_by])
            groups = df[group_by].dropna().unique()
            if len(groups) > MAX_FREQUENCY_POLYGON_GROUPS:
                raise AppError(
                    "TOO_MANY_GROUPS",
                    f"도수분포다각형의 그룹은 최대 {MAX_FREQUENCY_POLYGON_GROUPS}개까지만 비교할 수 있습니다.",
                    "그룹 수가 적은 컬럼을 선택해 주세요.",
                )
            series_by_group = [
                (str(group), pd.to_numeric(df[df[group_by] == group][column], errors="coerce").dropna())
                for group in groups
            ]
            empty_groups = [name for name, series in series_by_group if series.empty]
            series_by_group = [(name, series) for name, series in series_by_group if not series.empty]
            if empty_groups:
                warnings.append(f"{', '.join(empty_groups)} 그룹은 '{column}' 값이 없어 그래프에서 제외했습니다.")
            if not series_by_group:
                raise AppError(
                    "NO_VALID_GROUP_VALUES",
                    f"'{group_by}'로 나눈 어느 그룹에도 '{column}'의 값이 없습니다.",
                    "빈칸이 적은 항목을 고르거나 다른 범주 컬럼으로 나눠 주세요.",
                )
            for index, (name, series) in enumerate(series_by_group):
                counts, _ = np.histogram(series, bins=edges)
                extended_counts = np.concatenate(([0], counts, [0]))
                color = FREQUENCY_POLYGON_COLORS[index % len(FREQUENCY_POLYGON_COLORS)]
                plt.plot(
                    extended_midpoints, extended_counts, marker="o", markevery=inner_markers, color=color, label=name
                )
            plt.legend(title=group_by)
            chart_title = title or f"{group_by}별 {column} 도수분포다각형"
        else:
            counts, _ = np.histogram(values, bins=edges)
            extended_counts = np.concatenate(([0], counts, [0]))
            plt.plot(extended_midpoints, extended_counts, marker="o", markevery=inner_markers, color="#287c7a")
            chart_title = title or f"{column} 도수분포다각형"

        plt.xlabel(column)
        plt.ylabel("도수")
        chart = _save_chart(
            chart_title,
            f"{column} 값을 구간으로 나누고 구간 중앙값을 도수 선분으로 이은 도수분포다각형입니다.",
        )
        return tool_success(
            "plot_frequency_polygon",
            dataset_id,
            chart,
            "도수분포다각형은 구간별 도수를 선으로 이어 분포의 모양을 한눈에 보여줍니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_frequency_polygon", dataset_id, exc, start)


def plot_stem_leaf(dataset_id: str, column: str) -> dict:
    start = start_timer()
    try:
        DatasetService().require_numeric_columns(dataset_id, [column])
        return tool_success(
            "plot_stem_leaf",
            dataset_id,
            {"stems": [], "note": "v0.1 stub: 줄기와 잎 그림은 schema만 제공합니다."},
            "줄기와 잎 그림은 v0.1에서 stub로 남겨 두었습니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("plot_stem_leaf", dataset_id, exc, start)


def plot_pie(dataset_id: str, category_col: str, value_col: str, title: str | None = None) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_columns(dataset_id, [category_col])
        service.require_numeric_columns(dataset_id, [value_col])
        df = service.read_dataframe(dataset_id)
        grouped = df.groupby(category_col, dropna=False)[value_col].sum()
        if len(grouped) > 8:
            raise AppError(
                "TOO_MANY_CATEGORIES",
                "원그래프의 범주는 8개 이하만 사용할 수 있습니다.",
                "범주가 적은 컬럼을 선택해 주세요.",
            )
        negative = [str(label) for label, value in grouped.items() if value < 0]
        if negative:
            raise AppError(
                "NEGATIVE_VALUES_NOT_ALLOWED",
                f"원그래프는 음수 값을 표시할 수 없습니다: {', '.join(negative[:3])}",
                "값이 0 이상인 항목을 고르거나, 증감을 보려면 막대그래프를 사용해 주세요.",
            )
        if float(grouped.sum()) <= 0:
            raise AppError(
                "NO_POSITIVE_VALUES",
                "합계가 0이어서 원그래프로 비율을 나타낼 수 없습니다.",
                "0보다 큰 값이 있는 항목을 선택해 주세요.",
            )
        warnings = _base_figure()
        plt.pie(grouped.values, labels=[str(label) for label in grouped.index], autopct="%1.1f%%")
        chart_title = title or f"{category_col}별 비율"
        chart = _save_chart(chart_title, f"{category_col}별 {value_col} 비율을 원그래프로 표시했습니다.")
        return tool_success(
            "plot_pie",
            dataset_id,
            chart,
            "원그래프는 전체에서 각 범주가 차지하는 비율을 볼 때 사용합니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_pie", dataset_id, exc, start)
