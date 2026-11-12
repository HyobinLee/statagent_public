import json
import time
from functools import lru_cache
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from app.config import get_settings
from app.core.errors import AppError
from app.core.time import now_utc
from app.models.analysis import AnalysisResult, SynthesisResult
from app.models.project import Project
from app.models.report import Report
from app.models.usage import BlockEvent, UsageEvent
from app.models.user import User

DEV_USERS = [
    {
        "user_id": "admin-001",
        "email": "admin@example.com",
        "role": "admin",
        "display_name": "관리자",
    },
    {
        "user_id": "teacher-001",
        "email": "teacher@example.com",
        "role": "teacher",
        "display_name": "교사 개발 계정",
    },
    {
        "user_id": "student-001",
        "email": "student1@example.com",
        "role": "student",
        "display_name": "학생 개발 계정 1",
        "class_id": "class-001",
        "teacher_id": "teacher-001",
    },
    {
        "user_id": "student-002",
        "email": "student2@example.com",
        "role": "student",
        "display_name": "학생 개발 계정 2",
        "class_id": "class-001",
        "teacher_id": "teacher-001",
    },
]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class LocalJsonRepository:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().local_data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.seed()

    def reset(self) -> None:
        with self._lock:
            for path in self.root.glob("*.json"):
                path.unlink()
            self.seed()

    def seed(self) -> None:
        with self._lock:
            if not self._path("users").exists():
                now = now_utc()
                users = [User(**{**raw, "created_at": now, "updated_at": now}) for raw in DEV_USERS]
                self._write("users", [jsonable_encoder(user) for user in users])
            for collection in [
                "projects",
                "analysis_results",
                "synthesis_results",
                "reports",
                "usage_events",
                "block_events",
                "settings",
            ]:
                if not self._path(collection).exists():
                    self._write(collection, [])

    def _path(self, collection: str) -> Path:
        return self.root / f"{collection}.json"

    def _read(self, collection: str) -> list[dict]:
        path = self._path(collection)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write(self, collection: str, items: list[dict]) -> None:
        path = self._path(collection)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(items, file, ensure_ascii=False, indent=2)
        for attempt in range(5):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def _upsert(self, collection: str, id_field: str, item: dict) -> dict:
        with self._lock:
            items = self._read(collection)
            for index, existing in enumerate(items):
                if existing.get(id_field) == item[id_field]:
                    items[index] = item
                    self._write(collection, items)
                    return item
            items.append(item)
            self._write(collection, items)
            return item

    def list_users(self) -> list[User]:
        return [User(**item) for item in self._read("users")]

    def get_user(self, user_id: str) -> User | None:
        return next((user for user in self.list_users() if user.user_id == user_id), None)

    def get_user_by_email(self, email: str) -> User | None:
        normalized = _normalize_email(email)
        return next((user for user in self.list_users() if _normalize_email(user.email) == normalized), None)

    def upsert_user(self, user: User) -> User:
        user.email = _normalize_email(user.email)
        user.updated_at = now_utc()
        self._upsert("users", "user_id", jsonable_encoder(user))
        return user

    def set_user_blocked(self, user_id: str, blocked: bool, reason: str | None = None) -> User:
        user = self.get_user(user_id)
        if not user:
            raise AppError(
                "USER_NOT_FOUND",
                "사용자를 찾을 수 없습니다.",
                "사용자 목록을 새로고침해 주세요.",
                404,
            )
        user.is_blocked = blocked
        user.block_reason = reason if blocked else None
        if not blocked:
            user.blocked_until = None
        return self.upsert_user(user)

    def create_project(self, project: Project) -> Project:
        if not project.project_id:
            project.project_id = f"project_{uuid4().hex[:12]}"
        self._upsert("projects", "project_id", jsonable_encoder(project))
        return project

    def list_projects(self) -> list[Project]:
        return [Project(**item) for item in self._read("projects")]

    def get_project(self, project_id: str) -> Project | None:
        return next((project for project in self.list_projects() if project.project_id == project_id), None)

    def update_project(self, project: Project) -> Project:
        project.updated_at = now_utc()
        self._upsert("projects", "project_id", jsonable_encoder(project))
        return project

    def _delete(self, collection: str, id_field: str, item_id: str) -> None:
        with self._lock:
            items = [item for item in self._read(collection) if item.get(id_field) != item_id]
            self._write(collection, items)

    def delete_project(self, project_id: str) -> None:
        project = self.get_project(project_id)
        analysis_ids = set(project.analysis_result_ids if project else [])
        if project and project.latest_analysis_result_id:
            analysis_ids.add(project.latest_analysis_result_id)
        synthesis_ids = set(project.synthesis_result_ids if project else [])
        self._delete("projects", "project_id", project_id)
        for analysis_id in analysis_ids:
            self._delete("analysis_results", "analysis_result_id", analysis_id)
        for synthesis_id in synthesis_ids:
            self._delete("synthesis_results", "synthesis_result_id", synthesis_id)
        for report in self.list_reports():
            if report.project_id == project_id:
                self.delete_report(report.report_id)

    def create_analysis_result(self, result: AnalysisResult) -> AnalysisResult:
        self._upsert("analysis_results", "analysis_result_id", jsonable_encoder(result))
        return result

    def update_analysis_result(self, result: AnalysisResult) -> AnalysisResult:
        self._upsert("analysis_results", "analysis_result_id", jsonable_encoder(result))
        return result

    def list_analysis_results(self) -> list[AnalysisResult]:
        return [AnalysisResult(**item) for item in self._read("analysis_results")]

    def get_analysis_result(self, analysis_result_id: str) -> AnalysisResult | None:
        return next(
            (
                result
                for result in [AnalysisResult(**item) for item in self._read("analysis_results")]
                if result.analysis_result_id == analysis_result_id
            ),
            None,
        )

    def create_synthesis_result(self, result: SynthesisResult) -> SynthesisResult:
        self._upsert("synthesis_results", "synthesis_result_id", jsonable_encoder(result))
        return result

    def list_synthesis_results(self) -> list[SynthesisResult]:
        return [SynthesisResult(**item) for item in self._read("synthesis_results")]

    def get_synthesis_result(self, synthesis_result_id: str) -> SynthesisResult | None:
        return next(
            (
                result
                for result in [SynthesisResult(**item) for item in self._read("synthesis_results")]
                if result.synthesis_result_id == synthesis_result_id
            ),
            None,
        )

    def create_report(self, report: Report) -> Report:
        self._upsert("reports", "report_id", jsonable_encoder(report))
        return report

    def list_reports(self) -> list[Report]:
        return [Report(**item) for item in self._read("reports")]

    def get_report(self, report_id: str) -> Report | None:
        return next((report for report in self.list_reports() if report.report_id == report_id), None)

    def update_report(self, report: Report) -> Report:
        self._upsert("reports", "report_id", jsonable_encoder(report))
        return report

    def delete_report(self, report_id: str) -> None:
        self._delete("reports", "report_id", report_id)

    def delete_user(self, user_id: str) -> None:
        self._delete("users", "user_id", user_id)

    def add_usage_event(self, event: UsageEvent) -> UsageEvent:
        self._upsert("usage_events", "event_id", jsonable_encoder(event))
        return event

    def list_usage_events(self) -> list[UsageEvent]:
        return [UsageEvent(**item) for item in self._read("usage_events")]

    def add_block_event(self, event: BlockEvent) -> BlockEvent:
        self._upsert("block_events", "block_event_id", jsonable_encoder(event))
        return event

    def list_block_events(self) -> list[BlockEvent]:
        return [BlockEvent(**item) for item in self._read("block_events")]

    def resolve_block_events(self, user_id: str) -> None:
        events = self.list_block_events()
        for event in events:
            if event.user_id == user_id and event.active:
                event.active = False
                event.resolved_at = now_utc()
        self._write("block_events", [jsonable_encoder(event) for event in events])

    def get_setting(self, key: str) -> dict | None:
        return next((item for item in self._read("settings") if item.get("key") == key), None)

    def upsert_setting(self, key: str, value: dict) -> dict:
        item = {"key": key, "value": value, "updated_at": now_utc().isoformat()}
        self._upsert("settings", "key", item)
        return item

    def list_settings(self) -> list[dict]:
        return self._read("settings")


@lru_cache
def get_repository() -> LocalJsonRepository:
    return LocalJsonRepository()
