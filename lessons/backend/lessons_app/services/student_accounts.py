import hashlib
import secrets
from typing import Any

from app.core.errors import AppError
from app.core.time import now_utc
from app.models.user import User
from app.repositories.factory import get_repository

from lessons_app.services import lesson_store

CLASS_CODES = "classCodes"
STUDENT_PINS = "studentPins"

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6

_MAX_FAILED_ATTEMPTS = 5
_LOCK_SECONDS = 300

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _hash_pin(pin: str, salt: str) -> str:
    derived = hashlib.scrypt(
        pin.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return derived.hex()


def generate_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"


def generate_class_code() -> str:
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if lesson_store.get_doc(CLASS_CODES, code) is None:
            return code


def _set_pin(user_id: str, pin: str) -> None:
    lesson_store.set_doc(
        STUDENT_PINS,
        user_id,
        {
            "user_id": user_id,
            "pin": pin,
            "failed_count": 0,
            "locked_until": None,
            "updated_at": now_utc().isoformat(),
        },
    )


def get_class_record(class_id: str) -> dict | None:
    records = lesson_store.list_docs(CLASS_CODES, class_id=class_id)
    return records[0] if records else None


def get_class_by_code(code: str) -> dict:
    record = lesson_store.get_doc(CLASS_CODES, (code or "").strip().upper())
    if not record:
        raise AppError(
            "CLASS_CODE_NOT_FOUND",
            "학급 코드를 찾을 수 없습니다.",
            "선생님이 화면에 띄운 코드를 다시 확인해 주세요.",
            404,
        )
    return record


def list_class_students(class_id: str) -> list[User]:
    students = [user for user in get_repository().list_users() if user.role == "student" and user.class_id == class_id]
    students.sort(key=lambda user: user.display_name)
    return students


def roster_for_code(code: str) -> dict:
    record = get_class_by_code(code)
    students = [
        {"user_id": student.user_id, "display_name": student.display_name}
        for student in list_class_students(record["class_id"])
        if lesson_store.get_doc(STUDENT_PINS, student.user_id) is not None
    ]
    return {
        "class_id": record["class_id"],
        "code": record["code"],
        "track": record.get("track", ""),
        "scenario": record.get("scenario", ""),
        "students": students,
    }


def ensure_class_code(class_id: str, teacher_id: str, track: str = "", scenario: str = "") -> dict:
    from lessons_app.services import tracks

    existing = [
        record
        for record in lesson_store.list_docs(CLASS_CODES, class_id=class_id)
        if record.get("teacher_id") == teacher_id
    ]
    if existing:
        record = existing[0]
        patch = {}
        if track and tracks.normalize_track(track) != record.get("track"):
            patch["track"] = tracks.normalize_track(track)
        if scenario and tracks.normalize_scenario(scenario) != record.get("scenario"):
            patch["scenario"] = tracks.normalize_scenario(scenario)
        if not record.get("track"):
            patch.setdefault("track", tracks.DEFAULT_TRACK)
        if not record.get("scenario"):
            patch.setdefault("scenario", tracks.DEFAULT_SCENARIO)
        if patch:
            record = {**record, **patch}
            lesson_store.set_doc(CLASS_CODES, record["code"], record)
        return record
    return rotate_class_code(class_id, teacher_id, track=track, scenario=scenario)


def rotate_class_code(class_id: str, teacher_id: str, track: str = "", scenario: str = "") -> dict:
    from lessons_app.services import tracks

    join_url = ""
    kept_track = ""
    kept_scenario = ""
    for record in lesson_store.list_docs(CLASS_CODES, class_id=class_id):
        if record.get("teacher_id") == teacher_id:
            join_url = record.get("join_url") or join_url
            kept_track = record.get("track") or kept_track
            kept_scenario = record.get("scenario") or kept_scenario
            lesson_store.delete_doc(CLASS_CODES, record["code"])
    code = generate_class_code()
    record = {
        "code": code,
        "class_id": class_id,
        "teacher_id": teacher_id,
        "join_url": join_url,
        "track": tracks.normalize_track(track or kept_track),
        "scenario": tracks.normalize_scenario(scenario or kept_scenario),
        "created_at": now_utc().isoformat(),
    }
    return lesson_store.set_doc(CLASS_CODES, code, record)


def set_join_url(class_id: str, teacher_id: str, join_url: str) -> dict:
    record = ensure_class_code(class_id, teacher_id)
    record = {**record, "join_url": join_url}
    return lesson_store.set_doc(CLASS_CODES, record["code"], record)


def create_students(class_id: str, teacher_id: str, names: list[str]) -> dict:
    repo = get_repository()
    existing_names = {student.display_name for student in list_class_students(class_id)}
    created = []
    skipped = []
    for raw_name in names:
        display_name = raw_name.strip()
        if not display_name:
            continue
        if display_name in existing_names:
            skipped.append(display_name)
            continue
        existing_names.add(display_name)
        user_id = f"lesson-student-{secrets.token_hex(8)}"
        user = User(
            user_id=user_id,
            email=f"{user_id}@lesson.local",
            role="student",
            display_name=display_name,
            class_id=class_id,
            teacher_id=teacher_id,
        )
        repo.upsert_user(user)
        pin = generate_pin()
        _set_pin(user_id, pin)
        created.append({"user_id": user_id, "display_name": display_name, "pin": pin})
    return {"created": created, "skipped": skipped}


def get_class_student(class_id: str, user_id: str) -> User:
    student = get_repository().get_user(user_id)
    if not student or student.role != "student" or student.class_id != class_id:
        raise AppError(
            "STUDENT_NOT_IN_CLASS",
            "이 학급에서 그 학생을 찾을 수 없습니다.",
            "명단을 새로고침해 주세요.",
            404,
        )
    return student


def rename_student(class_id: str, user_id: str, display_name: str) -> User:
    student = get_class_student(class_id, user_id)
    name = (display_name or "").strip()
    if not name:
        raise AppError(
            "STUDENT_NAME_REQUIRED",
            "학생 이름을 입력해 주세요.",
            "빈 이름으로는 바꿀 수 없습니다.",
            400,
        )
    duplicated = any(other.user_id != user_id and other.display_name == name for other in list_class_students(class_id))
    if duplicated:
        raise AppError(
            "STUDENT_NAME_DUPLICATED",
            "같은 학급에 이미 그 이름이 있습니다.",
            '"김민준2"처럼 구분되는 이름으로 넣어 주세요.',
            409,
        )
    student.display_name = name
    return get_repository().upsert_user(student)


def remove_student(class_id: str, user_id: str) -> User:
    from lessons_app.services import progress

    student = get_class_student(class_id, user_id)
    for lesson_id in progress.LESSON_IDS:
        progress.reset_lesson(user_id, lesson_id)
    lesson_store.delete_doc(STUDENT_PINS, user_id)
    get_repository().delete_user(user_id)
    return student


def reset_pin(user_id: str) -> str:
    pin = generate_pin()
    _set_pin(user_id, pin)
    return pin


def _lock_error() -> AppError:
    return AppError(
        "STUDENT_PIN_LOCKED",
        "PIN을 여러 번 틀려 잠시 잠겼습니다.",
        "5분 뒤에 다시 시도하거나 선생님께 PIN 재발급을 요청해 주세요.",
        429,
    )


def verify_pin(code: str, user_id: str, pin: str) -> User:
    record = get_class_by_code(code)
    repo = get_repository()
    user = repo.get_user(user_id)
    if not user or user.role != "student" or user.class_id != record["class_id"]:
        raise AppError(
            "STUDENT_NOT_IN_CLASS",
            "이 학급에서 그 이름을 찾을 수 없습니다.",
            "학급 코드와 이름을 다시 확인해 주세요.",
            404,
        )

    credential: dict[str, Any] | None = lesson_store.get_doc(STUDENT_PINS, user_id)
    if not credential:
        raise AppError(
            "STUDENT_PIN_NOT_SET",
            "이 학생은 아직 PIN이 발급되지 않았습니다.",
            "선생님께 PIN 발급을 요청해 주세요.",
            403,
        )

    now = now_utc()
    locked_until = credential.get("locked_until")
    if locked_until and locked_until > now.isoformat():
        raise _lock_error()

    entered = (pin or "").strip()
    stored_pin = credential.get("pin")
    if stored_pin is not None:
        matched = secrets.compare_digest(str(stored_pin).encode("utf-8"), entered.encode("utf-8"))
    else:
        expected = _hash_pin(entered, credential["salt"])
        matched = secrets.compare_digest(expected, credential["pin_hash"])
    if not matched:
        failed = int(credential.get("failed_count") or 0) + 1
        patch: dict[str, Any] = {"failed_count": failed}
        if failed >= _MAX_FAILED_ATTEMPTS:
            patch["failed_count"] = 0
            patch["locked_until"] = _plus_seconds(_LOCK_SECONDS)
        lesson_store.update_doc(STUDENT_PINS, user_id, patch)
        if failed >= _MAX_FAILED_ATTEMPTS:
            raise _lock_error()
        raise AppError(
            "STUDENT_PIN_INVALID",
            "PIN이 맞지 않습니다.",
            f"남은 시도 {_MAX_FAILED_ATTEMPTS - failed}회입니다. 선생님께 문의해 주세요.",
            401,
        )

    lesson_store.update_doc(STUDENT_PINS, user_id, {"failed_count": 0, "locked_until": None})
    return user


def _plus_seconds(seconds: int) -> str:
    from datetime import timedelta

    return (now_utc() + timedelta(seconds=seconds)).isoformat()


def create_custom_token(user_id: str) -> str:
    try:
        from firebase_admin import auth
    except ImportError as exc:
        raise AppError(
            "GOOGLE_CLOUD_DEPENDENCY_MISSING",
            "Firebase Auth 연동 패키지가 설치되어 있지 않습니다.",
            '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
            500,
        ) from exc

    from app.core.firebase_auth import _firebase_app

    _firebase_app()
    try:
        token = auth.create_custom_token(user_id, {"lessons_student": True})
    except Exception as exc:
        raise AppError(
            "CUSTOM_TOKEN_FAILED",
            "학생 로그인 토큰을 만들지 못했습니다.",
            "Cloud Run 서비스 계정에 roles/iam.serviceAccountTokenCreator 권한이 있는지 확인해 주세요.",
            500,
        ) from exc
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)
