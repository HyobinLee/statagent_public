import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.patches import Polygon as MplPolygon

from app.config import get_settings
from app.core.errors import AppError
from app.services.dataset_service import DatasetService
from app.services.map_service import MapService
from app.services.map_tiles import fetch_basemap, lonlat_to_mercator
from app.services.region_codes import region_info
from app.services.sgis_boundary import fetch_regions, fetch_sido_boundaries
from app.tools.chart_tools import GROUP_MARKERS, _base_figure, _save_chart
from app.tools.schemas import start_timer, tool_failure, tool_success

MAX_MAP_LABELS = 30
MAX_MAP_POINTS = 500
MAX_MAP_GROUPS = 8
BBOX_PADDING_RATIO = 0.12
MIN_BBOX_DEGREES = 0.01


def _padded_bounds(values: pd.Series, padding_ratio: float = BBOX_PADDING_RATIO) -> tuple[float, float]:
    low, high = float(values.min()), float(values.max())
    span = high - low
    if span < MIN_BBOX_DEGREES:
        center = (low + high) / 2
        low, high = center - MIN_BBOX_DEGREES / 2, center + MIN_BBOX_DEGREES / 2
        span = high - low
    padding = span * padding_ratio
    return low - padding, high + padding


def plot_map(
    dataset_id: str,
    lat_col: str,
    lon_col: str,
    color_col: str,
    size_col: str | None = None,
    group_by: str | None = None,
    title: str | None = None,
) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        numeric_columns = [lat_col, lon_col, color_col]
        if size_col:
            numeric_columns.append(size_col)
        service.require_numeric_columns(dataset_id, numeric_columns)
        if group_by:
            service.require_columns(dataset_id, [group_by])

        df = service.read_dataframe(dataset_id)
        wanted = list(dict.fromkeys(numeric_columns + ([group_by] if group_by else [])))
        clean = df[wanted].copy()
        for column in numeric_columns:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=wanted)

        if clean.empty:
            raise AppError(
                "NO_VALID_COORDINATES",
                "지도에 표시할 좌표가 없습니다.",
                "위도, 경도, 값 항목에 빈칸이 없는 자료를 선택해 주세요.",
            )
        in_range = clean[lat_col].between(-90, 90) & clean[lon_col].between(-180, 180)
        dropped = int((~in_range).sum())
        clean = clean[in_range]
        if clean.empty:
            raise AppError(
                "INVALID_COORDINATE_RANGE",
                "위도와 경도 값이 지구 좌표 범위를 벗어났습니다.",
                "위도는 -90~90, 경도는 -180~180 범위의 컬럼을 선택해 주세요.",
            )
        if len(clean) > MAX_MAP_POINTS:
            raise AppError(
                "TOO_MANY_POINTS",
                f"지도에는 점 {MAX_MAP_POINTS}개 이하만 표시할 수 있습니다.",
                "자료를 줄이거나 다른 분석 방법을 선택해 주세요.",
            )

        warnings = _base_figure()
        if dropped:
            warnings.append(f"좌표 범위를 벗어난 {dropped}개 행은 지도에서 제외했습니다.")

        west, east = _padded_bounds(clean[lon_col])
        south, north = _padded_bounds(clean[lat_col])
        axes = plt.gca()

        basemap = fetch_basemap(west, south, east, north)
        if basemap is None:
            warnings.append("배경지도를 불러오지 못해 좌표만 표시했습니다.")
        else:
            image, extent = basemap
            axes.imshow(np.asarray(image), extent=extent, zorder=1, interpolation="bilinear")

        mercator = [lonlat_to_mercator(lon, lat) for lon, lat in zip(clean[lon_col], clean[lat_col], strict=True)]
        xs = np.array([point[0] for point in mercator])
        ys = np.array([point[1] for point in mercator])

        if size_col:
            values = clean[size_col].to_numpy(dtype=float)
            span = values.max() - values.min()
            sizes = 40 + (values - values.min()) / span * 220 if span > 0 else np.full(len(values), 80.0)
        else:
            sizes = np.full(len(clean), 80.0)

        if group_by:
            labels = clean[group_by].astype(str)
            group_names = list(dict.fromkeys(labels))
            if len(group_names) > MAX_MAP_GROUPS:
                raise AppError(
                    "TOO_MANY_GROUPS",
                    f"지도의 그룹은 최대 {MAX_MAP_GROUPS}개까지만 구분할 수 있습니다.",
                    "그룹 수가 적은 컬럼을 선택하거나 그룹 구분 없이 그려 주세요.",
                )
            markers = {name: GROUP_MARKERS[index % len(GROUP_MARKERS)] for index, name in enumerate(group_names)}
            color_values = clean[color_col].to_numpy(dtype=float)
            scatter = None
            for name in group_names:
                mask = (labels == name).to_numpy()
                scatter = axes.scatter(
                    xs[mask],
                    ys[mask],
                    c=color_values[mask],
                    cmap="Reds",
                    vmin=clean[color_col].min(),
                    vmax=clean[color_col].max(),
                    s=sizes[mask],
                    marker=markers[name],
                    edgecolor="black",
                    linewidth=0.6,
                    zorder=3,
                )
            handles = [
                plt.Line2D(
                    [0],
                    [0],
                    marker=markers[name],
                    color="w",
                    markerfacecolor="grey",
                    markeredgecolor="black",
                    markersize=9,
                    label=name,
                )
                for name in group_names
            ]
            axes.legend(handles=handles, title=group_by, fontsize=7, loc="lower left")
        else:
            scatter = axes.scatter(
                xs,
                ys,
                c=clean[color_col],
                cmap="Reds",
                s=sizes,
                edgecolor="black",
                linewidth=0.6,
                zorder=3,
            )

        colorbar = plt.colorbar(scatter, ax=axes, fraction=0.04, pad=0.02)
        colorbar.set_label(color_col, rotation=270, labelpad=16)

        axes.set_xlim(*sorted(lonlat_to_mercator(lon, 0.0)[0] for lon in (west, east)))
        axes.set_ylim(*sorted(lonlat_to_mercator(0.0, lat)[1] for lat in (south, north)))
        axes.set_axis_off()
        axes.text(
            0.99,
            0.01,
            get_settings().map_tile_attribution,
            transform=axes.transAxes,
            fontsize=6.5,
            color="#333333",
            ha="right",
            va="bottom",
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1.5},
            zorder=4,
        )

        legend_parts = [f"색={color_col}"]
        if size_col:
            legend_parts.append(f"크기={size_col}")
        if group_by:
            legend_parts.append(f"모양={group_by}")
        chart_title = title or f"지도 위 {color_col} 분포 ({', '.join(legend_parts)})"
        chart = _save_chart(
            chart_title,
            f"각 지점의 위치를 지도 위에 표시하고 {color_col} 값을 색으로 나타냈습니다.",
        )
        return tool_success(
            "plot_map",
            dataset_id,
            chart,
            "값이 큰 지점이 지도의 특정 구역에 몰려 있는지 살펴보세요. 몰려 있다면 그 이유를 생각해 볼 수 있습니다.",
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_map", dataset_id, exc, start)


def _ring_centroid(ring: list[tuple[float, float]]) -> tuple[float, float, float]:
    area = 0.0
    cx = 0.0
    cy = 0.0
    for index in range(len(ring)):
        x0, y0 = ring[index]
        x1, y1 = ring[(index + 1) % len(ring)]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-12:
        return ring[0][0], ring[0][1], 0.0
    area *= 0.5
    return cx / (6 * area), cy / (6 * area), abs(area)


def _label_point(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    best = max((_ring_centroid(ring) for ring in rings), key=lambda item: item[2])
    return best[0], best[1]


def _draw_region_polygons(
    axes,
    regions: list[dict],
    boundaries: dict[str, list[list[tuple[float, float]]]],
) -> tuple[int, list[tuple[float, float]], dict[str, tuple[float, float]]]:
    filled = 0
    points: list[tuple[float, float]] = []
    label_points: dict[str, tuple[float, float]] = {}

    def total_area(region: dict) -> float:
        rings = boundaries.get(str(region.get("region_code") or "")) or []
        return sum(_ring_centroid(ring)[2] for ring in rings)

    for region in sorted(regions, key=total_area, reverse=True):
        code = str(region.get("region_code") or "")
        rings = boundaries.get(code)
        if not rings:
            continue
        filled += 1
        label_points[code] = _label_point(rings)
        for ring in rings:
            points.extend(ring)
            mercator = [lonlat_to_mercator(lon, lat) for lon, lat in ring]
            axes.add_patch(
                MplPolygon(
                    mercator,
                    closed=True,
                    facecolor=region.get("color") or "#3498db",
                    edgecolor="#33333388",
                    linewidth=0.6,
                    alpha=0.78,
                    zorder=3,
                )
            )
    return filled, points, label_points


def _boundaries_for(choropleth: dict) -> dict[str, list[list[tuple[float, float]]]]:
    level = choropleth.get("level") or "sido"
    if level == "sido":
        return fetch_sido_boundaries() or {}
    parent_code, _ = MapService().resolve_parent(level, choropleth.get("parent_region"))
    records = fetch_regions(level, parent_code) or []
    return {record["sgis_code"]: record["rings"] for record in records}


def _render_region_map(choropleth: dict, value_col: str) -> tuple[dict, list[str]]:
    regions = [region for region in choropleth.get("regions", []) if region.get("lat") and region.get("lng")]
    if not regions:
        raise AppError(
            "MAP_NO_MATCHED_REGION",
            "지도에 표시할 수 있는 지역이 없습니다.",
            "지역 항목에 시도 이름(예: 서울특별시)이 들어 있는지 확인해 주세요.",
        )

    warnings = _base_figure()
    axes = plt.gca()

    boundaries = _boundaries_for(choropleth)
    filled, boundary_points, label_points = (
        _draw_region_polygons(axes, regions, boundaries) if boundaries else (0, [], {})
    )
    circle_regions = [region for region in regions if not boundaries.get(str(region.get("region_code") or ""))]
    if not boundaries:
        warnings.append("시도 경계를 불러오지 못해 지역 중심점에 원으로 표시했습니다.")
    elif circle_regions:
        warnings.append(f"경계를 찾지 못한 {len(circle_regions)}개 지역은 중심점에 원으로 표시했습니다.")

    if boundary_points:
        lons = pd.Series([point[0] for point in boundary_points])
        lats = pd.Series([point[1] for point in boundary_points])
        padding_ratio = 0.03
    else:
        lons = pd.Series([float(region["lng"]) for region in regions])
        lats = pd.Series([float(region["lat"]) for region in regions])
        padding_ratio = BBOX_PADDING_RATIO
    west, east = _padded_bounds(lons, padding_ratio)
    south, north = _padded_bounds(lats, padding_ratio)

    basemap = fetch_basemap(west, south, east, north)
    if basemap is None:
        warnings.append("배경지도를 불러오지 못해 지역만 표시했습니다.")
    else:
        image, extent = basemap
        axes.imshow(np.asarray(image), extent=extent, zorder=1, interpolation="bilinear")

    if circle_regions:
        values = np.array([float(region["value"]) for region in circle_regions])
        span = values.max() - values.min()
        sizes = 120 + (values - values.min()) / span * 380 if span > 0 else np.full(len(values), 260.0)
        for region, size in zip(circle_regions, sizes, strict=True):
            x, y = lonlat_to_mercator(float(region["lng"]), float(region["lat"]))
            axes.scatter(
                [x],
                [y],
                s=size,
                c=region.get("color") or "#3498db",
                edgecolor="black",
                linewidth=0.7,
                alpha=0.85,
                zorder=4,
            )

    for region in regions if len(regions) <= MAX_MAP_LABELS else []:
        code = str(region.get("region_code") or "")
        info = region_info(code)
        anchor = (
            (float(region["lng"]), float(region["lat"]))
            if info
            else label_points.get(code, (float(region["lng"]), float(region["lat"])))
        )
        x, y = lonlat_to_mercator(anchor[0], anchor[1])
        is_circle = region in circle_regions
        label = str(info["short"] if info else region.get("region_name", ""))
        axes.annotate(
            label.split()[-1] if label else "",
            (x, y),
            xytext=(0, -11 if is_circle else 0),
            textcoords="offset points",
            fontsize=6.5,
            ha="center",
            va="top" if is_circle else "center",
            zorder=5,
        )

    handles = [
        Patch(
            facecolor=item.get("color") or "#3498db",
            edgecolor="#333333",
            linewidth=0.6,
            label=item.get("label", ""),
        )
        if filled
        else plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=item.get("color") or "#3498db",
            markeredgecolor="black",
            markersize=9,
            label=item.get("label", ""),
        )
        for item in choropleth.get("legend", [])
    ]
    if handles:
        scale = choropleth.get("color_scale") or {}
        legend_title = value_col
        if scale.get("type_label"):
            legend_title = f"{value_col}\n{scale['type_label']} · {scale.get('name', '')}"
            if scale.get("type") == "diverging":
                legend_title += "\n(가운데 회색이 기준)"
        legend = axes.legend(
            handles=handles,
            title=legend_title,
            fontsize=7,
            title_fontsize=8,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            frameon=False,
        )
        legend.get_title().set_multialignment("left")

    axes.set_xlim(*sorted(lonlat_to_mercator(lon, 0.0)[0] for lon in (west, east)))
    axes.set_ylim(*sorted(lonlat_to_mercator(0.0, lat)[1] for lat in (south, north)))
    axes.set_axis_off()
    axes.text(
        0.99,
        0.01,
        get_settings().map_tile_attribution,
        transform=axes.transAxes,
        fontsize=6.5,
        color="#333333",
        ha="right",
        va="bottom",
        bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1.5},
        zorder=5,
    )

    alt_text = (
        f"시도 경계를 {value_col} 값에 따라 색으로 칠한 지도입니다."
        if filled
        else f"각 지역의 위치에 원을 찍고 {value_col} 값을 색과 크기로 나타낸 지도입니다."
    )
    chart = _save_chart(choropleth.get("title") or f"지역별 {value_col} 분포", alt_text)
    return chart, warnings


