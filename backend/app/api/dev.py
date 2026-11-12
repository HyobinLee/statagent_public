from fastapi import APIRouter

from app.config import get_settings
from app.core.errors import AppError, success_response
from app.repositories.factory import get_repository

router = APIRouter(prefix="/api/dev", tags=["dev"])


def _ensure_local() -> None:
    if get_settings().app_env != "local":
        raise AppError(
            "DEV_ENDPOINT_DISABLED",
            "개발 전용 API는 local 환경에서만 사용할 수 있습니다.",
            "APP_ENV를 확인해 주세요.",
            404,
        )


@router.post("/reset-local-data")
def reset_local_data() -> dict:
    _ensure_local()
    get_repository().reset()
    return success_response({"status": "reset"})


@router.post("/seed-local-data")
def seed_local_data() -> dict:
    _ensure_local()
    get_repository().seed()
    return success_response({"status": "seeded"})
