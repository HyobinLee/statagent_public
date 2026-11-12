from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.errors import AppError, success_response
from app.dependencies import require_role
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.blocking_service import BlockingService
from app.services.deployment_readiness import build_deployment_readiness
from app.services.stat_api_service import StatApiService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class AdminUserRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    role: str = Field(..., pattern="^(admin|teacher|student)$")
    display_name: str = Field(..., min_length=1, max_length=80)
    class_id: str | None = Field(default=None, max_length=80)
    teacher_id: str | None = Field(default=None, max_length=120)
    group_id: str | None = Field(default=None, max_length=80)


class AdminUserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|teacher|student)$")
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    class_id: str | None = Field(default=None, max_length=80)
    teacher_id: str | None = Field(default=None, max_length=120)
    group_id: str | None = Field(default=None, max_length=80)


class BlockRequest(BaseModel):
    reason: str = Field(default="관리자 수동 일시정지", max_length=200)


class AdminHierarchyRouteRequest(BaseModel):
    class_id: str = Field(..., min_length=1, max_length=80)
    teacher_id: str = Field(..., min_length=1, max_length=120)
    student_ids: list[str] = Field(default_factory=list)


@router.get("/users")
def users(_user: User = Depends(require_role("admin"))) -> dict:
    all_users = get_repository().list_users()
    return success_response([user.model_dump(mode="json") for user in all_users], {"count": len(all_users)})


@router.post("/users")
def upsert_user(payload: AdminUserRequest, _user: User = Depends(require_role("admin"))) -> dict:
    repo = get_repository()
    normalized_email = _normalize_email(payload.email)
    existing = repo.get_user_by_email(normalized_email)
    user = existing or User(
        user_id=f"user_{uuid4().hex[:12]}",
        email=normalized_email,
        role=payload.role,
        display_name=payload.display_name,
    )
    user.email = normalized_email
    user.role = payload.role
    user.display_name = payload.display_name
    user.class_id = payload.class_id
    user.teacher_id = payload.teacher_id
    user.group_id = payload.group_id
    saved = repo.upsert_user(user)
    return success_response(saved.model_dump(mode="json"))


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    _user: User = Depends(require_role("admin")),
) -> dict:
    repo = get_repository()
    user = repo.get_user(user_id)
    if not user:
        raise AppError("USER_NOT_FOUND", "사용자를 찾을 수 없습니다.", "사용자 목록을 새로고침해 주세요.", 404)
    for field in ("role", "display_name", "class_id", "teacher_id", "group_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    saved = repo.upsert_user(user)
    return success_response(saved.model_dump(mode="json"))


@router.delete("/users/{user_id}")
def delete_user(user_id: str, _user: User = Depends(require_role("admin"))) -> dict:
    repo = get_repository()
    for project in list(repo.list_projects()):
        if project.owner_user_id == user_id:
            WorkflowService().delete_project(project.project_id, _user)
    repo.delete_user(user_id)
    return success_response({"deleted": True, "user_id": user_id})


@router.post("/users/{user_id}/block")
def block_user(
    user_id: str,
    payload: BlockRequest,
    _user: User = Depends(require_role("admin")),
) -> dict:
    BlockingService().block_user(user_id, payload.reason, force_permanent=True)
    user = get_repository().get_user(user_id)
    return success_response(user.model_dump(mode="json") if user else {"user_id": user_id})


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: str, _user: User = Depends(require_role("admin"))) -> dict:
    BlockingService().unblock_user(user_id)
    user = get_repository().get_user(user_id)
    return success_response(user.model_dump(mode="json") if user else {"user_id": user_id})


@router.get("/projects")
def projects(_user: User = Depends(require_role("admin"))) -> dict:
    repo = get_repository()
    users_by_id = {user.user_id: user for user in repo.list_users()}
    reports_by_project = {report.project_id: report for report in repo.list_reports()}
    rows = []
    for project in WorkflowService().list_projects(_user):
        owner = users_by_id.get(project.owner_user_id)
        rows.append(
            {
                **project.model_dump(mode="json"),
                "owner_email": owner.email if owner else project.owner_user_id,
                "owner_name": owner.display_name if owner else project.owner_user_id,
                "report_id": reports_by_project.get(project.project_id).report_id
                if reports_by_project.get(project.project_id)
                else None,
            }
        )
    return success_response(rows, {"count": len(rows)})


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, user: User = Depends(require_role("admin"))) -> dict:
    WorkflowService().delete_project(project_id, user)
    return success_response({"deleted": True, "project_id": project_id})


