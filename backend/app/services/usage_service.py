from uuid import uuid4

from app.models.usage import UsageEvent
from app.repositories.factory import get_repository


class UsageService:
    def record_tool_call(self, user_id: str, tool_name: str, metadata: dict | None = None) -> None:
        get_repository().add_usage_event(
            UsageEvent(
                event_id=f"usage_{uuid4().hex[:12]}",
                user_id=user_id,
                event_type="tool_call",
                metadata={"tool_name": tool_name, **(metadata or {})},
            )
        )
