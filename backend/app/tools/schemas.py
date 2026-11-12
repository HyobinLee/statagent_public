from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from app.core.errors import AppError, error_response


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description_ko: str
    input_schema: dict
    output_schema: dict
    handler: Callable[..., dict]
    allowed_levels: list[str]
    status: str = "implemented"


def start_timer() -> float:
    return perf_counter()


def elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def tool_success(
    function: str,
    dataset_id: str | None,
    data: dict | list,
    explanation_hint: str,
    start: float,
    validation_warnings: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    base_metadata = {
        "function": function,
        "dataset_id": dataset_id,
        "execution_time_ms": elapsed_ms(start),
        "validation_warnings": validation_warnings or [],
    }
    if metadata:
        base_metadata.update(metadata)
    return {
        "success": True,
        "data": data,
        "metadata": base_metadata,
        "explanation_hint": explanation_hint,
    }


def tool_failure(function: str, dataset_id: str | None, exc: AppError, start: float) -> dict:
    payload = error_response(
        exc.error_code,
        exc.error_message_ko,
        exc.suggested_fix,
        {
            "function": function,
            "dataset_id": dataset_id,
            "execution_time_ms": elapsed_ms(start),
            "validation_warnings": [],
        },
    )
    payload["explanation_hint"] = None
    return payload
