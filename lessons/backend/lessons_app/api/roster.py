from datetime import datetime

from app.core.errors import AppError, success_response
from app.core.time import now_utc
from app.dependencies import require_any_role
from app.models.user import User
from app.repositories.factory import get_repository
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import lesson_store, progress, session_store, student_accounts, tracks

router = APIRouter(prefix="/api/lessons/roster", tags=["lesson-roster"])

MAX_NAMES = 60


class CreateRosterRequest(BaseModel):
    class_id: str = Field(..., min_length=1, max_length=80)
    names: list[str] = Field(default_factory=list)
    track: str = Field(default="", max_length=16)
    scenario: str = Field(default="", max_length=16)


def _validate_track_scenario(track: str, scenario: str) -> None:
    if track and track not in tracks.VALID_TRACKS:
        raise AppError(
            "TRACK_INVALID",
            "트랙 값이 올바르지 않습니다.",
            "m1, m3, high, gifted 중 하나를 골라 주세요.",
            400,
        )
    if scenario and scenario not in tracks.VALID_SCENARIOS:
        raise AppError(
            "SCENARIO_INVALID",
            "시나리오 값이 올바르지 않습니다.",
            "full(정규 7차시) 또는 exp2(실험수업 2차시)를 골라 주세요.",
            400,
        )


def _class_payload(record: dict) -> dict:
    track = tracks.normalize_track(record.get("track"))
    scenario = tracks.normalize_scenario(record.get("scenario"))
    return {
        "code": record["code"],
        "class_id": record["class_id"],
        "join_url": record.get("join_url", ""),
        "track": track,
        "track_label": tracks.TRACK_LABELS[track],
        "scenario": scenario,
        "scenario_label": tracks.SCENARIO_LABELS[scenario],
    }


class JoinUrlRequest(BaseModel):
    join_url: str = Field(default="", max_length=300)


def _assert_owns_class(user: User, class_id: str) -> None:
    if user.role == "admin":
        return
    students = student_accounts.list_class_students(class_id)
    if students and all(student.teacher_id != user.user_id for student in students):
        raise AppError(
            "ROSTER_FORBIDDEN",
            "담당 학급이 아닙니다.",
            "담당 학급인지 확인해 주세요.",
            403,
        )
    codes = lesson_store.list_docs(student_accounts.CLASS_CODES, class_id=class_id)
    if codes and all(record.get("teacher_id") != user.user_id for record in codes):
        raise AppError(
            "ROSTER_FORBIDDEN",
            "다른 선생님이 쓰고 있는 학급 이름입니다.",
            "다른 학급 이름을 쓰거나 관리자에게 문의해 주세요.",
            403,
        )


