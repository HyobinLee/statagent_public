from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        error_code: str,
        error_message_ko: str,
        suggested_fix: str,
        status_code: int = 400,
        metadata: dict | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_message_ko = error_message_ko
        self.suggested_fix = suggested_fix
        self.status_code = status_code
        self.metadata = metadata or {}


def success_response(data: object, metadata: dict | None = None) -> dict:
    return {"success": True, "data": data, "metadata": metadata or {}}


def error_response(
    error_code: str,
    error_message_ko: str,
    suggested_fix: str,
    metadata: dict | None = None,
) -> dict:
    return {
        "success": False,
        "error_code": error_code,
        "error_message_ko": error_message_ko,
        "suggested_fix": suggested_fix,
        "metadata": metadata or {},
    }


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            exc.error_code,
            exc.error_message_ko,
            exc.suggested_fix,
            exc.metadata,
        ),
    )


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code == 403:
        return JSONResponse(
            status_code=403,
            content=error_response(
                "FORBIDDEN",
                "이 기능을 사용할 권한이 없습니다.",
                "로그인 계정에 배정된 역할을 확인해 주세요.",
            ),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            "HTTP_ERROR",
            str(exc.detail),
            "요청 내용을 확인해 주세요.",
        ),
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_response(
            "INTERNAL_SERVER_ERROR",
            "서버 처리 중 오류가 발생했습니다.",
            "잠시 후 다시 시도하고, 문제가 계속되면 교사나 관리자에게 알려 주세요.",
        ),
    )
