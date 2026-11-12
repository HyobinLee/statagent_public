from typing import Literal

UserRole = Literal["admin", "teacher", "student"]

ALLOWED_ROLES: set[str] = {"admin", "teacher", "student"}
