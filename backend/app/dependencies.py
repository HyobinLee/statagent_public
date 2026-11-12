from collections.abc import Callable

from fastapi import Depends, Header

from app.config import get_settings
from app.core.errors import AppError
from app.core.firebase_auth import get_firebase_user
from app.core.roles import ALLOWED_ROLES
from app.models.user import User
from app.repositories.factory import get_repository

DEFAULT_EMAIL_BY_ROLE = {
    "admin": "admin@example.com",
    "teacher": "teacher@example.com",
    "student": "student1@example.com",
}


def _authenticated_user(
    authorization: str | None,
    x_dev_user: str | None,
    x_dev_role: str | None,
) -> User:
    if not get_settings().dev_auth_enabled:
        return get_firebase_user(authorization)

    role = x_dev_role or "teacher"
    if role not in ALLOWED_ROLES:
        raise AppError(
            "INVALID_ROLE",
            "허용되지 않은 로컬 개발 역할입니다.",
            "admin, teacher, student 중 하나를 사용해 주세요.",
            403,
        )
    email = x_dev_user or DEFAULT_EMAIL_BY_ROLE[role]
    repo = get_repository()
    user = repo.get_user_by_email(email)
    if not user:
        raise AppError(
            "DEV_USER_NOT_FOUND",
            "로컬 개발 사용자를 찾을 수 없습니다.",
            "README의 로컬 개발 사용자 이메일을 확인해 주세요.",
            403,
        )
    if user.role != role:
        raise AppError(
            "ROLE_USER_MISMATCH",
            "사용자와 역할이 일치하지 않습니다.",
            "관리자 배정 역할 또는 로컬 개발 헤더를 확인해 주세요.",
            403,
        )
    return user


def _admin_act_as(actor: User, target_user_id: str) -> User:
    if actor.role != "admin":
        raise AppError(
            "FORBIDDEN_ADMIN_ACT_AS",
            "관리자만 다른 사용자의 화면에 접근할 수 있습니다.",
            "관리자 계정으로 로그인한 뒤 다시 시도해 주세요.",
            403,
        )
    target = get_repository().get_user(target_user_id)
    if not target:
        raise AppError(
            "USER_NOT_FOUND",
            "접근할 사용자를 찾을 수 없습니다.",
            "관리자 사용자 목록을 새로고침해 주세요.",
            404,
        )
    return target


def _student_preview(actor: User) -> User:
    if actor.role not in {"teacher", "admin"}:
        raise AppError(
            "FORBIDDEN_STUDENT_PREVIEW",
            "교사 또는 관리자만 학생 화면 미리보기를 사용할 수 있습니다.",
            "교사 계정으로 로그인한 뒤 다시 시도해 주세요.",
            403,
        )
    repo = get_repository()
    preview_id = f"preview_{actor.user_id}"
    existing = repo.get_user(preview_id)
    preview = existing or User(
        user_id=preview_id,
        email=f"preview+{actor.user_id}@stat-agent.local",
        role="student",
        display_name=f"{actor.display_name} 학생 화면 미리보기",
    )
    preview.role = "student"
    preview.display_name = f"{actor.display_name} 학생 화면 미리보기"
    preview.teacher_id = actor.user_id if actor.role == "teacher" else preview.teacher_id
    return repo.upsert_user(preview)


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
    x_dev_role: str | None = Header(default=None, alias="X-Dev-Role"),
    x_admin_act_as_user: str | None = Header(default=None, alias="X-Admin-Act-As-User"),
    x_student_preview: str | None = Header(default=None, alias="X-Student-Preview"),
) -> User:
    actor = _authenticated_user(authorization, x_dev_user, x_dev_role)
    if x_admin_act_as_user:
        return _admin_act_as(actor, x_admin_act_as_user)
    if str(x_student_preview or "").strip().lower() in {"1", "true", "yes", "on"}:
        return _student_preview(actor)
    return actor


def require_role(role: str) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise AppError(
                "FORBIDDEN",
                "이 기능을 사용할 권한이 없습니다.",
                "로그인 계정에 배정된 역할을 확인해 주세요.",
                403,
            )
        return user

    checker.__name__ = f"require_role_{role}"
    return checker


def require_any_role(roles: list[str]) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(
                "FORBIDDEN",
                "이 기능을 사용할 권한이 없습니다.",
                "로그인 계정에 배정된 역할을 확인해 주세요.",
                403,
            )
        return user

    checker.__name__ = "require_any_role_" + "_".join(roles)
    return checker