@router.get("/usage")
def usage(_user: User = Depends(require_role("admin"))) -> dict:
    repo = get_repository()
    users_by_id = {user.user_id: user for user in repo.list_users()}
    summary: dict[str, dict] = {}
    for event in repo.list_usage_events():
        row = summary.setdefault(
            event.user_id,
            {
                "user_id": event.user_id,
                "email": users_by_id.get(event.user_id).email if users_by_id.get(event.user_id) else event.user_id,
                "display_name": users_by_id.get(event.user_id).display_name
                if users_by_id.get(event.user_id)
                else event.user_id,
                "ai_call_count": 0,
                "tool_call_count": 0,
                "workflow_bypass_count": 0,
                "blocked_count": 0,
                "last_event_at": None,
            },
        )
        if event.event_type == "ai_call":
            row["ai_call_count"] += 1
        elif event.event_type == "tool_call":
            row["tool_call_count"] += 1
        elif event.event_type == "workflow_bypass":
            row["workflow_bypass_count"] += 1
        elif event.event_type == "blocked":
            row["blocked_count"] += 1
        row["last_event_at"] = event.created_at
    return success_response(list(summary.values()), {"count": len(summary)})


@router.get("/classes")
def classes(_user: User = Depends(require_role("admin"))) -> dict:
    users = get_repository().list_users()
    teachers_by_id = {user.user_id: user for user in users if user.role == "teacher"}
    class_ids = sorted({user.class_id for user in users if user.class_id})
    return success_response(
        [
            {
                "class_id": class_id,
                "name": class_id,
                "member_count": len([user for user in users if user.class_id == class_id]),
                "teacher_ids": sorted(
                    {
                        user.teacher_id
                        for user in users
                        if user.role == "student" and user.class_id == class_id and user.teacher_id
                    }
                ),
                "teacher_names": [
                    teachers_by_id[teacher_id].display_name
                    for teacher_id in sorted(
                        {
                            user.teacher_id
                            for user in users
                            if (
                                user.role == "student"
                                and user.class_id == class_id
                                and user.teacher_id in teachers_by_id
                            )
                        }
                    )
                ],
            }
            for class_id in class_ids
        ]
    )


@router.post("/hierarchy-route")
def route_students_to_teacher(
    payload: AdminHierarchyRouteRequest,
    _user: User = Depends(require_role("admin")),
) -> dict:
    repo = get_repository()
    teacher = repo.get_user(payload.teacher_id)
    if not teacher or teacher.role != "teacher":
        raise AppError(
            "TEACHER_NOT_FOUND",
            "담당 교사를 찾을 수 없습니다.",
            "교사 계정을 먼저 만들거나 교사 목록에서 다시 선택해 주세요.",
            404,
        )
    updated = []
    for student_id in payload.student_ids:
        student = repo.get_user(student_id)
        if student and student.role == "student":
            student.class_id = payload.class_id
            student.teacher_id = teacher.user_id
            updated.append(repo.upsert_user(student).model_dump(mode="json"))
    return success_response(
        {
            "class_id": payload.class_id,
            "teacher_id": teacher.user_id,
            "teacher_name": teacher.display_name,
            "students": updated,
        }
    )


@router.get("/status")
def status(_user: User = Depends(require_role("admin"))) -> dict:
    settings = get_settings()
    readiness = build_deployment_readiness(settings)
    stat_api_key_status = StatApiService().stat_api_key_status()
    firebase_configured = all(
        [
            settings.firebase_web_api_key,
            settings.firebase_auth_domain,
            settings.firebase_project_id or settings.google_cloud_project,
            settings.firebase_app_id,
        ]
    )
    return success_response(
        {
            "app_env": settings.app_env,
            "app_region": settings.app_region,
            "google_cloud_project": settings.google_cloud_project,
            "firebase_web_configured": firebase_configured,
            "firebase_whitelist_secret_configured": bool(settings.firebase_whitelist_secret),
            "enable_gemini": settings.enable_gemini,
            "enable_secret_manager": settings.enable_secret_manager,
            "enable_firestore": settings.enable_firestore,
            "firestore_database": settings.firestore_database,
            "firestore_collection_prefix": settings.firestore_collection_prefix,
            "enable_cloud_storage": settings.enable_cloud_storage,
            "gcs_chart_bucket": settings.gcs_chart_bucket,
            "gcs_dataset_bucket": settings.gcs_dataset_bucket,
            "gcs_dataset_prefix": settings.gcs_dataset_prefix,
            "dev_auth_enabled": settings.dev_auth_enabled,
            "auto_provision_firebase_users": settings.auto_provision_firebase_users,
            "firebase_default_role": settings.firebase_default_role,
            "min_student_age": settings.min_student_age,
            "privacy_policy_url": settings.privacy_policy_url,
            "deployment_readiness": readiness,
            "stat_api_key_status": stat_api_key_status,
            "account_storage_policy": (
                "사용자 API는 이메일과 역할 메타데이터만 저장하며 비밀번호나 토큰은 저장하지 않습니다. "
                "배포 환경의 실제 인증은 Firebase Auth와 Firestore 보안 규칙에 위임합니다."
            ),
        }
    )


@router.get("/deployment-readiness")
def deployment_readiness(_user: User = Depends(require_role("admin"))) -> dict:
    return success_response(build_deployment_readiness())
