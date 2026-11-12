import base64
import binascii
import hashlib
import json
import time

import httpx
from app.core.errors import AppError
from app.models.user import User
from app.repositories.factory import get_repository
from fastapi import Header

from lessons_app.config import main_backend_url

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, User]] = {}

_transport: httpx.BaseTransport | None = None


def _cache_key(*parts: str | None) -> str:
    raw = "|".join(part or "" for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _forward_headers(
    authorization: str | None,
    x_dev_user: str | None,
    x_dev_role: str | None,
    x_admin_act_as_user: str | None,
    x_student_preview: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if x_dev_user:
        headers["X-Dev-User"] = x_dev_user
    if x_dev_role:
        headers["X-Dev-Role"] = x_dev_role
    if x_admin_act_as_user:
        headers["X-Admin-Act-As-User"] = x_admin_act_as_user
    if x_student_preview:
        headers["X-Student-Preview"] = x_student_preview
    return headers


def _peek_claims(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        return {}
    token = authorization.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, binascii.Error):
        return {}


def _pin_student_user(authorization: str) -> User | None:
    from app.core.firebase_auth import _verify_id_token

    token = authorization.split(" ", 1)[1].strip()
    claims = _verify_id_token(token)
    if not claims.get("lessons_student"):
        return None
    user_id = claims.get("uid") or claims.get("sub")
    user = get_repository().get_user(user_id) if user_id else None
    if not user or user.role != "student":
        raise AppError(
            "STUDENT_NOT_REGISTERED",
            "등록된 학생 계정이 아닙니다.",
            "선생님께 명단 등록을 다시 요청해 주세요.",
            403,
        )
    return user


async def lessons_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
    x_dev_role: str | None = Header(default=None, alias="X-Dev-Role"),
    x_admin_act_as_user: str | None = Header(default=None, alias="X-Admin-Act-As-User"),
    x_student_preview: str | None = Header(default=None, alias="X-Student-Preview"),
) -> User:
    key = _cache_key(authorization, x_dev_user, x_dev_role, x_admin_act_as_user, x_student_preview)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    if _peek_claims(authorization).get("lessons_student"):
        student = _pin_student_user(authorization)
        if student:
            _cache[key] = (now, student)
            return student

    forward_headers = _forward_headers(authorization, x_dev_user, x_dev_role, x_admin_act_as_user, x_student_preview)
    url = f"{main_backend_url()}/api/auth/me"
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=_transport) as client:
            response = await client.get(url, headers=forward_headers)
    except httpx.HTTPError as exc:
        raise AppError(
            "MAIN_BACKEND_UNREACHABLE",
            "주 백엔드에 연결할 수 없어 로그인을 확인할 수 없습니다.",
            "주 백엔드(기본 8080)가 실행 중인지 확인해 주세요.",
            503,
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(
            "MAIN_BACKEND_AUTH_INVALID_RESPONSE",
            "주 백엔드 로그인 응답을 읽을 수 없습니다.",
            "주 백엔드 상태를 확인해 주세요.",
            502,
        ) from exc

    if response.status_code != 200 or not body.get("success"):
        raise AppError(
            body.get("error_code", "MAIN_BACKEND_AUTH_FAILED"),
            body.get("error_message_ko", "주 백엔드에서 로그인 정보를 확인하지 못했습니다."),
            body.get("suggested_fix", "로그인 계정과 역할을 다시 확인해 주세요."),
            response.status_code if response.status_code != 200 else 401,
        )

    user = User(**body["data"])
    repo = get_repository()
    existing = repo.get_user(user.user_id)
    if existing:
        user.class_id = existing.class_id
        user.teacher_id = existing.teacher_id
        user.group_id = existing.group_id
    mirrored = repo.upsert_user(user)
    _cache[key] = (now, mirrored)
    return mirrored
