from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "statistics-agent", "env": get_settings().app_env}


@router.get("/api")
def api_root() -> dict:
    return {"success": True, "data": {"status": "ok", "app": "statistics-agent"}}
