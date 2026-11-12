from app.core.errors import AppError
from app.core.time import now_utc
from app.models.project import Project
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService
from app.services.workflow_service import WorkflowService

from lessons_app.services.lesson_defs import get_lesson_def_for_track

INQUIRY_LESSON_ID = "lesson5"

CONCLUSION_MAX_LENGTH = 1600

UPLOAD_DEFAULT_SOURCE = "학생 업로드 CSV"
UPLOAD_DEFAULT_TIME_RANGE = "업로드 자료"


def career_key(user_id: str) -> str:
    return f"career:{user_id}"


def presentation_key(project_id: str) -> str:
    return f"presentation:{project_id}"


def saved_career(user_id: str) -> dict | None:
    setting = get_repository().get_setting(career_key(user_id))
    return (setting or {}).get("value") or None


def apply_question(project: Project, question: str) -> Project:
    cleaned = (question or "").strip()
    if not cleaned or project.custom_topic_question == cleaned:
        return project
    project.custom_topic_title = cleaned[:80]
    project.custom_topic_question = cleaned
    return get_repository().update_project(project)


def sync_career_question(user: User, project: Project) -> Project:
    career = saved_career(user.user_id)
    if not career or not career.get("question"):
        return project
    return apply_question(project, career["question"])


def link_dataset(user: User, project_id: str, dataset_id: str) -> Project:
    workflow = WorkflowService()
    project = workflow.get_project(project_id, user)
    if project.dataset_id == dataset_id:
        return project
    repo = get_repository()
    previous_status = project.status
    if previous_status == "dataset_chosen":
        project.status = "topic_selected"
        repo.update_project(project)
    try:
        return workflow.select_dataset(project_id, dataset_id, user)
    except AppError:
        if previous_status == "dataset_chosen":
            restored = repo.get_project(project_id)
            if restored:
                restored.status = previous_status
                repo.update_project(restored)
        raise


def get_presentation(project_id: str) -> dict:
    setting = get_repository().get_setting(presentation_key(project_id))
    value = (setting or {}).get("value") or {}
    return {
        "selected": value.get("selected"),
        "conclusion": value.get("conclusion", ""),
        "limitations": value.get("limitations", ""),
        "updated_at": value.get("updated_at"),
    }


def save_presentation(
    user: User,
    project_id: str,
    selected: list[str] | None,
    conclusion: str,
    limitations: str,
) -> dict:
    workflow = WorkflowService()
    workflow.get_project(project_id, user)
    if selected is not None:
        known = {analysis.analysis_result_id for analysis in workflow.analyses(project_id, user)}
        unknown = [analysis_id for analysis_id in selected if analysis_id not in known]
        if unknown:
            raise AppError(
                "PRESENTATION_ANALYSIS_NOT_FOUND",
                "이 탐구에 없는 분석 결과가 발표 목록에 들어 있습니다.",
                "화면을 새로고침한 뒤 발표에 넣을 결과를 다시 골라 주세요.",
                400,
            )
        selected = list(dict.fromkeys(selected))
    value = {
        "selected": selected,
        "conclusion": (conclusion or "").strip()[:CONCLUSION_MAX_LENGTH],
        "limitations": (limitations or "").strip()[:CONCLUSION_MAX_LENGTH],
        "updated_at": now_utc().isoformat(),
    }
    get_repository().upsert_setting(presentation_key(project_id), value)
    return get_presentation(project_id)


def _dataset_summary(dataset_id: str | None) -> dict | None:
    if not dataset_id:
        return None
    service = DatasetService()
    try:
        dataset = service.get_dataset(dataset_id)
    except AppError:
        return None
    try:
        row_count = int(len(service.read_dataframe(dataset_id)))
    except AppError:
        row_count = None
    source = "" if dataset.source == UPLOAD_DEFAULT_SOURCE else dataset.source
    return {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "source": source,
        "source_recorded": bool(source.strip()),
        "source_note": dataset.source_note,
        "time_range": "" if dataset.time_range == UPLOAD_DEFAULT_TIME_RANGE else dataset.time_range,
        "row_count": row_count,
        "columns": [
            {"name": column.name, "display_name": column.display_name, "unit": column.unit}
            for column in dataset.columns
        ],
    }


def inquiry_summary(user: User, project_id: str) -> dict:
    from lessons_app.services import tracks

    workflow = WorkflowService()
    project = workflow.get_project(project_id, user)
    analyses = workflow.analyses(project_id, user)
    career = saved_career(project.owner_user_id)
    question = project.custom_topic_question or ""
    effective_track, _ = tracks.resolve(user)
    default_sentence = get_lesson_def_for_track(INQUIRY_LESSON_ID, effective_track)["topic_sentence"]
    return {
        "project_id": project.project_id,
        "question": question,
        "question_confirmed": bool(question) and question != default_sentence,
        "career": {"field_name": career.get("field_name"), "question": career.get("question")} if career else None,
        "dataset": _dataset_summary(project.dataset_id),
        "analysis_count": len(analyses),
        "interpreted_count": sum(1 for analysis in analyses if (analysis.interpretation or "").strip()),
        "presentation": get_presentation(project_id),
    }
