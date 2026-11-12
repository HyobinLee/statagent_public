from app.core.errors import AppError, success_response
from app.dependencies import get_current_user
from app.models.user import User
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from lessons_app.services import discuss_store

router = APIRouter(prefix="/api/lessons/discuss", tags=["lesson-discuss"])

MAX_TEXT_LENGTH = 500


class SubmitRequest(BaseModel):
    text: str
    choice: str = Field(default="", max_length=8)
    after_reveal: bool = False
    input_ms: int | None = Field(default=None, ge=0, le=6 * 60 * 60 * 1000)


class FeedbackRequest(BaseModel):
    text: str = Field(default="", max_length=300)


class BoardPatchRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    highlighted: bool | None = None
    hidden: bool | None = None


def _assert_valid_text(text: str) -> str:
    trimmed = text.strip()
    if not trimmed:
        raise AppError(
            "DISCUSS_TEXT_REQUIRED",
            "의견을 입력해 주세요.",
            "한 문장이라도 적은 뒤에 보내 주세요.",
            400,
        )
    if len(trimmed) > MAX_TEXT_LENGTH:
        raise AppError(
            "DISCUSS_TEXT_TOO_LONG",
            f"의견은 {MAX_TEXT_LENGTH}자까지 쓸 수 있습니다.",
            "내용을 줄여서 다시 보내 주세요.",
            400,
        )
    return trimmed


def _assert_valid_board_patch(payload: BoardPatchRequest) -> dict:
    patch: dict = {}
    for field in ("x", "y"):
        value = getattr(payload, field)
        if value is None:
            continue
        if value < 0 or value > 1:
            raise AppError(
                "DISCUSS_BOARD_INVALID",
                "카드 위치는 0에서 1 사이여야 합니다.",
                "보드 안쪽으로 다시 놓아 주세요.",
                400,
            )
        patch[field] = value
    if patch:
        patch["placed"] = True
    if payload.highlighted is not None:
        patch["highlighted"] = payload.highlighted
    if payload.hidden is not None:
        patch["hidden"] = payload.hidden
    return patch


def _response_not_found() -> AppError:
    return AppError(
        "DISCUSS_RESPONSE_NOT_FOUND",
        "응답을 찾을 수 없습니다.",
        "보드를 새로고침해 주세요.",
        404,
    )


def _forbidden() -> AppError:
    return AppError(
        "DISCUSS_FORBIDDEN",
        "이 응답에 접근할 권한이 없습니다.",
        "본인이 낸 응답인지, 담당 학급인지 확인해 주세요.",
        403,
    )


@router.post("/{lesson_id}/prompts/{prompt_id}/responses")
def submit_response(
    lesson_id: str,
    prompt_id: str,
    payload: SubmitRequest,
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "student":
        raise AppError(
            "DISCUSS_FORBIDDEN",
            "학생만 의견을 제출할 수 있습니다.",
            "학생 계정으로 로그인해 주세요.",
            403,
        )
    text = _assert_valid_text(payload.text)
    response = discuss_store.upsert_response(
        lesson_id=lesson_id,
        prompt_id=prompt_id,
        class_id=user.class_id,
        teacher_id=user.teacher_id,
        user_id=user.user_id,
        display_name=user.display_name,
        text=text,
        choice=payload.choice.strip(),
        after_reveal=payload.after_reveal,
        input_ms=payload.input_ms,
    )
    return success_response(response)


@router.get("/{lesson_id}/prompts/{prompt_id}/responses")
def list_responses(
    lesson_id: str,
    prompt_id: str,
    class_id: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    if user.role == "admin":
        responses = discuss_store.list_for_prompt(lesson_id, prompt_id, class_id=class_id)
    elif user.role == "teacher":
        responses = discuss_store.list_for_prompt(lesson_id, prompt_id, teacher_id=user.user_id, class_id=class_id)
    else:
        responses = [
            response
            for response in discuss_store.list_for_prompt(lesson_id, prompt_id)
            if response["user_id"] == user.user_id
        ]
    return success_response(responses)


@router.get("/{lesson_id}/prompts/{prompt_id}/peers")
def list_peer_responses(
    lesson_id: str,
    prompt_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "student":
        raise AppError(
            "DISCUSS_FORBIDDEN",
            "친구들 의견 모아 보기는 학생 화면용입니다.",
            "교사는 응답 보드에서 봅니다.",
            403,
        )
    own_id = discuss_store.response_id(lesson_id, prompt_id, user.user_id)
    if discuss_store.get_response(own_id) is None:
        raise AppError(
            "DISCUSS_PEERS_LOCKED",
            "내 의견을 먼저 보내야 친구들 의견을 볼 수 있습니다.",
            "의견을 보낸 뒤 다시 눌러 주세요.",
            403,
        )
    if not user.class_id:
        return success_response([])
    discuss_store.mark_peers_viewed(own_id)
    peers = [
        response
        for response in discuss_store.list_for_prompt(lesson_id, prompt_id, class_id=user.class_id)
        if response.get("user_id") != user.user_id and not (response.get("board") or {}).get("hidden")
    ]
    peers.sort(key=lambda response: str(response.get("created_at") or ""))
    return success_response(
        [{"text": response.get("text", ""), "choice": response.get("choice") or ""} for response in peers]
    )


@router.patch("/responses/{response_id}/board")
def patch_board(
    response_id: str,
    payload: BoardPatchRequest,
    user: User = Depends(get_current_user),
) -> dict:
    if user.role not in ("teacher", "admin"):
        raise _forbidden()
    existing = discuss_store.get_response(response_id)
    if existing is None:
        raise _response_not_found()
    if user.role == "teacher" and existing.get("teacher_id") != user.user_id:
        raise _forbidden()
    patch = _assert_valid_board_patch(payload)
    updated = discuss_store.patch_board(response_id, patch)
    return success_response(updated)


@router.patch("/responses/{response_id}/feedback")
def patch_feedback(
    response_id: str,
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
) -> dict:
    if user.role not in ("teacher", "admin"):
        raise _forbidden()
    existing = discuss_store.get_response(response_id)
    if existing is None:
        raise _response_not_found()
    if user.role == "teacher" and existing.get("teacher_id") != user.user_id:
        raise _forbidden()
    updated = discuss_store.set_feedback(response_id, payload.text.strip(), user.user_id)
    return success_response(updated)


@router.delete("/responses/{response_id}")
def delete_response(response_id: str, user: User = Depends(get_current_user)) -> dict:
    existing = discuss_store.get_response(response_id)
    if existing is None:
        raise _response_not_found()
    is_owner = existing.get("user_id") == user.user_id
    is_class_staff = user.role == "admin" or (user.role == "teacher" and existing.get("teacher_id") == user.user_id)
    if not (is_owner or is_class_staff):
        raise _forbidden()
    discuss_store.delete_response(response_id)
    return success_response({"response_id": response_id})
