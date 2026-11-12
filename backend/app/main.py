from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    admin,
    auth,
    datasets,
    dev,
    health,
    maps,
    merge,
    projects,
    reports,
    sso,
    stat,
    synthesis,
    teacher,
    topics,
)
from app.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, unhandled_error_handler


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="통계 에이전트 v0.1", version="0.1.0")
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=settings.local_chart_dir.parent), name="static")
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sso.router)
    app.include_router(topics.router)
    app.include_router(datasets.router)
    app.include_router(stat.router)
    app.include_router(merge.router)
    app.include_router(synthesis.router)
    app.include_router(maps.router)
    app.include_router(projects.router)
    app.include_router(reports.router)
    app.include_router(teacher.router)
    app.include_router(admin.router)
    app.include_router(dev.router)
    return app


app = create_app()
