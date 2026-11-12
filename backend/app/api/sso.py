from fastapi import APIRouter, Depends

from app.config import get_settings
from app.core.errors import success_response
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/sso", tags=["sso"])


def _normalized_domain() -> str:
    return get_settings().google_workspace_domain.strip().lower().lstrip("@")


@router.get("/google-workspace")
def google_workspace_sso(user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    domain = _normalized_domain()

    if settings.dev_auth_enabled:
        return success_response(
            {
                "provider": "google-workspace",
                "workspace_domain": domain,
                "workspace_email_pattern": f"@{domain}" if domain else "",
                "auth_mode": "dev",
                "is_domain_account": True,
                "email": user.email,
            }
        )

    email = (user.email or "").strip().lower()
    is_domain_account = bool(domain and email.endswith(f"@{domain}"))

    return success_response(
        {
            "provider": "google-workspace",
            "workspace_domain": domain,
            "workspace_email_pattern": f"@{domain}" if domain else "",
            "auth_mode": "firebase",
            "is_domain_account": is_domain_account,
            "email": email,
        }
    )
