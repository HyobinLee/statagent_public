from app.core.errors import AppError
from app.services.dataset_service import DatasetService

_UPDATE_CHUNK_SIZE = 1000


def materialize_column(
    *,
    dataset_id: str,
    owner_user_id: str,
    new_column: str,
    source_column: str,
    row_values: list,
    display_name: str | None = None,
    description: str | None = None,
) -> dict:
    service = DatasetService()
    row_count = len(service.read_dataframe(dataset_id))
    if len(row_values) != row_count:
        raise AppError(
            "MATERIALIZE_ROW_COUNT_MISMATCH",
            "값 개수가 자료의 행 수와 다릅니다.",
            "자료를 새로고침한 뒤 다시 시도해 주세요.",
        )

    create_result = service.add_derived_column(
        dataset_id,
        owner_user_id,
        new_column=new_column,
        formula=f'"x" & {{{source_column}}}',
        display_name=display_name,
        description=description,
    )
    column_name = create_result["derived_column"]["name"]

    result = create_result
    for start in range(0, len(row_values), _UPDATE_CHUNK_SIZE):
        chunk = row_values[start : start + _UPDATE_CHUNK_SIZE]
        updates = [
            {"row_index": start + offset, "column": column_name, "value": value} for offset, value in enumerate(chunk)
        ]
        result = service.update_cells(dataset_id, owner_user_id, updates)
    return {**result, "derived_column": create_result["derived_column"]}
