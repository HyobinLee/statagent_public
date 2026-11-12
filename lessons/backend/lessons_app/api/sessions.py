from app.core.errors import AppError, success_response
from app.core.time import now_utc
from app.dependencies import get_current_user
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from lessons_app.services import classroom, session_store

router = APIRouter(prefix="/api/lessons/sessions", tags=["lesson-session"])

MAX_RANGE_CARDS = 200


class FocusRequest(BaseModel):
    lesson_id: str
    level: str | None = None
    step: int
    card: int


class LockRequest(BaseModel):
    lock: bool


class OpenRequest(BaseModel):
    lesson_id: str
    level: str | None = None


class FollowRequest(BaseModel):
    follow: bool


class RangeCard(BaseModel):
    step: int
    card: int


class RangeRequest(BaseModel):
    cards: list[RangeCard] = []
    lesson_id: str | None = None


class RevealRequest(BaseModel):
    key: str
    value: bool


class ClearRevealsRequest(BaseModel):
    keys: list[str] = []


def _assert_non_negative(step: int, card: int) -> None:
    if step < 0 or card < 0:
        raise AppError(
            "SESSION_FOCUS_INVALID",
            "카드 위치가 올바르지 않습니다.",
            "0 이상의 값을 보내 주세요.",
            400,
        )


def _with_presence(session: dict) -> dict:
    return {
        **session,
        "teacher_active": session_store.teacher_active(session),
        "server_time": now_utc().isoformat(),
        "teacher_active_window_seconds": session_store.TEACHER_ACTIVE_WINDOW_SECONDS,
    }


@router.get("/me/current")
def get_my_session(user: User = Depends(get_current_user)) -> dict:
    class_id = classroom.student_class_id(user)
    return success_response(_with_presence(session_store.read_session(class_id)))


@router.get("/{class_id}")
def get_session(class_id: str, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_read_session(user, class_id)
    return success_response(_with_presence(session_store.read_session(class_id)))


@router.put("/{class_id}/open")
def mark_open(class_id: str, payload: OpenRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    session = session_store.mark_teacher_open(class_id, user.user_id, payload.lesson_id, payload.level)
    return success_response(_with_presence(session))


@router.put("/{class_id}/focus")
def push_focus(class_id: str, payload: FocusRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    _assert_non_negative(payload.step, payload.card)
    session = session_store.push_focus(
        class_id, user.user_id, payload.lesson_id, payload.level, payload.step, payload.card
    )
    return success_response(session)


@router.put("/{class_id}/lock")
def set_lock(class_id: str, payload: LockRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    session = session_store.set_lock(class_id, user.user_id, payload.lock)
    return success_response(session)


@router.put("/{class_id}/follow")
def set_follow(class_id: str, payload: FollowRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    session = session_store.set_follow(class_id, user.user_id, payload.follow)
    return success_response(session)


@router.put("/{class_id}/range")
def set_range(class_id: str, payload: RangeRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    for item in payload.cards:
        _assert_non_negative(item.step, item.card)
    if len(payload.cards) > MAX_RANGE_CARDS:
        raise AppError(
            "SESSION_RANGE_TOO_LARGE",
            "학습 범위로 지정할 수 있는 카드 수를 넘었습니다.",
            f"{MAX_RANGE_CARDS}장 이하로 골라 주세요.",
            400,
        )
    session = session_store.set_range(
        class_id, user.user_id, [item.model_dump() for item in payload.cards], payload.lesson_id
    )
    return success_response(session)


@router.put("/{class_id}/reveal")
def set_reveal(class_id: str, payload: RevealRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    session = session_store.set_reveal(class_id, user.user_id, payload.key, payload.value)
    return success_response(session)


@router.put("/{class_id}/reveals/clear")
def clear_reveals(class_id: str, payload: ClearRevealsRequest, user: User = Depends(get_current_user)) -> dict:
    classroom.assert_can_control_session(user, class_id)
    session = session_store.clear_reveals(class_id, user.user_id, payload.keys or None)
    return success_response(session)
