from uuid import uuid4

from app.core.errors import AppError, success_response
from app.dependencies import require_role
from app.models.user import User
from app.repositories.factory import get_repository
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/admin", tags=["lesson-admin"])


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
        user_id=f"lesson-user-{uuid4().hex[:12]}",
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
    get_repository().delete_user(user_id)
    return success_response({"deleted": True, "user_id": user_id})


@router.get("/classes")
def classes(_user: User = Depends(require_role("admin"))) -> dict:
    from lessons_app.services import student_accounts, tracks

    users = get_repository().list_users()
    teachers_by_id = {user.user_id: user for user in users if user.role == "teacher"}
    class_ids = sorted({user.class_id for user in users if user.class_id})
    class_records = {class_id: student_accounts.get_class_record(class_id) or {} for class_id in class_ids}
    return success_response(
        [
            {
                "class_id": class_id,
                "name": class_id,
                "track": tracks.normalize_track(class_records[class_id].get("track")),
                "scenario": tracks.normalize_scenario(class_records[class_id].get("scenario")),
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
