import logging

from app.api import auth, datasets, maps, projects, topics
from app.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, unhandled_error_handler
from app.dependencies import get_current_user
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from lessons_app.api import (
    admin,
    careers,
    column_evidence,
    connectors,
    diag,
    discuss,
    fixed_analysis,
    group_share,
    health,
    inquiry,
    lessons,
    roster,
    sessions,
    student_auth,
    teacher_dashboard,
    transform,
)
from lessons_app.auth import lessons_current_user
from lessons_app.config import LESSONS_BACKEND_DIR, ensure_env_defaults

logger = logging.getLogger(__name__)

_LESSONS_API_ALIAS_PREFIX = "/api/lessons"
LESSONS_FRONTEND_DIR = LESSONS_BACKEND_DIR.parent / "frontend"

_MAIN_BACKEND_ROUTERS = (auth.router, datasets.router, projects.router, topics.router, maps.router)
_LESSON_ROUTERS = (
    health.router,
    connectors.router,
    transform.router,
    careers.router,
    group_share.router,
    teacher_dashboard.router,
    admin.router,
    student_auth.router,
    roster.router,
    sessions.router,
    discuss.router,
    column_evidence.router,
    inquiry.router,
    fixed_analysis.router,
    diag.router,
    lessons.router,
)


def create_app() -> FastAPI:
    ensure_env_defaults()
    settings = get_settings()
    app = FastAPI(title="통계 에이전트 차시", version="0.1.0")
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.middleware("http")
    async def catch_unhandled(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("처리하지 못한 예외: %s %s", request.method, request.url.path)
            return await unhandled_error_handler(request, exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=settings.local_chart_dir.parent), name="static")

    app.dependency_overrides[get_current_user] = lessons_current_user

    for router in _MAIN_BACKEND_ROUTERS:
        app.include_router(router)
        app.include_router(router, prefix=_LESSONS_API_ALIAS_PREFIX, include_in_schema=False)
    for router in _LESSON_ROUTERS:
        app.include_router(router)

    if LESSONS_FRONTEND_DIR.is_dir():

        @app.get("/lessons", include_in_schema=False)
        def redirect_lessons_root() -> RedirectResponse:
            return RedirectResponse(url="/lessons/")

        app.mount("/lessons", StaticFiles(directory=LESSONS_FRONTEND_DIR, html=True), name="lessons-frontend")
    return app


app = create_app()
