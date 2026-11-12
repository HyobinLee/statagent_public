from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.time import now_utc
from app.models.common import APIModel

UserRole = Literal["admin", "teacher", "student"]


class User(APIModel):
    user_id: str
    email: str
    role: UserRole
    display_name: str
    class_id: str | None = None
    teacher_id: str | None = None
    group_id: str | None = None
    is_blocked: bool = False
    block_reason: str | None = None
    blocked_until: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
