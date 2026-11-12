from app.core.errors import AppError
from app.models.user import User
from app.repositories.factory import get_repository


def student_class_id(user: User) -> str:
    if not user.class_id:
        raise AppError(
            "CLASS_NOT_ASSIGNED",
            "학급이 배정되어 있지 않습니다.",
            "선생님께 학급 배정을 요청해 주세요.",
            403,
        )
    return user.class_id


def teaches_class(user: User, class_id: str) -> bool:
    if user.role == "admin":
        return True
    if user.role != "teacher":
        return False
    students = get_repository().list_users()
    return any(
        student.role == "student" and student.class_id == class_id and student.teacher_id == user.user_id
        for student in students
    )


def _forbidden() -> AppError:
    return AppError(
        "SESSION_CLASS_FORBIDDEN",
        "이 학급의 수업 화면에 접근할 수 없습니다.",
        "담당 학급인지 확인해 주세요.",
        403,
    )


def assert_can_read_session(user: User, class_id: str) -> None:
    if user.role == "student":
        if user.class_id != class_id:
            raise _forbidden()
        return
    if not teaches_class(user, class_id):
        raise _forbidden()


def assert_can_control_session(user: User, class_id: str) -> None:
    if user.role == "student" or not teaches_class(user, class_id):
        raise _forbidden()
