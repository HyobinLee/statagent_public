from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/projects", tags=["projects"])


SchoolLevelField = Literal["middle", "high", "middle_high"]


class CreateProjectRequest(BaseModel):
    school_level: SchoolLevelField | None = None


class SelectTopicRequest(BaseModel):
    topic_id: str


class SelectDatasetRequest(BaseModel):
    dataset_id: str


class UseSharedDatasetRequest(BaseModel):
    dataset_id: str
    source_project_id: str | None = None


class RunAnalysisRequest(BaseModel):
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    row_indices: list[int] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)


class ColumnMeaning(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    unit: str | None = None


class ApplyColumnMeaningsRequest(BaseModel):
    meanings: list[ColumnMeaning] = Field(default_factory=list)


class InterpretationRequest(BaseModel):
    prompt_text: str = ""


class InterpretationFeedbackRequest(BaseModel):
    interpretation_text: str = Field(..., min_length=1, max_length=1600)


class SaveInterpretationRequest(BaseModel):
    interpretation_text: str = Field(default="", max_length=1600)


class CoachRequest(BaseModel):
    prompt_text: str = ""


class QuestionAdviceRequest(BaseModel):
    student_input: str = Field(..., min_length=1, max_length=4000)
    advice_mode: Literal["direct_survey", "big_data"] = "direct_survey"
    school_level: SchoolLevelField | None = None


class CustomTopicRequest(BaseModel):
    decided_topic: str = Field(..., min_length=1, max_length=300)
    advisor_input: str = Field(default="", max_length=4000)
    school_level: SchoolLevelField | None = None


@router.post("")
def create_project(
    payload: CreateProjectRequest | None = None,
    user: User = Depends(require_role("student")),
) -> dict:
    project = WorkflowService().create_project(user, school_level=payload.school_level if payload else None)
    return success_response(project.model_dump(mode="json"))


@router.get("")
def list_projects(user: User = Depends(require_any_role(["student", "teacher", "admin"]))) -> dict:
    projects = [project.model_dump(mode="json") for project in WorkflowService().list_projects(user)]
    return success_response(projects, {"count": len(projects)})


@router.post("/question-advice")
def question_advice(
    payload: QuestionAdviceRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    advice = WorkflowService().question_advice(
        user,
        payload.student_input,
        advice_mode=payload.advice_mode,
        school_level=payload.school_level,
    )
    return success_response(advice)


@router.post("/custom-topic")
def create_custom_topic_project(
    payload: CustomTopicRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    project = WorkflowService().create_custom_topic_project(
        user,
        payload.decided_topic,
        advisor_input=payload.advisor_input,
        school_level=payload.school_level,
    )
    return success_response(project.model_dump(mode="json"))


@router.get("/shared-artifacts")
def shared_artifacts(user: User = Depends(require_role("student"))) -> dict:
    artifacts = WorkflowService().shared_artifacts(user)
    return success_response(artifacts, {"count": len(artifacts)})


@router.get("/{project_id}")
def get_project(
    project_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    project = WorkflowService().get_project(project_id, user)
    return success_response(project.model_dump(mode="json"))


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    user: User = Depends(require_any_role(["student", "admin"])),
) -> dict:
    WorkflowService().delete_project(project_id, user)
    return success_response({"deleted": True, "project_id": project_id})


@router.post("/{project_id}/select-topic")
def select_topic(
    project_id: str,
    payload: SelectTopicRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    project = WorkflowService().select_topic(project_id, payload.topic_id, user)
    return success_response(project.model_dump(mode="json"))


@router.post("/{project_id}/select-dataset")
def select_dataset(
    project_id: str,
    payload: SelectDatasetRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    project = WorkflowService().select_dataset(project_id, payload.dataset_id, user)
    return success_response(project.model_dump(mode="json"))


@router.post("/{project_id}/use-shared-dataset")
def use_shared_dataset(
    project_id: str,
    payload: UseSharedDatasetRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    project = WorkflowService().use_shared_dataset(
        project_id,
        payload.dataset_id,
        user,
        source_project_id=payload.source_project_id,
    )
    return success_response(project.model_dump(mode="json"))


@router.get("/{project_id}/analysis-options")
def analysis_options(project_id: str, user: User = Depends(require_role("student"))) -> dict:
    options = WorkflowService().analysis_options(project_id, user)
    return success_response(options, {"count": len(options)})


@router.get("/{project_id}/analyses")
def project_analyses(
    project_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    analyses = [analysis.model_dump(mode="json") for analysis in WorkflowService().analyses(project_id, user)]
    return success_response(analyses, {"count": len(analyses)})


@router.get("/{project_id}/derived-variable-suggestions")
def derived_variable_suggestions(project_id: str, user: User = Depends(require_role("student"))) -> dict:
    suggestions = WorkflowService().derived_variable_suggestions(project_id, user)
    return success_response(suggestions, {"count": len(suggestions)})


@router.get("/{project_id}/column-meaning-suggestions")
def column_meaning_suggestions(project_id: str, user: User = Depends(require_role("student"))) -> dict:
    meanings = WorkflowService().column_meaning_suggestions(project_id, user)
    return success_response(meanings, {"count": len(meanings)})


@router.post("/{project_id}/column-meanings")
def apply_column_meanings(
    project_id: str,
    payload: ApplyColumnMeaningsRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    schema = WorkflowService().apply_column_meanings(project_id, user, [item.model_dump() for item in payload.meanings])
    return success_response(schema)


@router.post("/{project_id}/run-analysis")
def run_analysis(
    project_id: str,
    payload: RunAnalysisRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    analysis = WorkflowService().run_analysis(
        project_id,
        payload.tool_name,
        payload.tool_args,
        user,
        row_indices=payload.row_indices,
        filters=payload.filters,
    )
    return success_response(analysis.model_dump(mode="json"))


@router.post("/{project_id}/interpretation-hints")
def interpretation_hints(
    project_id: str,
    payload: InterpretationRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    hints = WorkflowService().interpretation_hints(project_id, user, payload.prompt_text)
    return success_response(hints)


@router.post("/{project_id}/analyses/{analysis_result_id}/interpretation-feedback")
def interpretation_feedback(
    project_id: str,
    analysis_result_id: str,
    payload: InterpretationFeedbackRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    feedback = WorkflowService().interpretation_feedback(
        project_id, analysis_result_id, user, payload.interpretation_text
    )
    return success_response(feedback)


@router.put("/{project_id}/analyses/{analysis_result_id}/interpretation")
def save_interpretation(
    project_id: str,
    analysis_result_id: str,
    payload: SaveInterpretationRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    analysis = WorkflowService().save_interpretation(project_id, analysis_result_id, user, payload.interpretation_text)
    return success_response(analysis.model_dump(mode="json"))


@router.post("/{project_id}/ai-coach")
def ai_coach(
    project_id: str,
    payload: CoachRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    coach = WorkflowService().ai_coach(project_id, user, payload.prompt_text)
    return success_response(coach)


@router.post("/{project_id}/stop")
def stop_project(project_id: str, user: User = Depends(require_role("student"))) -> dict:
    project = WorkflowService().stop(project_id, user)
    return success_response(project.model_dump(mode="json"))
