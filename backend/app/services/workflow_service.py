import logging
from collections.abc import Callable
from uuid import uuid4

from app.core.errors import AppError
from app.core.time import now_utc
from app.models.analysis import AnalysisResult
from app.models.project import InquiryStep, Project, normalize_school_level
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.ai_guide_service import MockGuideService, get_guide_service
from app.services.blocking_service import BlockingService
from app.services.dataset_service import DatasetService
from app.services.kosis_service import KosisDatasetService
from app.services.stat_api_service import StatApiService
from app.services.topic_service import TopicService
from app.services.usage_service import UsageService
from app.tools.registry import get_tool

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self) -> None:
        self.repo = get_repository()
        self.topics = TopicService()
        self.datasets = DatasetService()
        self.blocking = BlockingService()
        self.usage = UsageService()

    def create_project(self, owner: User, school_level: str | None = None) -> Project:
        self.blocking.ensure_not_blocked(owner.user_id)
        project = Project(
            project_id=f"project_{uuid4().hex[:12]}",
            owner_user_id=owner.user_id,
            school_level=normalize_school_level(school_level),
        )
        return self.repo.create_project(project)

    def _default_student_level(self) -> str:
        setting = self.repo.get_setting("school_level") or {}
        value = setting.get("value") if isinstance(setting, dict) else {}
        student_level = value.get("school_level") if isinstance(value, dict) else None
        return normalize_school_level(student_level) or "middle_high"

    def _student_level(self, project: Project | None = None) -> str:
        if project is not None and project.school_level:
            return project.school_level
        return self._default_student_level()

    def _share_rules(self) -> list[dict]:
        setting = self.repo.get_setting("share_rules") or {}
        value = setting.get("value") if isinstance(setting, dict) else []
        return value if isinstance(value, list) else []

    def _rule_targets_user(self, rule: dict, user: User) -> bool:
        target_user_ids = set(rule.get("target_user_ids") or [])
        target_group_ids = set(rule.get("target_group_ids") or [])
        if rule.get("mode") == "targeted" and not target_user_ids and not target_group_ids:
            return False
        if not target_user_ids and not target_group_ids:
            return True
        return user.user_id in target_user_ids or bool(user.group_id and user.group_id in target_group_ids)

    def _rule_sources_project(self, rule: dict, project: Project) -> bool:
        source_user_ids = set(rule.get("source_user_ids") or [])
        return not source_user_ids or project.owner_user_id in source_user_ids

    def create_custom_topic_project(
        self,
        owner: User,
        decided_topic: str,
        advisor_input: str = "",
        school_level: str | None = None,
    ) -> Project:
        self.blocking.ensure_not_blocked(owner.user_id)
        cleaned = decided_topic.strip()
        if not cleaned:
            raise AppError(
                "DECIDED_TOPIC_REQUIRED",
                "결정한 탐구 주제를 입력해 주세요.",
                "AI 조언을 바탕으로 실제로 탐구할 질문을 한 문장으로 적어 주세요.",
            )
        if len(cleaned) > 300:
            raise AppError(
                "DECIDED_TOPIC_TOO_LONG",
                "결정한 탐구 주제가 너무 깁니다.",
                "핵심 탐구 질문을 300자 이내로 줄여 주세요.",
            )
        project = Project(
            project_id=f"project_{uuid4().hex[:12]}",
            owner_user_id=owner.user_id,
            school_level=normalize_school_level(school_level),
            topic_id=f"custom_{uuid4().hex[:12]}",
            custom_topic_title=cleaned[:80],
            custom_topic_question=cleaned,
            status="topic_selected",
        )
        self._add_step(
            project,
            "topic_selected",
            {
                "topic_id": project.topic_id,
                "mode": "custom",
                "decided_topic": cleaned,
                "advisor_input": advisor_input.strip()[:1000],
                "school_level": project.school_level,
            },
        )
        return self.repo.create_project(project)

    def list_projects(self, user: User) -> list[Project]:
        projects = self.repo.list_projects()
        if user.role == "student":
            projects = [project for project in projects if project.owner_user_id == user.user_id]
        return sorted(projects, key=lambda project: project.updated_at, reverse=True)

    def get_project(self, project_id: str, user: User) -> Project:
        project = self.repo.get_project(project_id)
        if not project:
            raise AppError(
                "PROJECT_NOT_FOUND",
                "프로젝트를 찾을 수 없습니다.",
                "프로젝트 목록을 새로고침해 주세요.",
                404,
            )
        if user.role == "student" and project.owner_user_id != user.user_id:
            raise AppError(
                "FORBIDDEN",
                "다른 사용자의 프로젝트를 볼 수 없습니다.",
                "로그인 계정 또는 관리자 대리 접근 대상을 확인해 주세요.",
                403,
            )
        return project

    def _add_step(self, project: Project, step_type: str, payload: dict) -> None:
        project.steps.append(InquiryStep(step_id=f"step_{uuid4().hex[:12]}", step_type=step_type, payload=payload))
        project.updated_at = now_utc()

    def _violation(self, project: Project, message: str) -> None:
        self.blocking.record_workflow_bypass(project.owner_user_id, message)
        raise AppError(
            "WORKFLOW_STEP_VIOLATION",
            "정해진 탐구 순서와 맞지 않는 요청입니다.",
            "주제 선택, 자료 선택, 분석 실행 순서로 다시 진행해 주세요.",
        )

    def select_topic(self, project_id: str, topic_id: str, user: User) -> Project:
        project = self.get_project(project_id, user)
        if project.status != "created":
            self._violation(project, "created 상태가 아닌 프로젝트에서 주제 선택")
        topic = self.topics.get_topic(topic_id)
        project.topic_id = topic.topic_id
        project.status = "topic_selected"
        self._add_step(project, "topic_selected", {"topic_id": topic_id})
        return self.repo.update_project(project)

    def select_dataset(self, project_id: str, dataset_id: str, user: User) -> Project:
        project = self.get_project(project_id, user)
        if project.status not in {"topic_selected", "analysis_done"}:
            self._violation(project, "자료 선택 전 상태가 올바르지 않음")
        dataset = self.datasets.get_dataset(dataset_id)
        if project.topic_id and dataset.topic_id != project.topic_id:
            raise AppError(
                "DATASET_TOPIC_MISMATCH",
                "선택한 자료가 현재 주제와 연결되어 있지 않습니다.",
                "주제에 표시된 자료 후보 중 하나를 선택해 주세요.",
            )
        if dataset.uploaded and dataset.owner_user_id and dataset.owner_user_id != user.user_id:
            raise AppError(
                "FORBIDDEN_DATASET",
                "다른 학생이 업로드한 자료는 선택할 수 없습니다.",
                "현재 계정에서 업로드한 CSV를 다시 선택해 주세요.",
                403,
            )
        project.dataset_id = dataset.dataset_id
        if dataset.dataset_id not in project.dataset_ids:
            project.dataset_ids.append(dataset.dataset_id)
        project.status = "dataset_chosen"
        self._add_step(project, "dataset_chosen", {"dataset_id": dataset_id})
        return self.repo.update_project(project)

    def analysis_options(self, project_id: str, user: User) -> list[dict]:
        project = self.get_project(project_id, user)
        if not project.dataset_id:
            self._violation(project, "자료 선택 없이 분석 옵션 조회")
        dataset = self.datasets.get_dataset(project.dataset_id)
        return get_guide_service().analysis_options(dataset, student_level=self._student_level(project))

    def column_meaning_suggestions(self, project_id: str, user: User) -> list[dict]:
        project = self.get_project(project_id, user)
        if not project.dataset_id:
            self._violation(project, "자료 선택 없이 항목 뜻 제안 요청")
        dataset = self.datasets.get_dataset(project.dataset_id)
        service = get_guide_service()
        if not hasattr(service, "column_meanings"):
            return []
        return service.column_meanings(
            dataset,
            research_question=project.custom_topic_question or "",
            student_level=self._student_level(project),
        )

    def apply_column_meanings(self, project_id: str, user: User, meanings: list[dict]) -> dict:
        project = self.get_project(project_id, user)
        if not project.dataset_id:
            self._violation(project, "자료 선택 없이 항목 뜻 저장 시도")
        dataset = self.datasets.apply_column_meanings(project.dataset_id, meanings, owner_user_id=user.user_id)
        return self.datasets.schema(dataset.dataset_id, school_level=project.school_level)

    def derived_variable_suggestions(self, project_id: str, user: User) -> list[dict]:
        project = self.get_project(project_id, user)
        if not project.dataset_id:
            self._violation(project, "자료 선택 없이 파생변수 제안 요청")
        dataset = self.datasets.get_dataset(project.dataset_id)
        topic = None
        if project.topic_id and not project.topic_id.startswith("custom_"):
            topic = self.topics.get_topic(project.topic_id, school_level=project.school_level)
        research_question = project.custom_topic_question or (topic.question if topic else "")
        topic_title = project.custom_topic_title or (topic.title if topic else "")
        service = get_guide_service()
        if hasattr(service, "derived_variable_suggestions"):
            return service.derived_variable_suggestions(
                dataset,
                research_question=research_question,
                topic_title=topic_title,
                student_level=self._student_level(project),
            )
        return []

    def question_advice(
        self,
        user: User,
        student_input: str,
        advice_mode: str = "direct_survey",
        school_level: str | None = None,
    ) -> dict:
        cleaned = student_input.strip()
        if not cleaned:
            raise AppError(
                "QUESTION_ADVICE_INPUT_REQUIRED",
                "탐구하고 싶은 내용을 입력해 주세요.",
                "주제, 현상, 질문 중 떠오르는 내용을 한두 문장으로 적어 주세요.",
            )
        if len(cleaned) > 4000:
            raise AppError(
                "QUESTION_ADVICE_INPUT_TOO_LONG",
                "입력한 내용이 너무 깁니다.",
                "핵심 궁금증을 4,000자 이내로 줄여 주세요.",
            )
        mode = advice_mode if advice_mode in {"direct_survey", "big_data"} else "direct_survey"
        self.blocking.record_ai_call(user.user_id, f"{mode}: {cleaned}")
        student_level = normalize_school_level(school_level) or self._default_student_level()
        if mode == "big_data":
            advice = self._big_data_question_advice(cleaned, student_level)
        else:
            advice = get_guide_service().question_advice(cleaned, student_level=student_level)
            advice["advice_mode"] = "direct_survey"
            advice.setdefault("metadata", {})["advice_mode"] = "direct_survey"
        advice["school_level"] = student_level
        advice.setdefault("metadata", {})["school_level"] = student_level
        return advice

    def _big_data_question_advice(self, cleaned_input: str, student_level: str) -> dict:
        evidence = self._big_data_question_evidence(cleaned_input, student_level)
        service = get_guide_service()
        try:
            advice = service.big_data_question_advice(
                cleaned_input,
                student_level=student_level,
                evidence=evidence,
            )
        except (AttributeError, AppError):
            advice = MockGuideService().big_data_question_advice(
                cleaned_input,
                student_level=student_level,
                evidence=evidence,
            )
        data_source_plan = self._compact_big_data_plan(evidence)
        ai_plan = advice.get("data_source_plan") if isinstance(advice, dict) else None
        if isinstance(ai_plan, dict):
            for key in ("next_data_actions", "limitations"):
                ai_items = [str(item).strip() for item in (ai_plan.get(key) or []) if str(item).strip()][:6]
                if ai_items:
                    data_source_plan[key] = ai_items
        advice["advice_mode"] = "big_data"
        advice["data_source_plan"] = data_source_plan
        advice.setdefault("metadata", {})["advice_mode"] = "big_data"
        advice["metadata"]["api_evidence_checked"] = True
        return advice

    def _evidence_step(
        self,
        evidence: dict,
        source: str,
        error_code: str,
        call: Callable[[], dict],
    ) -> dict | None:
        try:
            return call()
        except AppError as exc:
            evidence["errors"].append({"source": source, "error_code": exc.error_code, "message": exc.error_message_ko})
        except Exception as exc:
            evidence["errors"].append({"source": source, "error_code": error_code, "message": exc.__class__.__name__})
        return None

    def _big_data_question_evidence(self, cleaned_input: str, student_level: str) -> dict:
        evidence: dict = {"stat_api": {}, "kosis": {}, "errors": []}
        stat_service = StatApiService()

        route_result = self._evidence_step(
            evidence,
            "stat_api",
            "STAT_API_ROUTE_FAILED",
            lambda: stat_service.route_sources(
                research_question=cleaned_input,
                grade_level=student_level,
            ),
        )
        if route_result:
            evidence["stat_api"]["route_sources"] = route_result

        source_ids = [
            item.get("source_id")
            for item in (route_result or {}).get("recommended_sources", [])
            if item.get("source_id")
        ][:5]
        search_result = self._evidence_step(
            evidence,
            "stat_api",
            "STAT_API_SEARCH_FAILED",
            lambda: stat_service.search_datasets(
                research_question=cleaned_input,
                grade_level=student_level,
                source_ids=source_ids or None,
            ),
        )
        if search_result:
            evidence["stat_api"]["search_datasets"] = search_result

        kosis_result = self._evidence_step(
            evidence,
            "kosis",
            "KOSIS_SEARCH_FAILED",
            lambda: KosisDatasetService().recommend(
                research_question=cleaned_input,
                grade_level=student_level,
            ),
        )
        if kosis_result:
            evidence["kosis"] = kosis_result
        return evidence

    def _compact_big_data_plan(self, evidence: dict) -> dict:
        route_sources = evidence.get("stat_api", {}).get("route_sources", {})
        stat_search = evidence.get("stat_api", {}).get("search_datasets", {})
        stat_candidates = stat_search.get("candidates") if isinstance(stat_search, dict) else []
        kosis_result = evidence.get("kosis", {})
        kosis_recommendations = (
            kosis_result.get("recommendations", {}).get("recommended_datasets", [])
            if isinstance(kosis_result, dict)
            else []
        )
        recommended_sources = route_sources.get("recommended_sources", []) if isinstance(route_sources, dict) else []
        source_cards = [
            {
                "source_id": item.get("source_id"),
                "display_name": item.get("display_name"),
                "why_suitable": item.get("why_suitable"),
                "search_keywords": item.get("search_keywords", [])[:4],
                "access_status": (item.get("access_info") or {}).get("access_status"),
                "auto_fetch_available": (item.get("access_info") or {}).get("auto_fetch_available"),
                "limitations": item.get("limitations", [])[:3],
            }
            for item in recommended_sources[:5]
        ]
        candidate_cards = [
            {
                "source_id": item.get("source_id"),
                "provider": item.get("provider"),
                "dataset_id": item.get("dataset_id"),
                "dataset_title": item.get("dataset_title"),
                "description": item.get("description"),
                "available_dimensions": item.get("available_dimensions", [])[:5],
                "available_measures": item.get("available_measures", [])[:5],
                "period_range": item.get("period_range"),
                "unit": item.get("unit"),
                "access_status": (item.get("access_info") or {}).get("access_status"),
                "manual_download_url": item.get("manual_download_url"),
            }
            for item in (stat_candidates or [])[:8]
        ]
        kosis_cards = [
            {
                "dataset_title": item.get("dataset_title") or item.get("tbl_name"),
                "source_agency": item.get("source_agency") or item.get("org_name"),
                "stat_name": item.get("stat_name"),
                "relation_to_research_question": item.get("relation_to_research_question"),
                "usable_analysis": item.get("usable_analysis", [])[:4],
                "period_range": item.get("period_range"),
                "unit": item.get("unit"),
                "limitations": item.get("limitations", [])[:3],
            }
            for item in (kosis_recommendations or [])[:5]
        ]
        return {
            "data_need": route_sources.get("data_need", {}) if isinstance(route_sources, dict) else {},
            "recommended_sources": source_cards,
            "candidate_datasets": candidate_cards,
            "kosis_recommendations": kosis_cards,
            "search_notes": [
                "자동 수집 가능 여부는 access_status와 auto_fetch_available을 확인해야 합니다.",
                "KOSIS 후보는 실제 검색 결과가 있을 때만 표시되며, 없거나 키가 없으면 다른 API 후보를 먼저 사용합니다.",
            ],
            "next_data_actions": [
                "추천 자료 후보의 단위와 기간을 확인합니다.",
                "자동 수집 가능 후보는 자료 단계에서 직접 검색 또는 가져오기를 시도합니다.",
                "자동 수집이 어려운 후보는 CSV/XLS 다운로드 후 업로드합니다.",
            ],
            "limitations": [
                "자료 후보가 곧바로 자동 수집 가능하다는 뜻은 아니므로 접근 상태를 확인해야 합니다.",
                "집계자료로 개인 수준의 원인을 단정하지 않습니다.",
            ],
            "errors": evidence.get("errors", []),
        }

    def run_analysis(
        self,
        project_id: str,
        tool_name: str,
        tool_args: dict,
        user: User,
        row_indices: list[int] | None = None,
        filters: dict | None = None,
    ) -> AnalysisResult:
        project = self.get_project(project_id, user)
        if project.status not in {"dataset_chosen", "analysis_done"} or not project.dataset_id:
            self._violation(project, "자료 선택 없이 분석 실행")
        tool = get_tool(tool_name)
        if not tool:
            raise AppError(
                "TOOL_NOT_ALLOWED",
                "허용된 분석 도구가 아닙니다.",
                "분석 방법 목록에서 다시 선택해 주세요.",
            )
        args = dict(tool_args)
        args["dataset_id"] = project.dataset_id
        normalized_row_indices = self.datasets.normalize_analysis_row_indices(project.dataset_id, row_indices)
        normalized_filters = self.datasets.normalize_row_filters(project.dataset_id, filters)
        if normalized_filters:
            filtered_row_indices = self.datasets.row_indices_for_filters(project.dataset_id, normalized_filters)
            if not filtered_row_indices:
                raise AppError(
                    "ANALYSIS_FILTER_NO_ROWS",
                    "필터 조건에 맞는 행이 없습니다.",
                    "범주값이나 표 필터를 다시 선택해 주세요.",
                )
            if normalized_row_indices:
                filtered_set = set(filtered_row_indices)
                normalized_row_indices = [
                    row_index for row_index in normalized_row_indices if row_index in filtered_set
                ]
                if not normalized_row_indices:
                    raise AppError(
                        "ANALYSIS_FILTER_NO_ROWS",
                        "선택한 행과 필터 조건이 함께 맞는 행이 없습니다.",
                        "행 선택을 해제하거나 필터 조건을 다시 선택해 주세요.",
                    )
            else:
                normalized_row_indices = filtered_row_indices
        row_selection = None
        if normalized_row_indices:
            row_selection = {
                "mode": "filtered_rows" if normalized_filters and not row_indices else "selected_rows",
                "base_dataset_id": project.dataset_id,
                "row_indices": normalized_row_indices,
                "row_count": len(normalized_row_indices),
                "row_numbers": [row_index + 1 for row_index in normalized_row_indices],
            }
            if normalized_filters:
                row_selection["filters"] = normalized_filters
        with self.datasets.analysis_row_scope(project.dataset_id, normalized_row_indices):
            tool_result = tool.handler(**args)
        self.usage.record_tool_call(user.user_id, tool_name)
        if not tool_result.get("success"):
            raise AppError(
                tool_result.get("error_code", "TOOL_EXECUTION_FAILED"),
                tool_result.get("error_message_ko", "분석 도구 실행에 실패했습니다."),
                tool_result.get("suggested_fix", "입력값을 다시 확인해 주세요."),
            )
        if row_selection:
            tool_result.setdefault("metadata", {})["row_selection"] = row_selection

        chart_urls = []
        data = tool_result.get("data", {})
        if isinstance(data, dict):
            for key in ("png_url", "svg_url"):
                if data.get(key):
                    chart_urls.append(data[key])
        analysis = AnalysisResult(
            analysis_result_id=f"analysis_{uuid4().hex[:12]}",
            project_id=project.project_id,
            dataset_id=project.dataset_id,
            tool_name=tool_name,
            tool_args=args,
            result=tool_result,
            row_selection=row_selection,
            chart_urls=chart_urls,
            explanation_hint=tool_result.get("explanation_hint"),
        )
        self.repo.create_analysis_result(analysis)
        project.latest_analysis_result_id = analysis.analysis_result_id
        if analysis.analysis_result_id not in project.analysis_result_ids:
            project.analysis_result_ids.append(analysis.analysis_result_id)
        if project.dataset_id and project.dataset_id not in project.dataset_ids:
            project.dataset_ids.append(project.dataset_id)
        project.status = "analysis_done"
        self._add_step(
            project,
            "analysis_done",
            {
                "analysis_result_id": analysis.analysis_result_id,
                "tool_name": tool_name,
                "chart_urls": chart_urls,
                "row_selection": row_selection,
            },
        )
        self.repo.update_project(project)
        return analysis

    def interpretation_hints(self, project_id: str, user: User, prompt_text: str = "") -> dict:
        project = self.get_project(project_id, user)
        if not project.latest_analysis_result_id:
            self._violation(project, "분석 없이 해석 안내 요청")
        self.blocking.record_ai_call(user.user_id, prompt_text)
        analysis = self.repo.get_analysis_result(project.latest_analysis_result_id)
        if not analysis:
            raise AppError(
                "ANALYSIS_NOT_FOUND",
                "분석 결과를 찾을 수 없습니다.",
                "분석을 다시 실행해 주세요.",
                404,
            )
        student_level = self._student_level(project)
        try:
            hints = get_guide_service().interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
            )
            return self._normalize_interpretation_hints(
                hints,
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
            )
        except AppError as exc:
            logger.warning(
                "interpretation_hints AI 호출 실패, 규칙 기반 fallback 사용: %s %s",
                exc.error_code,
                exc.metadata,
            )
            return self._fallback_interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
                error_code=exc.error_code,
            )
        except Exception as exc:
            logger.warning("interpretation_hints 예상치 못한 오류, 규칙 기반 fallback 사용: %r", exc)
            fallback = self._fallback_interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
                error_code="AI_HINTS_UNEXPECTED_ERROR",
            )
            fallback["metadata"]["exception"] = exc.__class__.__name__
            return fallback

    MAX_INTERPRETATION_LENGTH = 1600

    def _project_analysis(self, project: Project, analysis_result_id: str) -> AnalysisResult:
        analysis = self.repo.get_analysis_result(analysis_result_id)
        if not analysis or analysis.project_id != project.project_id:
            raise AppError(
                "ANALYSIS_NOT_FOUND",
                "분석 결과를 찾을 수 없습니다.",
                "분석 목록을 새로고침한 뒤 다시 시도해 주세요.",
                404,
            )
        return analysis

    def _research_question(self, project: Project) -> str:
        if project.custom_topic_question:
            return project.custom_topic_question
        if project.topic_id and not project.topic_id.startswith("custom_"):
            try:
                return self.topics.get_topic(project.topic_id, school_level=project.school_level).question
            except AppError:
                return ""
        return ""

    def interpretation_feedback(
        self,
        project_id: str,
        analysis_result_id: str,
        user: User,
        interpretation_text: str,
    ) -> dict:
        project = self.get_project(project_id, user)
        analysis = self._project_analysis(project, analysis_result_id)
        cleaned = (interpretation_text or "").strip()
        if not cleaned:
            raise AppError(
                "INTERPRETATION_REQUIRED",
                "해석을 먼저 적어 주세요.",
                "분석 결과에서 읽은 내용을 한두 문장으로 적은 뒤 피드백을 요청해 주세요.",
            )
        if len(cleaned) > self.MAX_INTERPRETATION_LENGTH:
            raise AppError(
                "INTERPRETATION_TOO_LONG",
                "해석이 너무 깁니다.",
                f"{self.MAX_INTERPRETATION_LENGTH}자 이내로 줄여 주세요.",
            )
        self.blocking.record_ai_call(user.user_id, f"해석 피드백 요청: {cleaned[:200]}")
        student_level = self._student_level(project)
        research_question = self._research_question(project)
        try:
            feedback = get_guide_service().interpretation_feedback(
                analysis,
                cleaned,
                student_level=student_level,
                research_question=research_question,
            )
            return self._normalize_interpretation_feedback(
                feedback,
                analysis,
                cleaned,
                student_level=student_level,
                research_question=research_question,
            )
        except (AppError, AttributeError) as exc:
            logger.warning("interpretation_feedback AI 호출 실패, 규칙 기반 fallback 사용: %r", exc)
            return self._fallback_interpretation_feedback(
                analysis,
                cleaned,
                student_level=student_level,
                research_question=research_question,
                error_code=getattr(exc, "error_code", "AI_FEEDBACK_UNAVAILABLE"),
            )
        except Exception as exc:
            logger.warning("interpretation_feedback 예상치 못한 오류, 규칙 기반 fallback 사용: %r", exc)
            fallback = self._fallback_interpretation_feedback(
                analysis,
                cleaned,
                student_level=student_level,
                research_question=research_question,
                error_code="AI_FEEDBACK_UNEXPECTED_ERROR",
            )
            fallback["metadata"]["exception"] = exc.__class__.__name__
            return fallback

    def _normalize_interpretation_feedback(
        self,
        feedback: dict,
        analysis: AnalysisResult,
        interpretation_text: str,
        student_level: str,
        research_question: str,
    ) -> dict:
        if not isinstance(feedback, dict):
            return self._fallback_interpretation_feedback(
                analysis,
                interpretation_text,
                student_level=student_level,
                research_question=research_question,
                error_code="AI_FEEDBACK_INVALID_SHAPE",
            )
        strengths = self._hint_list(feedback.get("strengths"), limit=3)
        improvements = self._hint_list(feedback.get("improvements"), limit=3)
        if not strengths and not improvements:
            return self._fallback_interpretation_feedback(
                analysis,
                interpretation_text,
                student_level=student_level,
                research_question=research_question,
                error_code="AI_FEEDBACK_INCOMPLETE",
                note="AI 응답에 잘한 점과 보완할 점이 없어 기본 피드백을 제공했습니다.",
            )
        metadata = feedback.get("metadata") if isinstance(feedback.get("metadata"), dict) else {}
        return {
            **feedback,
            "student_level": str(feedback.get("student_level") or student_level),
            "summary": str(feedback.get("summary") or "해석을 읽고 잘한 점과 보완할 점을 정리했습니다."),
            "strengths": strengths,
            "improvements": improvements,
            "questions": self._hint_list(feedback.get("questions"), limit=3),
            "warning": str(
                feedback.get("warning") or "이 피드백은 해석을 대신 써 주지 않습니다. 고쳐 쓰는 것은 학생이 합니다."
            ),
            "metadata": metadata or {"source": "ai"},
        }

    def _fallback_interpretation_feedback(
        self,
        analysis: AnalysisResult,
        interpretation_text: str,
        student_level: str,
        research_question: str,
        error_code: str = "AI_FEEDBACK_UNAVAILABLE",
        note: str = "AI 응답 생성에 실패해 규칙 기반 피드백을 대신 제공했습니다.",
    ) -> dict:
        fallback = MockGuideService().interpretation_feedback(
            analysis,
            interpretation_text,
            student_level=student_level,
            research_question=research_question,
        )
        fallback["metadata"] = {
            "source": "rule-based-fallback",
            "error_code": error_code,
            "note": note,
        }
        return fallback

    def save_interpretation(
        self,
        project_id: str,
        analysis_result_id: str,
        user: User,
        interpretation_text: str,
    ) -> AnalysisResult:
        project = self.get_project(project_id, user)
        if user.role == "student" and project.owner_user_id != user.user_id:
            raise AppError(
                "FORBIDDEN",
                "다른 사용자의 분석 해석을 저장할 수 없습니다.",
                "현재 계정을 확인해 주세요.",
                403,
            )
        analysis = self._project_analysis(project, analysis_result_id)
        cleaned = (interpretation_text or "").strip()
        if len(cleaned) > self.MAX_INTERPRETATION_LENGTH:
            raise AppError(
                "INTERPRETATION_TOO_LONG",
                "해석이 너무 깁니다.",
                f"{self.MAX_INTERPRETATION_LENGTH}자 이내로 줄여 주세요.",
            )
        analysis.interpretation = cleaned
        analysis.interpretation_updated_at = now_utc()
        self.repo.update_analysis_result(analysis)
        self._add_step(
            project,
            "interpretation_saved",
            {"analysis_result_id": analysis.analysis_result_id, "length": len(cleaned)},
        )
        self.repo.update_project(project)
        return analysis

    def _normalize_interpretation_hints(
        self,
        hints: dict,
        analysis: AnalysisResult,
        student_level: str,
        prompt_text: str = "",
    ) -> dict:
        if not isinstance(hints, dict):
            return self._fallback_interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
                error_code="AI_HINTS_INVALID_SHAPE",
            )

        observations = self._hint_list(hints.get("observations"), limit=5)
        questions = self._hint_list(hints.get("questions"), limit=3)
        if not observations or not questions:
            fallback = self._fallback_interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text,
                error_code="AI_HINTS_INCOMPLETE",
                note="AI 응답에 관찰점 또는 유도 질문이 부족해 기본 안내를 제공했습니다.",
            )
            metadata = hints.get("metadata")
            if isinstance(metadata, dict):
                fallback["metadata"]["original_source"] = metadata.get("source")
            return fallback

        metadata = hints.get("metadata") if isinstance(hints.get("metadata"), dict) else {}
        return {
            **hints,
            "student_level": str(hints.get("student_level") or student_level),
            "observations": observations,
            "questions": questions,
            "warning": str(hints.get("warning") or "이 안내는 결론을 대신 작성하지 않으며, 관찰과 질문만 제공합니다."),
            "metadata": metadata or {"source": "ai"},
        }

    def _fallback_interpretation_hints(
        self,
        analysis: AnalysisResult,
        student_level: str,
        prompt_text: str = "",
        error_code: str = "AI_HINTS_UNAVAILABLE",
        note: str = "AI 응답 생성에 실패해 규칙 기반 관찰점과 유도 질문을 대신 제공했습니다.",
    ) -> dict:
        fallback = MockGuideService().interpretation_hints(
            analysis,
            student_level=student_level,
            prompt_text=prompt_text,
        )
        fallback["metadata"] = {
            "source": "rule-based-fallback",
            "error_code": error_code,
            "note": note,
        }
        return fallback

    def _hint_list(self, value: object, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
            if len(items) >= limit:
                break
        return items

    def ai_coach(self, project_id: str, user: User, prompt_text: str = "") -> dict:
        project = self.get_project(project_id, user)
        self.blocking.record_ai_call(
            user.user_id,
            prompt_text or f"AI 탐구 코치 요청: {project.status}",
        )
        topic = (
            self.topics.get_topic(project.topic_id, school_level=project.school_level)
            if project.topic_id and not project.topic_id.startswith("custom_")
            else None
        )
        dataset = self.datasets.get_dataset(project.dataset_id) if project.dataset_id else None
        analysis = None
        if project.latest_analysis_result_id:
            analysis = self.repo.get_analysis_result(project.latest_analysis_result_id)
        return get_guide_service().coach(
            project,
            topic=topic,
            dataset=dataset,
            analysis=analysis,
            student_level=self._student_level(project),
            prompt_text=prompt_text,
        )

    def stop(self, project_id: str, user: User) -> Project:
        project = self.get_project(project_id, user)
        if project.status != "analysis_done":
            self._violation(project, "중단 가능한 상태가 아님")
        project.status = "stopped"
        return self.repo.update_project(project)

    def delete_project(self, project_id: str, user: User) -> None:
        project = self.get_project(project_id, user)
        if user.role == "student" and project.owner_user_id != user.user_id:
            raise AppError(
                "FORBIDDEN",
                "다른 사용자의 프로젝트를 삭제할 수 없습니다.",
                "현재 계정을 확인해 주세요.",
                403,
            )
        dataset_ids = set(project.dataset_ids or [])
        if project.dataset_id:
            dataset_ids.add(project.dataset_id)
        other_projects = [item for item in self.repo.list_projects() if item.project_id != project.project_id]
        for dataset_id in dataset_ids:
            referenced_elsewhere = any(
                dataset_id in set(item.dataset_ids or []) or item.dataset_id == dataset_id for item in other_projects
            )
            if referenced_elsewhere:
                continue
            try:
                DatasetService().delete_uploaded_dataset(dataset_id, owner_user_id=project.owner_user_id)
            except AppError as exc:
                if exc.error_code != "DATASET_NOT_FOUND":
                    raise
        self.repo.delete_project(project_id)

    def analyses(self, project_id: str, user: User) -> list[AnalysisResult]:
        project = self.get_project(project_id, user)
        analysis_ids = project.analysis_result_ids or (
            [project.latest_analysis_result_id] if project.latest_analysis_result_id else []
        )
        results = []
        for analysis_id in analysis_ids:
            analysis = self.repo.get_analysis_result(analysis_id)
            if analysis:
                results.append(analysis)
        return results

    def shared_artifacts(self, user: User) -> list[dict]:
        artifacts: list[dict] = []
        projects = self.repo.list_projects()
        reports = {report.project_id: report for report in self.repo.list_reports()}
        for rule in self._share_rules():
            if not self._rule_targets_user(rule, user):
                continue
            stage = rule.get("stage")
            rows = []
            for project in projects:
                if user.role == "student" and project.owner_user_id == user.user_id:
                    continue
                if not self._rule_sources_project(rule, project):
                    continue
                if stage == "dataset":
                    dataset_ids = project.dataset_ids or ([project.dataset_id] if project.dataset_id else [])
                    for dataset_id in dataset_ids:
                        try:
                            dataset = self.datasets.get_dataset(dataset_id)
                        except AppError:
                            continue
                        rows.append(
                            {
                                "stage": "dataset",
                                "project_id": project.project_id,
                                "owner_user_id": project.owner_user_id,
                                "dataset_id": dataset.dataset_id,
                                "title": dataset.name,
                                "description": dataset.description,
                                "source": dataset.source,
                                "can_use_from_analysis": True,
                            }
                        )
                elif stage == "topic" and project.topic_id:
                    rows.append(
                        {
                            "stage": "topic",
                            "project_id": project.project_id,
                            "owner_user_id": project.owner_user_id,
                            "topic_id": project.topic_id,
                            "title": self._project_topic_title(project),
                            "description": project.custom_topic_question or "",
                        }
                    )
                elif stage == "analysis" and project.latest_analysis_result_id:
                    analysis = self.repo.get_analysis_result(project.latest_analysis_result_id)
                    if analysis:
                        rows.append(
                            {
                                "stage": "analysis",
                                "project_id": project.project_id,
                                "owner_user_id": project.owner_user_id,
                                "analysis_result_id": analysis.analysis_result_id,
                                "title": analysis.tool_name,
                                "description": analysis.explanation_hint or "",
                            }
                        )
                elif stage in {"conclusion", "report"} and project.project_id in reports:
                    report = reports[project.project_id]
                    rows.append(
                        {
                            "stage": stage,
                            "project_id": project.project_id,
                            "owner_user_id": project.owner_user_id,
                            "report_id": report.report_id,
                            "title": report.topic_title,
                            "description": report.conclusion_text,
                        }
                    )
            if rule.get("mode") == "sample":
                rows = rows[:3]
            artifacts.extend(rows)
        return artifacts

    def _project_topic_title(self, project: Project) -> str:
        if project.custom_topic_question:
            return project.custom_topic_title or project.custom_topic_question
        if not project.topic_id:
            return "탐구 주제"
        try:
            return self.topics.get_topic(project.topic_id).title
        except AppError:
            return project.topic_id

    def use_shared_dataset(
        self,
        project_id: str,
        dataset_id: str,
        user: User,
        source_project_id: str | None = None,
    ) -> Project:
        project = self.get_project(project_id, user)
        if project.status not in {"created", "topic_selected", "analysis_done"}:
            self._violation(project, "공유 자료를 붙일 수 없는 프로젝트 상태")
        allowed = [
            artifact
            for artifact in self.shared_artifacts(user)
            if artifact.get("stage") == "dataset" and artifact.get("dataset_id") == dataset_id
        ]
        if source_project_id:
            allowed = [artifact for artifact in allowed if artifact.get("project_id") == source_project_id]
        if not allowed:
            raise AppError(
                "SHARED_DATASET_NOT_ALLOWED",
                "공유받은 자료가 아니거나 사용할 권한이 없습니다.",
                "교사가 공유 설정의 대상과 자료 단계를 확인해야 합니다.",
                403,
            )
        source_project = self.repo.get_project(allowed[0]["project_id"])
        if source_project and not project.topic_id:
            project.topic_id = source_project.topic_id
            project.custom_topic_title = source_project.custom_topic_title
            project.custom_topic_question = source_project.custom_topic_question
        project.dataset_id = dataset_id
        if dataset_id not in project.dataset_ids:
            project.dataset_ids.append(dataset_id)
        project.status = "dataset_chosen"
        self._add_step(
            project,
            "dataset_chosen",
            {"dataset_id": dataset_id, "shared_from_project_id": allowed[0]["project_id"]},
        )
        return self.repo.update_project(project)
