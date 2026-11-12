from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import require_any_role
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.blocking_service import BlockingService

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


class ClassAssignmentRequest(BaseModel):
    class_id: str = Field(..., min_length=1, max_length=80)
    student_ids: list[str] = Field(default_factory=list)


class GroupAssignmentRequest(BaseModel):
    group_id: str = Field(..., min_length=1, max_length=80)
    student_ids: list[str] = Field(default_factory=list)


class TeacherHierarchyRouteRequest(BaseModel):
    class_id: str = Field(..., min_length=1, max_length=80)
    student_ids: list[str] = Field(default_factory=list)


class SchoolLevelRequest(BaseModel):
    school_level: str = Field(..., pattern="^(middle|high|middle_high)$")


class TopicTemplateRequest(BaseModel):
    template_id: str | None = Field(default=None, max_length=80)
    title: str = Field(..., min_length=1, max_length=120)
    question: str = Field(..., min_length=1, max_length=300)
    level: str = Field(default="middle_high", pattern="^(middle|high|middle_high)$")
    visible: bool = True


class ShareRuleRequest(BaseModel):
    stage: str = Field(..., pattern="^(topic|dataset|analysis|conclusion|report)$")
    mode: str = Field(..., pattern="^(all|sample|teacher_selected|targeted)$")
    source_user_ids: list[str] = Field(default_factory=list)
    target_user_ids: list[str] = Field(default_factory=list)
    target_group_ids: list[str] = Field(default_factory=list)


def _setting_value(key: str, default):
    item = get_repository().get_setting(key)
    return item.get("value") if item else default


