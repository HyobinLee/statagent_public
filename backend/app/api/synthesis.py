from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from app.services.synthesis_service import SynthesisService

router = APIRouter(tags=["synthesis"])


class JoinSpec(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=5)
    key_column_mappings: dict[str, str] = Field(default_factory=dict)
    join_type: str = Field(default="inner", pattern="^(inner|outer)$")
    time_column_mappings: dict[str, str] = Field(default_factory=dict)
    selected_time_points: list[str] = Field(default_factory=list)


class RunSynthesisRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    tool_args: dict = Field(default_factory=dict)
    join_spec: JoinSpec


@router.post("/api/projects/{project_id}/synthesis")
def run_synthesis(
    project_id: str,
    payload: RunSynthesisRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    result = SynthesisService().run_synthesis(
        project_id,
        payload.tool_name,
        payload.tool_args,
        payload.join_spec.model_dump(),
        user,
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/api/projects/{project_id}/synthesis")
def list_synthesis(
    project_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    results = SynthesisService().list_for_project(project_id, user)
    payload = [result.model_dump(mode="json") for result in results]
    return success_response(payload, {"count": len(payload)})


@router.get("/api/synthesis/{synthesis_result_id}/observations")
def synthesis_observations(
    synthesis_result_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    result = SynthesisService().observations(synthesis_result_id, user)
    return success_response(result)
