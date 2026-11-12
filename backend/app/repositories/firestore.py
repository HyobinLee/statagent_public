from functools import cached_property
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
from app.repositories.local_json import DEV_USERS


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class FirestoreRepository:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.seed()

    @cached_property
    def client(self):
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise AppError(
                "GOOGLE_CLOUD_DEPENDENCY_MISSING",
                "Firestore 연동 패키지가 설치되어 있지 않습니다.",
                '`cd backend && python -m pip install -e ".[google-cloud]"`를 실행해 주세요.',
                500,
            ) from exc

        kwargs = {}
        if self.settings.google_cloud_project:
            kwargs["project"] = self.settings.google_cloud_project
        if self.settings.firestore_database:
            kwargs["database"] = self.settings.firestore_database
        return firestore.Client(**kwargs)

    def _collection_name(self, name: str) -> str:
        prefix = self.settings.firestore_collection_prefix.strip()
        if not prefix:
            return name
        separator = "" if prefix.endswith("_") else "_"
        return f"{prefix}{separator}{name}"

    def _collection(self, name: str):
        return self.client.collection(self._collection_name(name))

    def _list(self, collection: str) -> list[dict]:
        return [snapshot.to_dict() for snapshot in self._collection(collection).stream()]

    def _get(self, collection: str, document_id: str) -> dict | None:
        snapshot = self._collection(collection).document(document_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def _upsert(self, collection: str, id_field: str, item: dict) -> dict:
        self._collection(collection).document(item[id_field]).set(item)
        return item

    def reset(self) -> None:
        if not self.settings.allow_cloud_reset:
            raise AppError(
                "CLOUD_RESET_DISABLED",
                "Cloud 저장소 초기화는 기본적으로 비활성화되어 있습니다.",
                "정말 필요한 개발 환경에서만 ALLOW_CLOUD_RESET=true를 설정해 주세요.",
                403,
            )
        for collection in [
            "users",
            "projects",
            "analysisResults",
            "synthesisResults",
            "reports",
            "usageEvents",
            "blockEvents",
            "settings",
        ]:
            for snapshot in self._collection(collection).stream():
                snapshot.reference.delete()
        self.seed()

    def seed(self) -> None:
        if self._list("users"):
            return
        now = now_utc()
        for raw in DEV_USERS:
            user = User(**{**raw, "created_at": now, "updated_at": now})
            self.upsert_user(user)

    def list_users(self) -> list[User]:
        return [User(**item) for item in self._list("users")]

    def get_user(self, user_id: str) -> User | None:
        item = self._get("users", user_id)
        return User(**item) if item else None

    def get_user_by_email(self, email: str) -> User | None:
        from google.cloud.firestore_v1 import FieldFilter

        normalized = _normalize_email(email)
        snapshots = self._collection("users").where(filter=FieldFilter("email", "==", normalized)).limit(1).stream()
        for snapshot in snapshots:
            return User(**snapshot.to_dict())

        for snapshot in self._collection("users").stream():
            payload = snapshot.to_dict() or {}
            candidate = str(payload.get("email") or "")
            if _normalize_email(candidate) == normalized:
                return User(**payload)
        return None

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
        return [Project(**item) for item in self._list("projects")]

    def get_project(self, project_id: str) -> Project | None:
        item = self._get("projects", project_id)
        return Project(**item) if item else None

    def update_project(self, project: Project) -> Project:
        project.updated_at = now_utc()
        self._upsert("projects", "project_id", jsonable_encoder(project))
        return project

    def delete_project(self, project_id: str) -> None:
        project = self.get_project(project_id)
        analysis_ids = set(project.analysis_result_ids if project else [])
        if project and project.latest_analysis_result_id:
            analysis_ids.add(project.latest_analysis_result_id)
        synthesis_ids = set(project.synthesis_result_ids if project else [])
        self._collection("projects").document(project_id).delete()
        for analysis_id in analysis_ids:
            self._collection("analysisResults").document(analysis_id).delete()
        for synthesis_id in synthesis_ids:
            self._collection("synthesisResults").document(synthesis_id).delete()
        for report in self.list_reports():
            if report.project_id == project_id:
                self.delete_report(report.report_id)

    def create_analysis_result(self, result: AnalysisResult) -> AnalysisResult:
        self._upsert("analysisResults", "analysis_result_id", jsonable_encoder(result))
        return result

    def update_analysis_result(self, result: AnalysisResult) -> AnalysisResult:
        self._upsert("analysisResults", "analysis_result_id", jsonable_encoder(result))
        return result

    def list_analysis_results(self) -> list[AnalysisResult]:
        return [AnalysisResult(**item) for item in self._list("analysisResults")]

    def get_analysis_result(self, analysis_result_id: str) -> AnalysisResult | None:
        item = self._get("analysisResults", analysis_result_id)
        return AnalysisResult(**item) if item else None

    def create_synthesis_result(self, result: SynthesisResult) -> SynthesisResult:
        self._upsert("synthesisResults", "synthesis_result_id", jsonable_encoder(result))
        return result

    def list_synthesis_results(self) -> list[SynthesisResult]:
        return [SynthesisResult(**item) for item in self._list("synthesisResults")]

    def get_synthesis_result(self, synthesis_result_id: str) -> SynthesisResult | None:
        item = self._get("synthesisResults", synthesis_result_id)
        return SynthesisResult(**item) if item else None

    def create_report(self, report: Report) -> Report:
        self._upsert("reports", "report_id", jsonable_encoder(report))
        return report

    def list_reports(self) -> list[Report]:
        return [Report(**item) for item in self._list("reports")]

    def get_report(self, report_id: str) -> Report | None:
        item = self._get("reports", report_id)
        return Report(**item) if item else None

    def update_report(self, report: Report) -> Report:
        self._upsert("reports", "report_id", jsonable_encoder(report))
        return report

    def delete_report(self, report_id: str) -> None:
        self._collection("reports").document(report_id).delete()

    def delete_user(self, user_id: str) -> None:
        self._collection("users").document(user_id).delete()

    def add_usage_event(self, event: UsageEvent) -> UsageEvent:
        self._upsert("usageEvents", "event_id", jsonable_encoder(event))
        return event

    def list_usage_events(self) -> list[UsageEvent]:
        return [
            UsageEvent(**{**(snapshot.to_dict() or {}), "_document_id": snapshot.id})
            for snapshot in self._collection("usageEvents").stream()
        ]

    def add_block_event(self, event: BlockEvent) -> BlockEvent:
        self._upsert("blockEvents", "block_event_id", jsonable_encoder(event))
        return event

    def list_block_events(self) -> list[BlockEvent]:
        return [BlockEvent(**item) for item in self._list("blockEvents")]

    def resolve_block_events(self, user_id: str) -> None:
        for event in self.list_block_events():
            if event.user_id == user_id and event.active:
                event.active = False
                event.resolved_at = now_utc()
                self._upsert("blockEvents", "block_event_id", jsonable_encoder(event))

    def get_setting(self, key: str) -> dict | None:
        return self._get("settings", key)

    def upsert_setting(self, key: str, value: dict) -> dict:
        item = {"key": key, "value": value, "updated_at": now_utc().isoformat()}
        self._upsert("settings", "key", item)
        return item

    def list_settings(self) -> list[dict]:
        return self._list("settings")
