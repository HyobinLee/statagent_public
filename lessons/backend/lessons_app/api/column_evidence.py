from app.core.errors import AppError, success_response
from app.dependencies import require_role
from app.models.user import User
from app.services.dataset_service import DatasetService
from app.services.workflow_service import WorkflowService
from fastapi import APIRouter, Depends

from lessons_app.services import tracks
from lessons_app.services.connector_provisioning import registered_dataset_id

router = APIRouter(prefix="/api/lessons/projects", tags=["lesson-evidence"])

MAX_EXAMPLES = 5


@router.get("/{project_id}/column-meaning-evidence")
def column_meaning_evidence(
    project_id: str,
    connector: str = "",
    lesson_id: str = "",
    track: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    workflow = WorkflowService()
    project = workflow.get_project(project_id, user)

    dataset_id = project.dataset_id
    if connector:
        effective_track, scenario = tracks.resolve(user, track)
        dataset_id = registered_dataset_id(user.user_id, effective_track, scenario, lesson_id, connector)
        if not dataset_id:
            raise AppError(
                "CONNECTOR_DATASET_NOT_READY",
                "아직 이 자료를 불러오지 않았습니다.",
                "앞 카드에서 자료를 먼저 불러온 뒤 다시 열어 주세요.",
                400,
            )
    if not dataset_id:
        raise AppError(
            "DATASET_NOT_SELECTED",
            "자료가 선택되지 않았습니다.",
            "차시를 다시 불러와 주세요.",
            400,
        )

    datasets = DatasetService()
    dataset = datasets.get_dataset(dataset_id)

    dataframe = None
    columns_payload = []
    for column in dataset.columns:
        examples = [label.value for label in column.value_labels[:MAX_EXAMPLES]]
        source = "value_labels"
        if not examples:
            source = "rows"
            if dataframe is None:
                dataframe = datasets.read_dataframe(dataset.dataset_id)
            if column.name in dataframe.columns:
                seen: list[str] = []
                for raw_value in dataframe[column.name].tolist():
                    if raw_value is None:
                        continue
                    text = str(raw_value)
                    if text not in seen:
                        seen.append(text)
                    if len(seen) >= MAX_EXAMPLES:
                        break
                examples = seen
        columns_payload.append(
            {
                "name": column.name,
                "display_name": column.display_name,
                "dtype": column.dtype,
                "unit": column.unit,
                "value_examples": examples,
                "examples_source": source,
            }
        )
    return success_response(columns_payload)
