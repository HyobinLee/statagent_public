import pandas as pd

from app.core.errors import AppError
from app.services.dataset_service import DatasetService
from app.tools.schemas import start_timer, tool_failure, tool_success


def create_frequency_table(dataset_id: str, column: str, bins: int | None = None) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_columns(dataset_id, [column])
        df = service.read_dataframe(dataset_id)
        series = df[column].dropna()
        if bins is not None:
            if bins < 5 or bins > 20:
                raise AppError(
                    "INVALID_BINS",
                    "도수분포표 구간 수는 5개 이상 20개 이하만 가능합니다.",
                    "bins 값을 5에서 20 사이로 조정해 주세요.",
                )
            counts = pd.cut(pd.to_numeric(series, errors="coerce").dropna(), bins=bins).value_counts().sort_index()
            rows = [{"range": str(index), "frequency": int(value)} for index, value in counts.items()]
        else:
            counts = series.value_counts()
            rows = [{"value": str(index), "frequency": int(value)} for index, value in counts.items()]
        return tool_success(
            "create_frequency_table",
            dataset_id,
            {"rows": rows},
            "도수분포표는 값이 얼마나 자주 나타나는지 정리합니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("create_frequency_table", dataset_id, exc, start)


def create_crosstab(dataset_id: str, row_column: str, col_column: str, normalize: bool = False) -> dict:
    start = start_timer()
    try:
        service = DatasetService()
        service.require_columns(dataset_id, [row_column, col_column])
        df = service.read_dataframe(dataset_id)
        table = pd.crosstab(df[row_column], df[col_column], normalize="all" if normalize else False)
        return tool_success(
            "create_crosstab",
            dataset_id,
            {"rows": table.reset_index().to_dict(orient="records")},
            "교차표는 두 범주형 변수의 조합별 빈도를 보여줍니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("create_crosstab", dataset_id, exc, start)
