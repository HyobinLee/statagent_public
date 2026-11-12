from uuid import uuid4

from app.core.errors import AppError
from app.core.time import now_utc
from app.models.analysis import SynthesisResult
from app.models.project import InquiryStep, Project
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.blocking_service import BlockingService
from app.services.dataset_service import DatasetService
from app.services.merge_service import build_merged_dataframe
from app.services.usage_service import UsageService
from app.tools.synthesis_tools import SYNTHESIS_TOOLS

MAX_SYNTHESIS_DATASETS = 5
OBSERVATION_WARNING = "이 안내는 결론을 대신 작성하지 않으며, 관찰과 질문만 제공합니다."


class SynthesisService:
    def __init__(self) -> None:
        self.repo = get_repository()
        self.datasets = DatasetService()
        self.blocking = BlockingService()
        self.usage = UsageService()

    def _get_project(self, project_id: str, user: User) -> Project:
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
                "다른 사용자의 프로젝트에 접근할 수 없습니다.",
                "로그인 계정 또는 관리자 대리 접근 대상을 확인해 주세요.",
                403,
            )
        return project

    def run_synthesis(
        self,
        project_id: str,
        tool_name: str,
        tool_args: dict,
        join_spec: dict,
        user: User,
    ) -> SynthesisResult:
        self.blocking.ensure_not_blocked(user.user_id)
        project = self._get_project(project_id, user)
        if project.status not in {"dataset_chosen", "analysis_done"}:
            raise AppError(
                "WORKFLOW_STEP_VIOLATION",
                "자료를 선택하고 분석을 진행한 뒤에 종합 비교를 실행할 수 있습니다.",
                "자료 선택과 분석 실행을 먼저 완료해 주세요.",
            )

        dataset_ids = [str(item) for item in (join_spec.get("dataset_ids") or [])]
        if len(dataset_ids) < 2:
            raise AppError(
                "MERGE_MINIMUM_DATASETS",
                "종합 비교를 하려면 자료를 2개 이상 선택해야 합니다.",
                "자료 목록에서 하나 더 선택해 주세요.",
            )
        if len(dataset_ids) > MAX_SYNTHESIS_DATASETS:
            raise AppError(
                "MERGE_TOO_MANY_DATASETS",
                f"자료는 최대 {MAX_SYNTHESIS_DATASETS}개까지 종합 비교할 수 있습니다.",
                "종합 비교할 자료 수를 줄여 주세요.",
            )

        allowed_ids = set(project.dataset_ids or [])
        if project.dataset_id:
            allowed_ids.add(project.dataset_id)
        for dataset_id in dataset_ids:
            dataset = self.datasets.get_dataset(dataset_id)
            owned_by_project = dataset_id in allowed_ids
            owned_by_user = bool(dataset.uploaded and dataset.owner_user_id == user.user_id)
            if not (owned_by_project or owned_by_user or dataset.curated):
                raise AppError(
                    "SYNTHESIS_DATASET_NOT_ALLOWED",
                    "이 프로젝트에서 사용할 수 없는 자료가 포함되어 있습니다.",
                    "현재 프로젝트에서 선택했거나 본인이 업로드한 자료만 종합 비교에 사용할 수 있습니다.",
                    403,
                )

        tool = SYNTHESIS_TOOLS.get(tool_name)
        if not tool:
            raise AppError(
                "TOOL_NOT_ALLOWED",
                "허용된 종합 비교 도구가 아닙니다.",
                "종합 비교 도구 목록에서 다시 선택해 주세요.",
            )

        key_column_mappings = {str(k): str(v) for k, v in (join_spec.get("key_column_mappings") or {}).items()}
        time_column_mappings = {str(k): str(v) for k, v in (join_spec.get("time_column_mappings") or {}).items()}
        join_type = str(join_spec.get("join_type") or "inner")
        selected_time_points = join_spec.get("selected_time_points") or None

        merged_df, _source_info, _final_key_name = build_merged_dataframe(
            self.datasets,
            dataset_ids=dataset_ids,
            key_column_mappings=key_column_mappings,
            join_type=join_type,
            time_column_mappings=time_column_mappings or None,
            selected_time_points=selected_time_points,
        )

        tool_result = tool.handler(merged_df, **tool_args)
        self.usage.record_tool_call(user.user_id, tool_name)
        if not tool_result.get("success"):
            raise AppError(
                tool_result.get("error_code", "TOOL_EXECUTION_FAILED"),
                tool_result.get("error_message_ko", "종합 비교 도구 실행에 실패했습니다."),
                tool_result.get("suggested_fix", "입력값을 다시 확인해 주세요."),
            )

        chart_urls: list[str] = []
        data = tool_result.get("data", {})
        if isinstance(data, dict):
            for key in ("png_url", "svg_url"):
                if data.get(key):
                    chart_urls.append(data[key])

        synthesis = SynthesisResult(
            synthesis_result_id=f"synthesis_{uuid4().hex[:12]}",
            project_id=project.project_id,
            dataset_ids=dataset_ids,
            key_column_mappings=key_column_mappings,
            time_column_mappings=time_column_mappings,
            tool_name=tool_name,
            tool_args=tool_args,
            result=tool_result,
            chart_urls=chart_urls,
            explanation_hint=tool_result.get("explanation_hint"),
        )
        self.repo.create_synthesis_result(synthesis)
        if synthesis.synthesis_result_id not in project.synthesis_result_ids:
            project.synthesis_result_ids.append(synthesis.synthesis_result_id)
        project.status = "analysis_done"
        project.steps.append(
            InquiryStep(
                step_id=f"step_{uuid4().hex[:12]}",
                step_type="synthesis_done",
                payload={
                    "synthesis_result_id": synthesis.synthesis_result_id,
                    "tool_name": tool_name,
                    "dataset_ids": dataset_ids,
                    "chart_urls": chart_urls,
                },
            )
        )
        project.updated_at = now_utc()
        self.repo.update_project(project)
        return synthesis

    def list_for_project(self, project_id: str, user: User) -> list[SynthesisResult]:
        project = self._get_project(project_id, user)
        results = []
        for synthesis_id in project.synthesis_result_ids:
            result = self.repo.get_synthesis_result(synthesis_id)
            if result:
                results.append(result)
        return results

    def observations(self, synthesis_result_id: str, user: User) -> dict:
        synthesis = self.repo.get_synthesis_result(synthesis_result_id)
        if not synthesis:
            raise AppError(
                "SYNTHESIS_NOT_FOUND",
                "종합 비교 결과를 찾을 수 없습니다.",
                "종합 비교를 다시 실행해 주세요.",
                404,
            )
        self._get_project(synthesis.project_id, user)

        try:
            from app.services.ai_guide_service import get_guide_service

            service = get_guide_service()
            if hasattr(service, "synthesis_observations"):
                ai_result = service.synthesis_observations(synthesis)
                if isinstance(ai_result, dict) and ai_result.get("observations") and ai_result.get("questions"):
                    ai_result.setdefault("warning", OBSERVATION_WARNING)
                    ai_result.setdefault("metadata", {"source": "ai"})
                    return ai_result
        except Exception:
            pass

        return self._rule_based_observations(synthesis)

    def _rule_based_observations(self, synthesis: SynthesisResult) -> dict:
        data = synthesis.result.get("data") if isinstance(synthesis.result, dict) else {}
        observations: list[str] = []
        questions: list[str] = [
            "두 자료의 시간 범위와 지역 단위가 같은지 먼저 확인해 보세요.",
            "관찰한 차이가 자료의 수집 범위 차이와 관련이 있을지 생각해 보세요.",
        ]

        if isinstance(data, dict) and isinstance(data.get("statistics"), dict):
            for column, stats in data["statistics"].items():
                if not isinstance(stats, dict):
                    continue
                parts = [f"{key}={value}" for key, value in stats.items() if not isinstance(value, (dict, list))]
                if parts:
                    observations.append(f"'{column}' 항목: {', '.join(parts[:4])}")
        elif isinstance(data, dict) and "pearson_correlation" in data:
            coefficient = data.get("pearson_correlation")
            label = data.get("interpretation_label", "")
            suffix = f"({label})" if label else ""
            observations.append(
                f"결합한 자료에서 '{data.get('x_column')}'과(와) '{data.get('y_column')}'의 "
                f"상관계수는 {coefficient}{suffix}입니다."
            )
            if isinstance(coefficient, (int, float)) and abs(coefficient) < 0.3:
                observations.append("상관계수의 크기가 작아 두 항목 사이의 관계가 뚜렷하지 않을 수 있습니다.")
        else:
            observations.append("그래프에서 두 자료의 흐름이 비슷한 시점에 함께 움직이는지 살펴보세요.")

        if not observations:
            observations.append("종합 비교 결과에서 자료별 수치를 직접 비교해 보세요.")

        return {
            "observations": observations[:5],
            "questions": questions[:3],
            "warning": OBSERVATION_WARNING,
            "metadata": {"source": "rule-based", "synthesis_result_id": synthesis.synthesis_result_id},
        }
