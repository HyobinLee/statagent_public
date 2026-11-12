from collections.abc import Callable
from typing import Any

import pandas as pd
from app.core.errors import AppError
from app.models.project import Project
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService
from app.services.workflow_service import WorkflowService

from lessons_app.config import LESSON_CSV_DIR
from lessons_app.services import progress, tracks


def _state_key(user_id: str, track: str, scenario: str, lesson_id: str, connector_key: str) -> str:
    return progress.connector_key(
        user_id, tracks.normalize_track(track), tracks.normalize_scenario(scenario), lesson_id, connector_key
    )


def registered_dataset_id(user_id: str, track: str, scenario: str, lesson_id: str, connector_key: str) -> str | None:
    setting = get_repository().get_setting(_state_key(user_id, track, scenario, lesson_id, connector_key))
    if not setting:
        return None
    return (setting.get("value") or {}).get("dataset_id")


def provision_connector_dataset(
    *,
    user: User,
    project: Project,
    track: str,
    scenario: str,
    lesson_id: str,
    connector_key: str,
    fetch_live: Callable[[], dict[str, Any]],
    fallback_csv: str,
    dataset_name: str,
    live_source_label: str,
    fallback_source_label: str,
    fallback_dataset_name: str | None = None,
    fallback_source_note: str | None = None,
    select_into_project: bool = False,
) -> dict:
    repo = get_repository()
    key = _state_key(user.user_id, track, scenario, lesson_id, connector_key)

    existing = repo.get_setting(key)
    if existing:
        value = existing.get("value") or {}
        dataset_id = value.get("dataset_id")
        if dataset_id and _dataset_still_exists(dataset_id):
            return value

    request_url = None
    source_reason = None
    effective_dataset_name = dataset_name
    source_note = None
    try:
        live_result = fetch_live()
        rows = live_result.get("rows") or []
        if not rows:
            raise AppError(
                "CONNECTOR_EMPTY_RESULT",
                "불러온 자료에 행이 없습니다.",
                "탑재된 대체 자료로 진행해 주세요.",
                404,
            )
        df = pd.DataFrame(rows)
        request_url = live_result.get("request_url")
        source = live_source_label
    except AppError as exc:
        fallback_path = LESSON_CSV_DIR / fallback_csv
        if not fallback_path.exists():
            raise AppError(
                "CONNECTOR_NO_DATA_SOURCE",
                "실시간 호출과 탑재 대체 자료를 모두 사용할 수 없습니다.",
                "교사 또는 관리자에게 문의해 주세요.",
                503,
                {"live_error": exc.error_message_ko},
            ) from exc
        df = pd.read_csv(fallback_path)
        source = fallback_source_label
        source_reason = exc.error_message_ko
        effective_dataset_name = fallback_dataset_name or dataset_name
        source_note = fallback_source_note

    content = df.to_csv(index=False).encode("utf-8-sig")
    upload = DatasetService().create_uploaded_dataset(
        filename=f"{connector_key}.csv",
        content=content,
        topic_id=project.topic_id,
        owner_user_id=user.user_id,
        dataset_name=effective_dataset_name,
        source=source,
        source_note=source_note or source_reason or f"{live_source_label} 실시간 호출",
    )
    dataset_id = upload["dataset"]["dataset_id"]

    if select_into_project and project.dataset_id != dataset_id:
        if project.status in {"topic_selected", "analysis_done"}:
            WorkflowService().select_dataset(project.project_id, dataset_id, user)

    value = {
        "dataset_id": dataset_id,
        "source": source,
        "source_reason": source_reason,
        "request_url": request_url,
        "row_count": int(len(df)),
    }
    repo.upsert_setting(key, value)
    return value


def _dataset_still_exists(dataset_id: str) -> bool:
    try:
        DatasetService().get_dataset(dataset_id)
        return True
    except AppError:
        return False
