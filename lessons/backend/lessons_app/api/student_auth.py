from app.core.errors import success_response
from fastapi import APIRouter
from pydantic import BaseModel, Field

from lessons_app.services import student_accounts

router = APIRouter(prefix="/api/lessons/student-auth", tags=["lesson-student-auth"])


class StudentLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)
    user_id: str = Field(..., min_length=1, max_length=128)
    pin: str = Field(..., min_length=1, max_length=8)


@router.get("/class/{code}")
def class_roster(code: str) -> dict:
    return success_response(student_accounts.roster_for_code(code))


@router.post("/login")
def student_login(payload: StudentLoginRequest) -> dict:
    user = student_accounts.verify_pin(payload.code, payload.user_id, payload.pin)
    token = student_accounts.create_custom_token(user.user_id)
    return success_response(
        {
            "custom_token": token,
            "user": {
                "user_id": user.user_id,
                "display_name": user.display_name,
                "class_id": user.class_id,
            },
        }
    )
