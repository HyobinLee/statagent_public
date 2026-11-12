import csv

from app.models.project import Project
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService
from app.services.workflow_service import WorkflowService

from lessons_app.config import LESSON_CSV_DIR
from lessons_app.services import tracks
from lessons_app.services.progress import state_key


def _state_key(user_id: str, lesson_id: str, track: str, scenario: str) -> str:
    return state_key(user_id, tracks.normalize_track(track), tracks.normalize_scenario(scenario), lesson_id)


def ensure_lesson_project(user: User, lesson_id: str, lesson_def: dict, track: str = "", scenario: str = "") -> Project:
    repo = get_repository()
    key = _state_key(user.user_id, lesson_id, track, scenario)

    existing = repo.get_setting(key)
    if existing:
        value = existing.get("value") or {}
        project_id = value.get("project_id")
        if project_id:
            project = repo.get_project(project_id)
            if project and (not lesson_def.get("dataset_file") or project.dataset_id):
                if _dataset_matches(value, project, lesson_def):
                    return project

    workflow = WorkflowService()
    project = workflow.create_custom_topic_project(
        user,
        decided_topic=lesson_def["topic_sentence"],
    )

    dataset_id = None
    csv_filename = lesson_def.get("dataset_file")
    if csv_filename:
        content = (LESSON_CSV_DIR / csv_filename).read_bytes()
        dataset_source = lesson_def.get("dataset_source", "차시 예시 자료")
        upload = DatasetService().create_uploaded_dataset(
            filename=csv_filename,
            content=content,
            topic_id=project.topic_id,
            owner_user_id=user.user_id,
            dataset_name=lesson_def.get("title", csv_filename),
            source=dataset_source,
            source_note=f"{lesson_id} 탑재 자료 · {dataset_source}",
        )
        dataset_id = upload["dataset"]["dataset_id"]
        project = workflow.select_dataset(project.project_id, dataset_id, user)

    repo.upsert_setting(
        key,
        {
            "project_id": project.project_id,
            "dataset_id": dataset_id,
            "lesson_id": lesson_id,
            "dataset_file": csv_filename,
        },
    )
    return project


def _dataset_matches(value: dict, project: Project, lesson_def: dict) -> bool:
    csv_filename = lesson_def.get("dataset_file")
    if not csv_filename:
        return True
    if "dataset_file" in value:
        return value["dataset_file"] == csv_filename
    try:
        dataset = DatasetService().get_dataset(project.dataset_id)
    except Exception:
        return False
    if dataset.source != lesson_def.get("dataset_source", "차시 예시 자료"):
        return False
    expected = _csv_columns(csv_filename)
    return expected <= {column.name for column in dataset.columns}


def _csv_columns(csv_filename: str) -> set[str]:
    with open(LESSON_CSV_DIR / csv_filename, encoding="utf-8-sig", newline="") as handle:
        return {name.strip() for name in next(csv.reader(handle), [])}


def record_lesson_visit(user: User, lesson_id: str, project: Project, track: str = "", scenario: str = "") -> None:
    repo = get_repository()
    key = _state_key(user.user_id, lesson_id, track, scenario)
    repo.upsert_setting(
        key,
        {"project_id": project.project_id, "dataset_id": project.dataset_id, "lesson_id": lesson_id},
    )
