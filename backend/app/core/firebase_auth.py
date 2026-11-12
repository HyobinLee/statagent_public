import json
import re
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings
from app.core.errors import AppError
from app.core.roles import ALLOWED_ROLES
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.secrets import SecretManagerService

EMAIL_PATTERN = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
EMAIL_SEARCH_PATTERN = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


@dataclass(frozen=True)
class FirebaseWhitelistEntry:
    email: str
    role: str | None = None
    display_name: str | None = None
    subject: str | None = None
    hosted_domain: str | None = None


@lru_cache
def _firebase_app():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise AppError(
            "GOOGLE_CLOUD_DEPENDENCY_MISSING",
            "Firebase Auth 연동 패키지가 설치되어 있지 않습니다.",
            '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
            500,
        ) from exc

    settings = get_settings()
    if firebase_admin._apps:
        return firebase_admin.get_app()

    options = {}
    project_id = settings.firebase_project_id or settings.google_cloud_project
    if project_id:
        options["projectId"] = project_id
    if settings.firebase_service_account_id:
        options["serviceAccountId"] = settings.firebase_service_account_id
    return firebase_admin.initialize_app(credentials.ApplicationDefault(), options=options)


def _verify_id_token(token: str) -> dict:
    try:
        from firebase_admin import auth
    except ImportError as exc:
        raise AppError(
            "GOOGLE_CLOUD_DEPENDENCY_MISSING",
            "Firebase Auth 연동 패키지가 설치되어 있지 않습니다.",
            '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
            500,
        ) from exc

    _firebase_app()
    try:
        return auth.verify_id_token(token)
    except Exception as exc:
        raise AppError(
            "INVALID_FIREBASE_TOKEN",
            "Firebase ID token을 검증할 수 없습니다.",
            "Authorization: Bearer <ID_TOKEN> 형식과 Firebase 프로젝트 설정을 확인해 주세요.",
            401,
        ) from exc


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_email(value: object) -> str | None:
    text = _clean_optional_text(value)
    if not text:
        return None
    return text.lower()


def _is_active(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", "inactive"}
    return bool(value)


def _entry_from_email(email: str) -> FirebaseWhitelistEntry | None:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        return None
    return FirebaseWhitelistEntry(email=normalized)


def _entry_from_dict(item: dict) -> FirebaseWhitelistEntry | None:
    if not _is_active(item.get("active", True)):
        return None

    email = _clean_optional_text(item.get("email"))
    if not email:
        return None

    entry = _entry_from_email(email)
    if not entry:
        return None

    role = _clean_optional_text(item.get("role"))
    role = role.lower() if role else None
    if role not in ALLOWED_ROLES:
        role = None

    return FirebaseWhitelistEntry(
        email=entry.email,
        role=role,
        display_name=_clean_optional_text(item.get("display_name")),
        subject=_clean_optional_text(item.get("subject")),
        hosted_domain=_clean_optional_text(item.get("hosted_domain")),
    )


def _entries_from_sequence(items: list) -> dict[str, FirebaseWhitelistEntry]:
    entries: dict[str, FirebaseWhitelistEntry] = {}
    for item in items:
        entry = _entry_from_dict(item) if isinstance(item, dict) else _entry_from_email(str(item))
        if entry:
            entries[entry.email] = entry
    return entries


def parse_firebase_whitelist(raw: str) -> dict[str, FirebaseWhitelistEntry]:
    stripped = raw.strip()
    if not stripped:
        return {}

    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _entries_from_sequence(parsed)
        if isinstance(parsed, dict):
            for key in ("entries", "users", "whitelist", "emails"):
                candidates = parsed.get(key)
                if isinstance(candidates, list):
                    return _entries_from_sequence(candidates)

    entries = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0]
        for candidate in EMAIL_SEARCH_PATTERN.findall(line):
            entry = _entry_from_email(candidate)
            if entry:
                entries[entry.email] = entry
    return entries


def _firebase_whitelist() -> dict[str, FirebaseWhitelistEntry]:
    settings = get_settings()
    if not settings.firebase_whitelist_secret:
        return {}
    raw = SecretManagerService().access_secret(settings.firebase_whitelist_secret)
    return parse_firebase_whitelist(raw)


def _admin_whitelist_entry(email: str) -> FirebaseWhitelistEntry | None:
    settings = get_settings()
    if not settings.firebase_whitelist_secret:
        return None

    entry = _firebase_whitelist().get(email.strip().lower())
    if entry and entry.role == "admin":
        return entry
    return None


def get_firebase_user(authorization: str | None) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(
            "AUTHORIZATION_REQUIRED",
            "Firebase 인증 토큰이 필요합니다.",
            "Authorization: Bearer <ID_TOKEN> 헤더를 포함해 주세요.",
            401,
        )

    settings = get_settings()
    token = authorization.split(" ", 1)[1].strip()
    claims = _verify_id_token(token)
    email = _normalize_email(claims.get("email"))
    if not email:
        raise AppError(
            "EMAIL_REQUIRED",
            "Firebase token에 이메일 정보가 없습니다.",
            "이메일이 포함된 학교 계정으로 로그인해 주세요.",
            403,
        )

    admin_entry = _admin_whitelist_entry(email)
    repo = get_repository()
    user = repo.get_user_by_email(email)

    if admin_entry:
        if user:
            if user.role != "admin":
                user.role = "admin"
                user = repo.upsert_user(user)
            return user
        user = User(
            user_id=claims.get("uid") or admin_entry.subject or claims.get("sub"),
            email=email,
            role="admin",
            display_name=admin_entry.display_name or claims.get("name") or email,
            class_id=claims.get("class_id"),
        )
        return repo.upsert_user(user)

    if user:
        return user

    if not settings.auto_provision_firebase_users:
        raise AppError(
            "USER_NOT_REGISTERED",
            "등록된 사용자가 아닙니다.",
            "관리자가 users 컬렉션에 사용자를 먼저 등록해야 합니다.",
            403,
        )

    role = claims.get("role") or settings.firebase_default_role
    if role == "admin" or role not in ALLOWED_ROLES:
        raise AppError(
            "ROLE_CLAIM_REQUIRED",
            "자동 사용자 등록에는 올바른 Firebase role 설정이 필요합니다.",
            "role claim을 teacher 또는 student로 설정해 주세요. admin은 Secret Manager 화이트리스트로만 관리됩니다.",
            403,
        )

    user = User(
        user_id=claims.get("uid") or claims.get("sub"),
        email=email,
        role=role,
        display_name=claims.get("name") or email,
        class_id=claims.get("class_id"),
    )
    return repo.upsert_user(user)
