from datetime import timedelta
from uuid import uuid4

from app.core.errors import AppError
from app.core.security import hash_prompt
from app.core.time import now_utc
from app.models.usage import BlockEvent, UsageEvent
from app.repositories.factory import get_repository

BLOCK_DURATION_MINUTES = 5
DAILY_ESCALATION_THRESHOLD = 3
WORKFLOW_BYPASS_THRESHOLD = 3


def _timed_block_error(remaining_minutes: int) -> AppError:
    return AppError(
        "USER_TEMPORARILY_BLOCKED",
        f"5분간 일시 차단 상태입니다. 약 {remaining_minutes}분 후 자동 해제됩니다.",
        "잠시 기다리거나 교사에게 문의하세요.",
        429,
    )


BLOCKED_ERROR_PERMANENT = AppError(
    "USER_TEMPORARILY_BLOCKED",
    "교사 확인이 필요한 차단 상태입니다.",
    "교사 대시보드에서 차단 사유를 확인하고 해제할 수 있습니다.",
    429,
)


class BlockingService:
    def __init__(self) -> None:
        self.repo = get_repository()

    def _is_api_tool_block_exempt(self, user_id: str) -> bool:
        user = self.repo.get_user(user_id)
        if not user:
            return False
        if user.role in {"admin", "teacher"}:
            return True
        return user.role == "student" and bool((user.class_id or "").strip())

    def ensure_not_blocked(self, user_id: str) -> None:
        user = self.repo.get_user(user_id)
        if not user:
            return
        if user.is_blocked:
            raise BLOCKED_ERROR_PERMANENT
        if user.blocked_until:
            now = now_utc()
            if now < user.blocked_until:
                remaining_secs = int((user.blocked_until - now).total_seconds())
                remaining_min = max(1, (remaining_secs + 59) // 60)
                raise _timed_block_error(remaining_min)
            user.blocked_until = None
            user.block_reason = None
            self.repo.upsert_user(user)

    def block_user(self, user_id: str, reason: str, *, force_permanent: bool = False) -> None:
        user = self.repo.get_user(user_id)
        if not user:
            return
        if user.is_blocked:
            return

        today_count = self._count_today_block_events(user_id)
        use_permanent = force_permanent or today_count >= DAILY_ESCALATION_THRESHOLD - 1

        if use_permanent:
            escalated_reason = (
                reason
                if force_permanent
                else f"{reason} — 하루 {DAILY_ESCALATION_THRESHOLD}회 이상 차단: 교사 확인 필요"
            )
            self.repo.set_user_blocked(user_id, True, escalated_reason)
        else:
            user.blocked_until = now_utc() + timedelta(minutes=BLOCK_DURATION_MINUTES)
            user.block_reason = reason
            self.repo.upsert_user(user)

        self.repo.add_block_event(
            BlockEvent(block_event_id=f"block_{uuid4().hex[:12]}", user_id=user_id, reason=reason)
        )
        self.repo.add_usage_event(
            UsageEvent(
                event_id=f"usage_{uuid4().hex[:12]}",
                user_id=user_id,
                event_type="blocked",
                metadata={"reason": reason, "escalated": today_count >= DAILY_ESCALATION_THRESHOLD - 1},
            )
        )

    def unblock_user(self, user_id: str) -> None:
        self.repo.set_user_blocked(user_id, False)
        self.repo.resolve_block_events(user_id)
        self.repo.add_usage_event(
            UsageEvent(
                event_id=f"usage_{uuid4().hex[:12]}",
                user_id=user_id,
                event_type="unblocked",
                metadata={},
            )
        )

    def record_ai_call(self, user_id: str, prompt_text: str = "") -> None:
        self.ensure_not_blocked(user_id)
        prompt_length = len(prompt_text)
        event = UsageEvent(
            event_id=f"usage_{uuid4().hex[:12]}",
            user_id=user_id,
            event_type="ai_call",
            prompt_hash=hash_prompt(prompt_text) if prompt_text else None,
            prompt_length=prompt_length,
            input_tokens_estimate=max(1, prompt_length // 4) if prompt_text else None,
            metadata={"short_input": prompt_length <= 2},
        )
        self.repo.add_usage_event(event)

        if self._is_api_tool_block_exempt(user_id):
            return

        if prompt_length >= 5000:
            self.block_user(user_id, "한 번의 입력 길이 5,000자 이상")
            self.ensure_not_blocked(user_id)
            return

        events = [
            item for item in self.repo.list_usage_events() if item.user_id == user_id and item.event_type == "ai_call"
        ]
        now = now_utc()
        recent_5s = [item for item in events if now - item.created_at <= timedelta(seconds=5)]
        recent_1m = [item for item in events if now - item.created_at <= timedelta(minutes=1)]
        if len(recent_5s) >= 3:
            self.block_user(user_id, "5초 이내 동일 사용자 AI 호출 3회 이상")
            self.ensure_not_blocked(user_id)
            return
        if len(recent_1m) >= 10:
            self.block_user(user_id, "1분 이내 동일 사용자 AI 호출 10회 이상")
            self.ensure_not_blocked(user_id)
            return

        ordered = sorted(events, key=lambda item: item.created_at, reverse=True)
        short_streak = 0
        for item in ordered:
            if item.metadata.get("short_input"):
                short_streak += 1
            else:
                break
        if short_streak >= 5:
            self.block_user(user_id, "2자 이하 입력 5회 연속")
            self.ensure_not_blocked(user_id)

    def record_workflow_bypass(self, user_id: str, reason: str) -> None:
        self.repo.add_usage_event(
            UsageEvent(
                event_id=f"usage_{uuid4().hex[:12]}",
                user_id=user_id,
                event_type="workflow_bypass",
                metadata={"reason": reason},
            )
        )
        if self._is_api_tool_block_exempt(user_id):
            return
        events = [
            item
            for item in self.repo.list_usage_events()
            if item.user_id == user_id and item.event_type == "workflow_bypass"
        ]
        now = now_utc()
        recent = [item for item in events if now - item.created_at <= timedelta(minutes=5)]
        if len(recent) >= WORKFLOW_BYPASS_THRESHOLD:
            self.block_user(user_id, f"5분 내 workflow 우회 {WORKFLOW_BYPASS_THRESHOLD}회 이상: {reason}")

    def _count_today_block_events(self, user_id: str) -> int:
        now = now_utc()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for e in self.repo.list_block_events() if e.user_id == user_id and e.created_at >= today_start)
