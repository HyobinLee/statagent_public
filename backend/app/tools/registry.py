from app.tools.chart_tools import (
    plot_bar,
    plot_boxplot,
    plot_frequency_polygon,
    plot_grouped_scatter,
    plot_histogram,
    plot_line,
    plot_pie,
    plot_scatter,
    plot_stem_leaf,
)
from app.tools.dataset_tools import (
    get_dataset_schema,
    get_dataset_summary,
    list_datasets_for_topic,
    list_topics,
)
from app.tools.map_tools import plot_choropleth, plot_map
from app.tools.schemas import ToolDefinition
from app.tools.session_tools import get_inquiry_history, save_conclusion, save_inquiry_step
from app.tools.stats_tools import (
    compute_correlation,
    compute_descriptive_stats,
    compute_grouped_correlation,
    resample_compare,
)
from app.tools.table_tools import create_crosstab, create_frequency_table


def _schema(required: list[str], properties: dict) -> dict:
    return {"type": "object", "required": required, "properties": properties}


TOOLS: dict[str, ToolDefinition] = {
    "list_topics": ToolDefinition(
        "list_topics",
        "사용 가능한 탐구 주제를 조회합니다.",
        _schema([], {}),
        {},
        list_topics,
        ["middle", "high"],
    ),
    "list_datasets_for_topic": ToolDefinition(
        "list_datasets_for_topic",
        "주제에 연결된 자료를 조회합니다.",
        _schema(["topic_id"], {"topic_id": {"type": "string"}}),
        {},
        list_datasets_for_topic,
        ["middle", "high"],
    ),
    "get_dataset_schema": ToolDefinition(
        "get_dataset_schema",
        "자료의 컬럼 구조를 조회합니다.",
        _schema(["dataset_id"], {"dataset_id": {"type": "string"}}),
        {},
        get_dataset_schema,
        ["middle", "high"],
    ),
    "get_dataset_summary": ToolDefinition(
        "get_dataset_summary",
        "자료의 요약 정보를 조회합니다.",
        _schema(["dataset_id"], {"dataset_id": {"type": "string"}}),
        {},
        get_dataset_summary,
        ["middle", "high"],
    ),
    "compute_descriptive_stats": ToolDefinition(
        "compute_descriptive_stats",
        "평균, 중앙값, 표준편차 등 허용된 통계량을 계산합니다. group_by를 주면 집단별 요약 통계량을 나란히 비교합니다.",
        _schema(
            ["dataset_id", "columns", "statistics"],
            {
                "dataset_id": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "statistics": {"type": "array", "items": {"type": "string"}},
                "group_by": {"type": "string"},
            },
        ),
        {},
        compute_descriptive_stats,
        ["middle", "high"],
    ),
    "compute_correlation": ToolDefinition(
        "compute_correlation",
        "두 수치형 컬럼의 피어슨 상관계수를 계산합니다.",
        _schema(
            ["dataset_id", "x_column", "y_column"],
            {
                "dataset_id": {"type": "string"},
                "x_column": {"type": "string"},
                "y_column": {"type": "string"},
            },
        ),
        {},
        compute_correlation,
        ["high"],
    ),
    "compute_grouped_correlation": ToolDefinition(
        "compute_grouped_correlation",
        "집단을 나눠 전체 상관계수와 집단별 상관계수를 함께 계산합니다.",
        _schema(
            ["dataset_id", "x_column", "y_column", "group_by"],
            {
                "dataset_id": {"type": "string"},
                "x_column": {"type": "string"},
                "y_column": {"type": "string"},
                "group_by": {"type": "string"},
            },
        ),
        {},
        compute_grouped_correlation,
        ["high"],
    ),
    "resample_compare": ToolDefinition(
        "resample_compare",
        "두 집단의 평균 차이가 우연만으로 얼마나 날 수 있는지 집단 라벨을 무작위로 "
        "섞은 재표집 분포 그림으로 보여주고 관찰된 차이를 표시합니다. "
        "p값 등 검정 수치는 산출하지 않습니다(stats_tools.py 경계 주석 참조).",
        _schema(
            ["dataset_id", "value_column", "group_column"],
            {
                "dataset_id": {"type": "string"},
                "value_column": {"type": "string"},
                "group_column": {"type": "string"},
                "n_resamples": {"type": "integer"},
            },
        ),
        {},
        resample_compare,
        ["high"],
    ),
    "plot_grouped_scatter": ToolDefinition(
        "plot_grouped_scatter",
        "집단별 색과 추세선을 나눠 그린 산점도를 생성합니다.",
        _schema(
            ["dataset_id", "x_col", "y_col", "group_by"],
            {
                "dataset_id": {"type": "string"},
                "x_col": {"type": "string"},
                "y_col": {"type": "string"},
                "group_by": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_grouped_scatter,
        ["high"],
    ),
    "plot_map": ToolDefinition(
        "plot_map",
        "위도와 경도가 있는 자료를 지도 위에 표시합니다.",
        _schema(
            ["dataset_id", "lat_col", "lon_col", "color_col"],
            {
                "dataset_id": {"type": "string"},
                "lat_col": {"type": "string"},
                "lon_col": {"type": "string"},
                "color_col": {"type": "string"},
                "size_col": {"type": "string"},
                "group_by": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_map,
        ["middle", "high"],
    ),
    "plot_bar": ToolDefinition(
        "plot_bar",
        "막대그래프 PNG/SVG를 생성합니다.",
        _schema(
            ["dataset_id", "category_col", "value_col"],
            {
                "dataset_id": {"type": "string"},
                "category_col": {"type": "string"},
                "value_col": {"type": "string"},
                "group_col": {"type": "string"},
                "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_bar,
        ["middle", "high"],
    ),
    "plot_histogram": ToolDefinition(
        "plot_histogram",
        "히스토그램 PNG/SVG를 생성합니다.",
        _schema(
            ["dataset_id", "column", "bins"],
            {
                "dataset_id": {"type": "string"},
                "column": {"type": "string"},
                "bins": {"type": "integer", "minimum": 5, "maximum": 20},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_histogram,
        ["middle", "high"],
    ),
    "plot_boxplot": ToolDefinition(
        "plot_boxplot",
        "상자그림 PNG/SVG를 생성합니다.",
        _schema(
            ["dataset_id", "columns"],
            {
                "dataset_id": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "group_by": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_boxplot,
        ["high"],
    ),
    "plot_scatter": ToolDefinition(
        "plot_scatter",
        "산점도 PNG/SVG를 생성합니다.",
        _schema(
            ["dataset_id", "x_col", "y_col"],
            {
                "dataset_id": {"type": "string"},
                "x_col": {"type": "string"},
                "y_col": {"type": "string"},
                "show_trendline": {"type": "boolean"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_scatter,
        ["middle", "high"],
    ),
    "plot_line": ToolDefinition(
        "plot_line",
        "선그래프 PNG/SVG를 생성합니다.",
        _schema(
            ["dataset_id", "x_col", "y_col"],
            {
                "dataset_id": {"type": "string"},
                "x_col": {"type": "string"},
                "y_col": {"type": "string"},
                "multi_series": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_line,
        ["middle", "high"],
    ),
    "generate_interpretation_hints": ToolDefinition(
        "generate_interpretation_hints",
        "분석 결과에 대한 관찰점과 유도 질문을 생성합니다.",
        _schema(
            ["analysis_result", "student_level"],
            {
                "analysis_result": {"type": "object"},
                "student_level": {"type": "string", "enum": ["middle", "high", "middle_high"]},
            },
        ),
        {},
        lambda analysis_result, student_level="middle_high": {
            "success": True,
            "data": {
                "observations": ["그래프의 증가 또는 감소 흐름을 먼저 확인해 보세요."],
                "questions": ["이 변화가 모든 기간에서 같은가요?"],
            },
            "metadata": {"function": "generate_interpretation_hints", "validation_warnings": []},
            "explanation_hint": "학생이 스스로 결론을 쓰도록 돕는 질문입니다.",
        },
        ["middle", "high"],
    ),
    "plot_frequency_polygon": ToolDefinition(
        "plot_frequency_polygon",
        "도수분포다각형을 생성합니다.",
        _schema(
            ["dataset_id", "column", "bins"],
            {
                "dataset_id": {"type": "string"},
                "column": {"type": "string"},
                "bins": {"type": "integer", "minimum": 5, "maximum": 20},
                "group_by": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_frequency_polygon,
        ["middle", "high"],
    ),
    "plot_stem_leaf": ToolDefinition(
        "plot_stem_leaf",
        "줄기와 잎 그림 schema를 제공합니다.",
        _schema(
            ["dataset_id", "column"],
            {"dataset_id": {"type": "string"}, "column": {"type": "string"}},
        ),
        {},
        plot_stem_leaf,
        ["middle"],
        status="stub",
    ),
    "plot_pie": ToolDefinition(
        "plot_pie",
        "원그래프를 생성합니다.",
        _schema(
            ["dataset_id", "category_col", "value_col"],
            {
                "dataset_id": {"type": "string"},
                "category_col": {"type": "string"},
                "value_col": {"type": "string"},
                "title": {"type": "string"},
            },
        ),
        {},
        plot_pie,
        ["middle"],
        status="stub",
    ),
    "create_frequency_table": ToolDefinition(
        "create_frequency_table",
        "도수분포표를 생성합니다.",
        _schema(
            ["dataset_id", "column"],
            {
                "dataset_id": {"type": "string"},
                "column": {"type": "string"},
                "bins": {"type": "integer", "minimum": 5, "maximum": 20},
            },
        ),
        {},
        create_frequency_table,
        ["middle", "high"],
        status="stub",
    ),
    "create_crosstab": ToolDefinition(
        "create_crosstab",
        "교차표를 생성합니다.",
        _schema(
            ["dataset_id", "row_column", "col_column"],
            {
                "dataset_id": {"type": "string"},
                "row_column": {"type": "string"},
                "col_column": {"type": "string"},
                "normalize": {"type": "boolean"},
            },
        ),
        {},
        create_crosstab,
        ["middle", "high"],
        status="stub",
    ),
    "save_inquiry_step": ToolDefinition(
        "save_inquiry_step",
        "탐구 단계를 저장합니다.",
        _schema(
            ["project_id", "step_type", "payload"],
            {
                "project_id": {"type": "string"},
                "step_type": {"type": "string"},
                "payload": {"type": "object"},
            },
        ),
        {},
        save_inquiry_step,
        ["middle", "high"],
        status="stub",
    ),
    "save_conclusion": ToolDefinition(
        "save_conclusion",
        "결론을 저장합니다.",
        _schema(
            ["project_id", "conclusion_text"],
            {"project_id": {"type": "string"}, "conclusion_text": {"type": "string"}},
        ),
        {},
        save_conclusion,
        ["middle", "high"],
        status="stub",
    ),
    "plot_choropleth": ToolDefinition(
        "plot_choropleth",
        "지역별 수치를 지도 히트맵으로 시각화합니다.",
        _schema(
            ["dataset_id", "region_col", "value_col"],
            {
                "dataset_id": {"type": "string"},
                "region_col": {"type": "string"},
                "value_col": {"type": "string"},
                "map_level": {"type": "string", "enum": ["sido", "sigungu", "emd"]},
                "parent_region": {"type": "string"},
                "color_scale": {"type": "string"},
                "title": {"type": "string"},
                "time_column": {"type": "string"},
                "time_point": {"type": "string"},
                "n_classes": {"type": "integer", "minimum": 3, "maximum": 7},
            },
        ),
        {},
        plot_choropleth,
        ["middle", "high"],
    ),
    "get_inquiry_history": ToolDefinition(
        "get_inquiry_history",
        "탐구 이력을 조회합니다.",
        _schema(["project_id"], {"project_id": {"type": "string"}}),
        {},
        get_inquiry_history,
        ["middle", "high"],
        status="stub",
    ),
}


def get_tool(name: str) -> ToolDefinition | None:
    return TOOLS.get(name)


def list_tools() -> list[ToolDefinition]:
    return list(TOOLS.values())