def plot_choropleth(
    dataset_id: str,
    region_col: str,
    value_col: str,
    map_level: str = "sido",
    parent_region: str = "",
    color_scale: str = "",
    title: str = "",
    time_column: str = "",
    time_point: str = "",
    n_classes: int = 5,
) -> dict:
    start = start_timer()
    try:
        service = MapService()
        result = service.generate_choropleth(
            dataset_id=dataset_id,
            region_column=region_col,
            value_column=value_col,
            level=map_level,
            parent_region=parent_region or None,
            time_column=time_column or None,
            time_point=time_point or None,
            n_classes=n_classes,
            color_scale=color_scale or None,
            title=title or None,
        )
        choropleth = result.get("choropleth", {})
        stats = result.get("statistics", {})
        warnings = list(result.get("warnings", []))
        chart, chart_warnings = _render_region_map(choropleth, value_col)
        warnings.extend(chart_warnings)
        hint = (
            f"지역별 {value_col}의 분포를 지도에서 확인합니다. "
            f"매핑된 지역 {stats.get('matched_count', 0)}개, "
            f"미매핑 {stats.get('unmatched_count', 0)}개."
        )
        if warnings:
            hint += " " + " ".join(warnings[:2])

        return tool_success(
            "plot_choropleth",
            dataset_id,
            {
                **chart,
                "choropleth": choropleth,
                "statistics": stats,
                "warnings": warnings,
                "map_type": "choropleth",
            },
            hint,
            start,
            warnings,
        )
    except AppError as exc:
        plt.close()
        return tool_failure("plot_choropleth", dataset_id, exc, start)
