import httpx
from app.config import get_settings
from fastapi import APIRouter

from lessons_app.config import main_backend_url

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    main_reachable = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{main_backend_url()}/health")
            main_reachable = response.status_code == 200
    except httpx.HTTPError:
        main_reachable = False
    return {
        "status": "ok" if main_reachable else "degraded",
        "app": "statistics-agent-lessons",
        "env": settings.app_env,
        "main_backend_reachable": main_reachable,
    }