@router.get("/dashboard")
def dashboard(user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    repo = get_repository()
    projects = repo.list_projects()
    reports = repo.list_reports()
    users = repo.list_users()
    teachers_by_id = {item.user_id: item for item in users if item.role == "teacher"}
    blocked_users = [item for item in users if item.is_blocked]
    data = {
        "viewer": user.model_dump(mode="json"),
        "summary": {
            "project_count": len(projects),
            "submitted_report_count": len(reports),
            "blocked_user_count": len(blocked_users),
        },
        "teachers": [
            {
                "user_id": teacher.user_id,
                "display_name": teacher.display_name,
                "email": teacher.email,
            }
            for teacher in sorted(teachers_by_id.values(), key=lambda item: item.display_name)
        ],
        "students": [
            {
                "user_id": student.user_id,
                "display_name": student.display_name,
                "class_id": student.class_id,
                "teacher_id": student.teacher_id,
                "teacher_name": teachers_by_id.get(student.teacher_id).display_name
                if student.teacher_id and teachers_by_id.get(student.teacher_id)
                else None,
                "group_id": student.group_id,
                "is_blocked": student.is_blocked,
                "latest_project_status": next(
                    (
                        project.status
                        for project in sorted(projects, key=lambda item: item.updated_at, reverse=True)
                        if project.owner_user_id == student.user_id
                    ),
                    "not_started",
                ),
            }
            for student in users
            if student.role == "student"
        ],
        "reports": [report.model_dump(mode="json") for report in reports],
        "blocked_users": [blocked.model_dump(mode="json") for blocked in blocked_users],
        "classes": _classes_from_users(users),
        "groups": _groups_from_users(users),
        "school_level": _setting_value("school_level", {"school_level": "middle_high"}).get("school_level"),
        "topic_templates": _setting_value("topic_templates", []),
        "share_rules": _setting_value("share_rules", []),
    }
    return success_response(data, {"viewer": user.user_id})


def _classes_from_users(users: list[User]) -> list[dict]:
    teachers_by_id = {user.user_id: user for user in users if user.role == "teacher"}
    class_ids = sorted({user.class_id for user in users if user.class_id})
    return [
        {
            "class_id": class_id,
            "name": class_id,
            "member_count": len([user for user in users if user.class_id == class_id]),
            "teacher_ids": sorted(
                {
                    user.teacher_id
                    for user in users
                    if user.role == "student" and user.class_id == class_id and user.teacher_id
                }
            ),
            "teacher_names": [
                teachers_by_id[teacher_id].display_name
                for teacher_id in sorted(
                    {
                        user.teacher_id
                        for user in users
                        if (user.role == "student" and user.class_id == class_id and user.teacher_id in teachers_by_id)
                    }
                )
            ],
        }
        for class_id in class_ids
    ]


def _groups_from_users(users: list[User]) -> list[dict]:
    group_ids = sorted({user.group_id for user in users if user.group_id})
    return [
        {
            "group_id": group_id,
            "name": group_id,
            "member_count": len([user for user in users if user.group_id == group_id]),
        }
        for group_id in group_ids
    ]


@router.get("/students")
def students(_user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    users = [user for user in get_repository().list_users() if user.role == "student"]
    return success_response([user.model_dump(mode="json") for user in users], {"count": len(users)})


@router.get("/reports")
def teacher_reports(_user: User = Depends(require_any_role(["teacher", "admin"]))) -> dict:
    reports = get_repository().list_reports()
    return success_response([report.model_dump(mode="json") for report in reports], {"count": len(reports)})


@router.post("/classes")
def assign_class(
    payload: ClassAssignmentRequest,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    repo = get_repository()
    updated = []
    for student_id in payload.student_ids:
        student = repo.get_user(student_id)
        if student and student.role == "student":
            student.class_id = payload.class_id
            updated.append(repo.upsert_user(student).model_dump(mode="json"))
    return success_response({"class_id": payload.class_id, "students": updated})


@router.post("/groups")
def assign_group(
    payload: GroupAssignmentRequest,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    repo = get_repository()
    updated = []
    for student_id in payload.student_ids:
        student = repo.get_user(student_id)
        if student and student.role == "student":
            student.group_id = payload.group_id
            updated.append(repo.upsert_user(student).model_dump(mode="json"))
    return success_response({"group_id": payload.group_id, "students": updated})


@router.post("/hierarchy-route")
def route_students_to_teacher(
    payload: TeacherHierarchyRouteRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    repo = get_repository()
    teacher_id = user.user_id
    if user.role == "admin":
        teacher_id = "teacher-001"
        teacher = repo.get_user(teacher_id)
        if not teacher or teacher.role != "teacher":
            teacher_id = next((item.user_id for item in repo.list_users() if item.role == "teacher"), user.user_id)
    updated = []
    for student_id in payload.student_ids:
        student = repo.get_user(student_id)
        if student and student.role == "student":
            student.class_id = payload.class_id
            student.teacher_id = teacher_id
            updated.append(repo.upsert_user(student).model_dump(mode="json"))
    return success_response({"class_id": payload.class_id, "teacher_id": teacher_id, "students": updated})


@router.post("/school-level")
def set_school_level(
    payload: SchoolLevelRequest,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    item = get_repository().upsert_setting("school_level", {"school_level": payload.school_level})
    return success_response(item["value"])


@router.post("/topic-templates")
def save_topic_template(
    payload: TopicTemplateRequest,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    templates = list(_setting_value("topic_templates", []))
    template = payload.model_dump()
    template["template_id"] = template["template_id"] or f"template_{len(templates) + 1:03d}"
    templates = [item for item in templates if item.get("template_id") != template["template_id"]]
    templates.append(template)
    get_repository().upsert_setting("topic_templates", templates)
    return success_response(template, {"count": len(templates)})


@router.post("/share-rules")
def save_share_rule(
    payload: ShareRuleRequest,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    rules = list(_setting_value("share_rules", []))
    rule = payload.model_dump()
    rule["rule_id"] = f"share_{len(rules) + 1:03d}"
    rules.append(rule)
    get_repository().upsert_setting("share_rules", rules)
    return success_response(rule, {"count": len(rules)})


@router.post("/students/{user_id}/unblock")
def unblock_student(
    user_id: str,
    _user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    BlockingService().unblock_user(user_id)
    unblocked = get_repository().get_user(user_id)
    return success_response(unblocked.model_dump(mode="json") if unblocked else {"user_id": user_id})
