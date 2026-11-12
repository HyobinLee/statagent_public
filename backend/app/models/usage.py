from datetime import UTC, datetime

from pydantic import Field, model_validator

from app.core.time import now_utc
from app.models.common import APIModel

UsageEventType = str


class UsageEvent(APIModel):
    event_id: str
    user_id: str
    event_type: UsageEventType
    prompt_hash: str | None = None
    prompt_length: int | None = None
    input_tokens_estimate: int | None = None
    output_tokens_estimate: int | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_event(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data["event_id"] = (
            data.get("event_id")
            or data.get("usage_event_id")
            or data.get("_document_id")
            or data.get("id")
            or "usage_legacy_unknown"
        )
        data["user_id"] = data.get("user_id") or data.get("uid") or "unknown"
        data["event_type"] = data.get("event_type") or data.get("type") or "unknown"
        if not isinstance(data.get("metadata"), dict):
            data["metadata"] = {}
        for field_name in ("prompt_length", "input_tokens_estimate", "output_tokens_estimate"):
            raw_value = data.get(field_name)
            if raw_value in ("", None):
                data[field_name] = None
                continue
            try:
                data[field_name] = int(raw_value)
            except (TypeError, ValueError):
                data[field_name] = None
        if "created_at" in data and data.get("created_at") in ("", None):
            data["created_at"] = datetime(1970, 1, 1, tzinfo=UTC)
        return data


class BlockEvent(APIModel):
    block_event_id: str
    user_id: str
    reason: str
    active: bool = True
    created_at: datetime = Field(default_factory=now_utc)
    resolved_at: datetime | None = None
