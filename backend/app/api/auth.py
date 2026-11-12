from fastapi import APIRouter, Depends

from app.config import get_settings
from app.core.errors import success_response
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/client-config")
def client_config() -> dict:
    settings = get_settings()
    workspace_domain = settings.google_workspace_domain.strip().lower().lstrip("@")
    firebase_config = {
        "apiKey": settings.firebase_web_api_key,
        "authDomain": settings.firebase_auth_domain,
        "projectId": settings.firebase_project_id or settings.google_cloud_project,
        "appId": settings.firebase_app_id,
        "messagingSenderId": settings.firebase_messaging_sender_id,
        "measurementId": settings.firebase_measurement_id,
    }
    required = ["apiKey", "authDomain", "projectId", "appId"]
    missing = [key for key in required if not firebase_config.get(key)]
    return success_response(
        {
            "auth_provider": "dev" if settings.dev_auth_enabled else "firebase",
            "dev_auth_enabled": settings.dev_auth_enabled,
            "google_workspace_domain": workspace_domain,
            "google_workspace_email_pattern": f"@{workspace_domain}" if workspace_domain else "",
            "firebase_config": firebase_config,
            "missing_firebase_config": missing,
        }
    )


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return success_response(user.model_dump(mode="json"))