@router.get("")
def list_my_classes(user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    records = lesson_store.list_docs(student_accounts.CLASS_CODES)
    if user.role != "admin":
        records = [record for record in records if record.get("teacher_id") == user.user_id]
    classes = []
    for record in sorted(records, key=lambda r: str(r.get("created_at", "")), reverse=True):
        classes.append(
            {
                **_class_payload(record),
                "student_count": len(student_accounts.list_class_students(record["class_id"])),
                "created_at": record.get("created_at", ""),
            }
        )
    return success_response({"classes": classes})


@router.delete("/{class_id}")
def close_class(class_id: str, user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    _assert_owns_class(user, class_id)
    students = student_accounts.list_class_students(class_id)
    repo = get_repository()
    for student in students:
        for lesson_id in progress.LESSON_IDS:
            progress.reset_lesson(student.user_id, lesson_id)
        lesson_store.delete_doc(student_accounts.STUDENT_PINS, student.user_id)
        repo.delete_user(student.user_id)
    for record in lesson_store.list_docs(student_accounts.CLASS_CODES, class_id=class_id):
        lesson_store.delete_doc(student_accounts.CLASS_CODES, record["code"])
    lesson_store.delete_doc(session_store.COLLECTION, class_id)
    return success_response({"class_id": class_id, "deleted_students": len(students)})


@router.post("")
def create_roster(
    payload: CreateRosterRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, payload.class_id)
    names = [name.strip() for name in payload.names if name.strip()]
    if not names:
        raise AppError(
            "ROSTER_NAMES_REQUIRED",
            "학생 이름을 한 명 이상 입력해 주세요.",
            "한 줄에 한 명씩 이름을 붙여넣어 주세요.",
            400,
        )
    if len(names) > MAX_NAMES:
        raise AppError(
            "ROSTER_TOO_MANY_NAMES",
            f"한 번에 {MAX_NAMES}명까지 만들 수 있습니다.",
            "명단을 나누어 등록해 주세요.",
            400,
        )

    _validate_track_scenario(payload.track, payload.scenario)
    result = student_accounts.create_students(payload.class_id, user.user_id, names)
    code = student_accounts.ensure_class_code(
        payload.class_id, user.user_id, track=payload.track, scenario=payload.scenario
    )
    return success_response(
        {
            **_class_payload(code),
            "students": result["created"],
            "skipped": result["skipped"],
        }
    )


@router.get("/{class_id}")
def get_roster(class_id: str, user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    _assert_owns_class(user, class_id)
    code = student_accounts.ensure_class_code(class_id, user.user_id)
    students = []
    for student in student_accounts.list_class_students(class_id):
        record = lesson_store.get_doc(student_accounts.STUDENT_PINS, student.user_id)
        students.append(
            {
                "user_id": student.user_id,
                "display_name": student.display_name,
                "has_pin": record is not None,
                "pin": (record or {}).get("pin"),
            }
        )
    return success_response({**_class_payload(code), "students": students})


class RenameStudentRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=40)


@router.patch("/{class_id}/students/{user_id}")
def rename_student(
    class_id: str,
    user_id: str,
    payload: RenameStudentRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    student = student_accounts.rename_student(class_id, user_id, payload.display_name)
    return success_response({"user_id": student.user_id, "display_name": student.display_name})


@router.delete("/{class_id}/students/{user_id}")
def remove_student(
    class_id: str,
    user_id: str,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    student = student_accounts.remove_student(class_id, user_id)
    return success_response({"user_id": student.user_id, "display_name": student.display_name})


class TrackRequest(BaseModel):
    track: str = Field(default="", max_length=16)
    scenario: str = Field(default="", max_length=16)


@router.put("/{class_id}/track")
def set_class_track(
    class_id: str,
    payload: TrackRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    _validate_track_scenario(payload.track, payload.scenario)
    record = student_accounts.ensure_class_code(class_id, user.user_id, track=payload.track, scenario=payload.scenario)
    return success_response(_class_payload(record))


@router.put("/{class_id}/join-url")
def set_join_url(
    class_id: str,
    payload: JoinUrlRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    join_url = payload.join_url.strip()
    if join_url and not join_url.startswith(("http://", "https://")):
        raise AppError(
            "JOIN_URL_INVALID",
            "주소는 http:// 또는 https:// 로 시작해야 합니다.",
            "단축 URL 서비스가 알려준 주소를 그대로 붙여넣어 주세요.",
            400,
        )
    record = student_accounts.set_join_url(class_id, user.user_id, join_url)
    return success_response(_class_payload(record))


@router.post("/{class_id}/rotate-code")
def rotate_code(class_id: str, user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    _assert_owns_class(user, class_id)
    record = student_accounts.rotate_class_code(class_id, user.user_id)
    return success_response(_class_payload(record))


@router.get("/{class_id}/pins")
def get_pin_status(class_id: str, user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    _assert_owns_class(user, class_id)
    now = now_utc()

    students = []
    for student in student_accounts.list_class_students(class_id):
        record = lesson_store.get_doc(student_accounts.STUDENT_PINS, student.user_id)
        locked_until = (record or {}).get("locked_until")
        locked = False
        if locked_until:
            try:
                locked = datetime.fromisoformat(locked_until) > now
            except ValueError:
                locked = False
        students.append(
            {
                "user_id": student.user_id,
                "display_name": student.display_name,
                "has_pin": record is not None,
                "pin": (record or {}).get("pin"),
                "locked": locked,
                "locked_until": locked_until if locked else None,
                "failed_count": (record or {}).get("failed_count", 0),
                "issued_at": (record or {}).get("updated_at", ""),
            }
        )

    return success_response(
        {
            "class_id": class_id,
            "students": students,
            "pin_visible": True,
            "pin_note": (
                "PIN 칸을 누르면 보입니다. '재발급 필요'는 평문 보관 전환 전에 "
                "발급된 학생으로, 원문을 보려면 재발급해 주세요."
            ),
        }
    )


class ReissuePinsRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


@router.post("/{class_id}/reissue-pins")
def reissue_pins(
    class_id: str,
    payload: ReissuePinsRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    students = student_accounts.list_class_students(class_id)
    if payload.user_ids:
        wanted = set(payload.user_ids)
        students = [student for student in students if student.user_id in wanted]
        missing = wanted - {student.user_id for student in students}
        if missing:
            raise AppError(
                "STUDENT_NOT_IN_CLASS",
                "이 학급에 없는 학생이 섞여 있습니다.",
                "명단을 새로고침한 뒤 다시 시도해 주세요.",
                404,
            )
    if not students:
        raise AppError(
            "ROSTER_EMPTY",
            "PIN을 발급할 학생이 없습니다.",
            "먼저 학급 명단을 만들어 주세요.",
            400,
        )

    issued = [
        {
            "user_id": student.user_id,
            "display_name": student.display_name,
            "pin": student_accounts.reset_pin(student.user_id),
        }
        for student in students
    ]
    return success_response({"class_id": class_id, "students": issued})


@router.post("/{class_id}/students/{user_id}/reset-pin")
def reset_student_pin(
    class_id: str,
    user_id: str,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    _assert_owns_class(user, class_id)
    student = get_repository().get_user(user_id)
    if not student or student.role != "student" or student.class_id != class_id:
        raise AppError(
            "STUDENT_NOT_IN_CLASS",
            "이 학급에서 그 학생을 찾을 수 없습니다.",
            "명단을 새로고침해 주세요.",
            404,
        )
    pin = student_accounts.reset_pin(user_id)
    return success_response({"user_id": user_id, "display_name": student.display_name, "pin": pin})
