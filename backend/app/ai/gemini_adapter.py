from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai.system_prompt import SYSTEM_PROMPT
from app.config import REPO_ROOT, get_settings
from app.core.errors import AppError, error_response
from app.models.analysis import AnalysisResult
from app.models.dataset import Dataset
from app.models.project import Project
from app.models.topic import Topic
from app.services.ai_guide_service import MockGuideService, build_rule_based_coach
from app.services.secrets import get_gemini_api_key
from app.tools.registry import get_tool, list_tools


@lru_cache
def _question_advisor_prompt(student_level: str = "middle_high") -> str:
    if student_level == "high":
        candidates = [
            REPO_ROOT / "docs" / "question-advisor-prompt-hs.md",
            Path(__file__).with_name("question_advisor_prompt_hs.md"),
        ]
    else:
        candidates = [
            REPO_ROOT / "docs" / "question-advisor-prompt.md",
            Path(__file__).with_name("question_advisor_prompt.md"),
        ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    raise AppError(
        "QUESTION_ADVISOR_PROMPT_MISSING",
        "탐구 질문 조언 프롬프트 파일을 찾을 수 없습니다.",
        "docs/question-advisor-prompt.md 또는 앱 패키지의 prompt 파일이 배포에 포함되어 있는지 확인해 주세요.",
        500,
    )


@lru_cache
def _function_calling_schema_prompt() -> str:
    path = REPO_ROOT / "docs" / "function-calling-schema.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "AI는 registry에 등록된 도구만 사용하고 raw CSV 전체를 prompt에 넣지 않는다."


def _student_level_instruction(student_level: str) -> str:
    labels = {
        "middle": "중학교",
        "high": "고등학교",
        "middle_high": "중·고등학교 공통",
    }
    label = labels.get(student_level, labels["middle_high"])
    if student_level == "middle":
        scope = "도수, 상대도수, 대푯값, 산포도, 그래프 해석 중심으로 안내한다."
    elif student_level == "high":
        scope = "상관계수와 회귀의 직관적 해석까지 허용하되 p-value, 검정, 신뢰구간은 요구하지 않는다."
    else:
        scope = "중학교 개념을 기본으로 삼고, 필요한 경우 고등학교 수준의 상관 해석을 선택적으로 제안한다."
    return f"현재 학생이 선택한 학교급: {label}. {scope} 학생 결론을 대신 쓰지 않는다."


_COMPACT_MAX_DEPTH = 8

_COMPACT_LIST_LIMITS = (200, 50, 20)
_COMPACT_MAX_LIST_ITEMS = _COMPACT_LIST_LIMITS[0]
_COMPACT_MAX_CHARS = 20000
_COMPACT_MAX_STRING_CHARS = 1200

STAT_LABELS_KO = {
    "mean": "평균",
    "median": "중앙값",
    "mode": "최빈값",
    "range": "범위",
    "min": "최솟값",
    "max": "최댓값",
    "variance": "분산",
    "std": "표준편차",
    "q1": "제1사분위수",
    "q3": "제3사분위수",
    "iqr": "사분위범위",
}


_TRUNCATION_INSTRUCTION = (
    'tool_result 안의 "<omitted>", omitted_count, "...<truncated>"는 프롬프트 길이 때문에 '
    "값이 잘려 나간 자리입니다. 잘린 값을 추정하거나 다른 자리의 숫자로 대신 채우지 마세요.\n"
    "확인할 수 없는 부분은 아예 언급하지 말고, 남아 있는 값만 근거로 삼으세요.\n"
)
_TRUNCATION_TOOL_INSTRUCTION = "잘린 부분이 꼭 필요하면 허용된 도구를 다시 호출해 확인하세요.\n"

_GROUP_COMPARISON_INSTRUCTION = (
    "group_comparison은 학생 화면에 보이는 집단별 비교 표와 같은 내용입니다. "
    "집단별 수치를 말할 때는 반드시 이 표의 values에서 해당 집단 이름의 값을 그대로 쓰세요.\n"
    "overall_label(전체) 값은 자료 전체의 수치입니다. 이 값을 특정 집단의 값처럼 쓰지 마세요.\n"
    "표에 없는 집단이나 통계량은 언급하지 마세요.\n"
)


def _group_comparison_table(analysis: AnalysisResult) -> dict | None:
    if analysis.tool_name != "compute_descriptive_stats":
        return None
    result = analysis.result if isinstance(analysis.result, dict) else {}
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        return None

    overall = data.get("overall") if isinstance(data.get("overall"), dict) else None
    overall_label = str(overall.get("group")) if overall else "전체"
    columns = data.get("columns")
    if not isinstance(columns, list) or not columns:
        first = groups[0].get("statistics") if isinstance(groups[0], dict) else None
        columns = list(first) if isinstance(first, dict) else []

    def cell(source: dict | None, column: str, key: str) -> Any:
        statistics = source.get("statistics") if isinstance(source, dict) else None
        column_stats = statistics.get(column) if isinstance(statistics, dict) else None
        return column_stats.get(key) if isinstance(column_stats, dict) else None

    tables = []
    for column in columns:
        column = str(column)
        keys: list[str] = []
        for source in [*groups, overall]:
            statistics = source.get("statistics") if isinstance(source, dict) else None
            column_stats = statistics.get(column) if isinstance(statistics, dict) else None
            if not isinstance(column_stats, dict):
                continue
            for key, value in column_stats.items():
                if isinstance(value, dict):
                    continue
                if key not in keys:
                    keys.append(key)

        sample_sizes = {}
        for group in groups:
            if not isinstance(group, dict):
                continue
            sizes = group.get("sample_sizes")
            size = sizes.get(column) if isinstance(sizes, dict) else group.get("sample_size")
            sample_sizes[str(group.get("group"))] = size
        if overall:
            sample_sizes[overall_label] = overall.get("sample_size")

        rows = [{"statistic": "sample_size", "label": "자료 수", "values": sample_sizes}]
        for key in keys:
            values = {str(group.get("group")): cell(group, column, key) for group in groups if isinstance(group, dict)}
            if overall:
                values[overall_label] = cell(overall, column, key)
            rows.append({"statistic": key, "label": STAT_LABELS_KO.get(key, key), "values": values})
        tables.append({"column": column, "rows": rows})

    return {
        "group_by": data.get("group_by"),
        "groups": [str(group.get("group")) for group in groups if isinstance(group, dict)],
        "overall_label": overall_label,
        "tables": tables,
    }


ANALYSIS_TOOL_NAMES = {
    "compute_descriptive_stats",
    "compute_correlation",
    "plot_bar",
    "plot_histogram",
    "plot_boxplot",
    "plot_scatter",
    "plot_line",
    "plot_frequency_polygon",
    "plot_stem_leaf",
    "plot_pie",
    "create_frequency_table",
    "create_crosstab",
}


class GeminiGuideService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_function_calls: int | None = None,
        client: Any | None = None,
        types_module: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else get_gemini_api_key()
        self.model = model or settings.gemini_model
        self.timeout_seconds = timeout_seconds or settings.gemini_timeout_seconds
        self.max_function_calls = max_function_calls or settings.gemini_max_function_calls
        self._client = client
        self._types = types_module

    def dataset_options(self, datasets: list[Dataset]) -> list[dict]:
        return [
            {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "description": dataset.description,
                "recommended_analyses": [analysis.model_dump() for analysis in dataset.recommended_analyses[:3]],
            }
            for dataset in datasets[:4]
        ]

    def analysis_options(self, dataset: Dataset, student_level: str = "middle_high") -> list[dict]:
        payload = {
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.name,
            "source": dataset.source,
            "student_level": student_level,
            "columns": [column.model_dump() for column in dataset.columns],
            "rule_based_candidates": [analysis.model_dump() for analysis in dataset.recommended_analyses[:5]],
        }
        contents = [
            self._content(
                "user",
                "아래 dataset schema만 보고 학생에게 제안할 분석 방법과 사용할 자료 항목을 고르세요. "
                "raw CSV 행 전체를 요청하거나 추정하지 마세요.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        try:
            response = self._generate(
                contents,
                self._kosis_json_config(self._analysis_recommendation_prompt(student_level), 4096),
            )
            options = self._parse_analysis_options(response)
        except AppError:
            return [analysis.model_dump() for analysis in dataset.recommended_analyses[:3]]
        return options or [analysis.model_dump() for analysis in dataset.recommended_analyses[:3]]

    def column_meanings(
        self,
        dataset: Dataset,
        research_question: str = "",
        student_level: str = "middle_high",
    ) -> list[dict]:
        payload = {
            "dataset_name": dataset.name,
            "source": dataset.source,
            "research_question": research_question,
            "student_level": student_level,
            "columns": [
                {
                    "name": column.name,
                    "display_name": column.display_name,
                    "dtype": column.dtype,
                    "unit": column.unit,
                    "value_examples": [item.value for item in column.value_labels[:5]],
                }
                for column in dataset.columns
            ],
        }
        contents = [
            self._content(
                "user",
                "아래 자료의 항목마다 학생이 이해할 수 있는 한글 표시명과 뜻을 추정하세요.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        try:
            response = self._generate(contents, self._kosis_json_config(self._column_meanings_prompt(), 4096))
            payload = self._loads_json_object(getattr(response, "text", "") or "")
        except AppError:
            return MockGuideService().column_meanings(dataset, research_question, student_level)

        known = {column.name for column in dataset.columns}
        raw_items = payload.get("column_meanings")
        meanings = []
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict) or item.get("name") not in known:
                continue
            unit = str(item.get("unit") or "").strip()
            meanings.append(
                {
                    "name": str(item["name"]),
                    "display_name": str(item.get("display_name") or "").strip(),
                    "description": str(item.get("description") or "").strip(),
                    "unit": unit or None,
                    "confident": bool(item.get("confident", True)),
                }
            )
        if not meanings:
            return MockGuideService().column_meanings(dataset, research_question, student_level)
        return meanings

    def _column_meanings_prompt(self) -> str:
        return (
            "너는 학생이 받은 자료의 항목이 무엇을 뜻하는지 설명해 주는 에이전트이다. "
            "각 항목에 대해 학생이 읽고 바로 이해할 수 있는 한글 표시명과 한 문장 뜻을 만든다. "
            "컬럼명, 자료 유형, 값 예시만 근거로 삼고 없는 사실을 지어내지 않는다. "
            "확실하지 않으면 confident를 false로 두고 뜻을 단정하지 않는다. "
            "단위를 알 수 있으면 unit에 적고, 모르면 null로 둔다. "
            "표시명은 10자 이내의 명사구로 짧게 쓴다. 뜻은 한 문장으로 쓴다. "
            "입력에 없는 항목을 새로 만들지 않는다. name은 입력의 name을 그대로 쓴다. "
            "JSON 객체 하나만 출력한다. "
            'schema: {"column_meanings":[{"name":"","display_name":"","description":"",'
            '"unit":null,"confident":true}]}'
        )

    def derived_variable_suggestions(
        self,
        dataset: Dataset,
        research_question: str = "",
        topic_title: str = "",
        student_level: str = "middle_high",
    ) -> list[dict]:
        payload = {
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.name,
            "source": dataset.source,
            "research_context": {
                "topic_title": topic_title,
                "research_question": research_question,
            },
            "columns": [column.model_dump() for column in dataset.columns],
        }
        contents = [
            self._content(
                "user",
                "아래 탐구 질문과 dataset schema를 함께 보고 분석 전에 만들면 유용할 수 있는 파생변수를 제안하세요. "
                "자료 구조만으로 떠오르는 계산을 나열하지 말고, 탐구 질문을 해결하는 데 필요한 변수가 "
                "이미 있는지, 파생해서 만들 수 있는지 먼저 확인하세요. "
                "raw CSV 행 전체를 요청하거나 추정하지 마세요. 파생변수가 굳이 필요 없거나 "
                "질문에 필요한 변수를 만들 수 없으면 빈 배열을 반환하세요.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        try:
            response = self._generate(
                contents,
                self._kosis_json_config(
                    f"{self._derived_variable_prompt()}\n\n{_student_level_instruction(student_level)}",
                    3072,
                ),
            )
            return self._parse_derived_variable_suggestions(response)
        except AppError:
            from app.services.ai_guide_service import MockGuideService

            return MockGuideService().derived_variable_suggestions(
                dataset,
                research_question=research_question,
                topic_title=topic_title,
                student_level=student_level,
            )

    def question_advice(self, student_input: str, student_level: str = "middle_high") -> dict:
        contents = [
            self._content(
                "user",
                "학생이 자유롭게 적은 탐구 관심사입니다. "
                "developer instruction의 JSON 형식에 맞춰 통계 탐구 질문 후보를 제안하세요.\n\n"
                f"학교급 설정: {student_level}\n"
                f"학생 입력:\n{student_input.strip()}",
            )
        ]
        response = self._generate(contents, self._question_advisor_config(student_level))
        advice = self._parse_question_advice(response)
        advice["metadata"] = {
            "source": "gemini",
            "model": self.model,
            "prompt": "question-advisor",
            "student_level": student_level,
        }
        return advice

    def big_data_question_advice(
        self,
        student_input: str,
        student_level: str = "middle_high",
        evidence: dict | None = None,
    ) -> dict:
        evidence = evidence or {}
        payload = {
            "student_input": student_input.strip(),
            "student_level": student_level,
            "api_evidence": self._compact(evidence),
        }
        contents = [
            self._content(
                "user",
                "학생이 자유롭게 적은 탐구 관심사를 공개 통계/API 자료로 탐구 가능한 질문으로 다듬으세요.\n"
                "아래 api_evidence에 있는 실제 소스 라우팅, 후보 데이터셋, KOSIS 검색 결과만 근거로 사용하세요.\n"
                "없는 API, 없는 통계표, 확인되지 않은 기간·단위는 만들지 말고 '확인 필요'라고 쓰세요.\n"
                "직접 설문이나 우리 반 조사 중심이 아니라, 공식 통계/API 또는 CSV 다운로드 자료를 "
                "사용하는 계획으로 안내하세요.\n"
                "candidate_questions[].data_to_collect.collection_method에는 사용할 API/자료 후보 이름을 적고, "
                "sample_size_hint에는 기간·지역·국가 수 등 집계자료 규모 기준을 적으세요.\n"
                "추가로 data_source_plan 객체를 포함해 recommended_sources, candidate_datasets, kosis_recommendations, "
                "next_data_actions를 학생 눈높이로 요약하세요.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        response = self._generate(contents, self._big_data_question_advisor_config(student_level))
        raw_payload = self._loads_json_object(getattr(response, "text", "") or "")
        advice = self._parse_question_advice(response)
        advice["data_source_plan"] = self._parse_big_data_plan(raw_payload, evidence)
        advice["metadata"] = {
            "source": "gemini",
            "model": self.model,
            "prompt": "big-data-question-advisor",
            "student_level": student_level,
        }
        return advice

    def kosis_search_plan(self, research_question: str, grade_level: str = "middle_high") -> dict:
        contents = [
            self._content(
                "user",
                "학생이 확정한 통계 탐구 질문을 KOSIS 검색 전략으로 바꾸세요.\n"
                "존재하지 않는 통계표를 만들지 말고, 검색어와 필요한 자료 형태만 제안하세요.\n\n"
                f"grade_level: {grade_level}\n"
                f"research_question: {research_question}",
            )
        ]
        response = self._generate(contents, self._kosis_json_config(self._kosis_search_plan_prompt(), 2048))
        plan = self._parse_kosis_search_plan(response, research_question)
        plan["metadata"] = {"source": "gemini", "model": self.model, "prompt": "kosis-search-plan"}
        return plan

    def recommend_external_candidates(self, source_id: str, keywords: list[str]) -> list[dict]:
        payload = {"source_id": source_id, "keywords": keywords}
        contents = [
            self._content(
                "user",
                "너는 통계 자료 지표 추천 에이전트이다. "
                "사용자가 특정 외부 API(source_id)에서 키워드(keywords)에 맞는 자료를 찾고 있다. "
                "해당 기관에서 제공하는 실제 통계표 이름과 고유 코드(dataset_id)를 추론하여 2~3개 추천하라. "
                "단, OECD는 SDMX Developer API URL 자체를 dataset_id로 제공하고, "
                "나머지(ECOS, SGIS, NEIS 등)는 해당 기관의 통계표 코드를 dataset_id에 넣는다. "
                "모르면 임의로 지어내지 말고 1개의 포괄적인 탐색용 데이터셋만 반환하라. "
                "JSON 객체 하나만 출력한다. "
                'schema: {"candidates":[{"dataset_id":"","dataset_title":"","description":""}]}'
                f"\n\n{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        try:
            response = self._generate(contents, self._kosis_json_config("통계 지표 추천 에이전트", 2048))
            data = self._loads_json_object(getattr(response, "text", "") or "")
            return data.get("candidates") or []
        except Exception:
            return []

    def kosis_dataset_recommendations(
        self,
        research_question: str,
        grade_level: str,
        search_plan: dict,
        candidates: list[dict],
    ) -> dict:
        payload = {
            "research_question": research_question,
            "grade_level": grade_level,
            "search_plan": search_plan,
            "kosis_candidates": self._compact(candidates),
        }
        contents = [
            self._content(
                "user",
                "아래 KOSIS 검색 결과와 메타데이터에 근거해서만 자료 후보를 평가하세요.\n"
                "없는 기관, 통계표, 기간, 분류, 단위를 만들지 마세요.\n"
                "search_mode가 student_keyword이면 학생이 직접 입력한 검색어로 KOSIS API가 반환한 "
                "실제 후보만 평가하고, relation_to_research_question에 탐구 질문과 연결되는 이유를 "
                "학생 눈높이로 쓰세요.\n\n"
                f"{json.dumps(payload, ensure_ascii=False)}",
            )
        ]
        response = self._generate(contents, self._kosis_json_config(self._kosis_recommendation_prompt(), 4096))
        recommendations = self._parse_kosis_dataset_recommendations(response, research_question)
        recommendations["metadata"] = {
            "source": "gemini",
            "model": self.model,
            "prompt": "kosis-dataset-recommendation",
        }
        return recommendations

    def interpretation_hints(
        self,
        analysis: AnalysisResult,
        student_level: str = "middle_high",
        prompt_text: str = "",
    ) -> dict:
        contents = [self._content("user", self._prompt_for_hints(analysis, student_level, prompt_text))]
        config = self._generate_config(student_level)
        response = self._generate(contents, config)
        called_tools: list[str] = []

        while function_calls := self._extract_function_calls(response):
            if len(called_tools) + len(function_calls) > self.max_function_calls:
                raise AppError(
                    "GEMINI_TOOL_CALL_LIMIT_EXCEEDED",
                    "Gemini 도구 호출 횟수가 제한을 초과했습니다.",
                    "질문을 더 좁히거나 분석을 다시 실행해 주세요.",
                    502,
                    {"max_function_calls": self.max_function_calls},
                )

            model_content = self._candidate_content(response)
            if model_content is not None:
                contents.append(model_content)

            function_response_parts = []
            for function_call in function_calls:
                name = self._function_call_name(function_call)
                called_tools.append(name)
                tool_result = self._execute_tool_call(function_call)
                function_response_parts.append(
                    self.types.Part.from_function_response(
                        name=name,
                        response={"result": tool_result},
                    )
                )

            contents.append(self.types.Content(role="tool", parts=function_response_parts))
            response = self._generate(contents, config)

        hints = self._parse_hints(response, student_level)
        hints["metadata"] = {
            "source": "gemini",
            "model": self.model,
            "function_call_count": len(called_tools),
            "called_tools": called_tools,
        }
        return hints

    def interpretation_feedback(
        self,
        analysis: AnalysisResult,
        interpretation_text: str,
        student_level: str = "middle_high",
        research_question: str = "",
    ) -> dict:
        prompt = self._prompt_for_interpretation_feedback(
            analysis, interpretation_text, student_level, research_question
        )
        config = self._kosis_json_config(
            f"{SYSTEM_PROMPT}\n\n{_student_level_instruction(student_level)}\n\n"
            "너는 학생이 쓴 해석을 읽고 다시 쓰도록 돕는 피드백 교사이다. "
            "학생의 해석을 대신 고쳐 쓰거나 모범 답안을 제시하지 않는다. "
            "잘한 점과 보완할 점, 다시 생각해 볼 질문만 준다. "
            "최종 답변은 다른 설명 없이 JSON 객체 하나만 출력한다.",
            2048,
        )
        response = self._generate([self._content("user", prompt)], config)
        feedback = self._parse_interpretation_feedback(response, student_level)
        feedback["metadata"] = {"source": "gemini", "model": self.model}
        return feedback

    def coach(
        self,
        project: Project,
        topic: Topic | None = None,
        dataset: Dataset | None = None,
        analysis: AnalysisResult | None = None,
        student_level: str = "middle_high",
        prompt_text: str = "",
    ) -> dict:
        if not analysis:
            coach = build_rule_based_coach(project, topic, dataset, analysis, source="gemini-ready")
            coach["metadata"]["student_level"] = student_level
            coach["metadata"]["note"] = "분석 전 단계는 비용을 줄이기 위해 규칙 기반 코치가 안내합니다."
            return coach

        try:
            hints = self.interpretation_hints(
                analysis,
                student_level=student_level,
                prompt_text=prompt_text or "현재 분석 결과를 바탕으로 다음 탐구 행동을 제안해 주세요.",
            )
        except AppError as exc:
            coach = build_rule_based_coach(project, topic, dataset, analysis, source="gemini-fallback")
            coach["metadata"]["error_code"] = exc.error_code
            coach["metadata"]["note"] = "Gemini 호출이 실패해 규칙 기반 코치가 대신 안내합니다."
            return coach
        next_actions = [*hints.get("observations", [])[:2], *hints.get("questions", [])[:1]]
        return {
            "role_name": "AI 탐구 코치",
            "project_status": project.status,
            "message": "분석 결과를 바탕으로 다음에 확인할 관찰 포인트를 정리했습니다.",
            "next_actions": next_actions,
            "guardrail": hints.get("warning") or "AI 코치는 결론을 대신 쓰지 않습니다.",
            "metadata": hints.get("metadata", {"source": "gemini"}),
        }

    @property
    def types(self) -> Any:
        if self._types is not None:
            return self._types
        try:
            from google.genai import types
        except ImportError as exc:
            raise AppError(
                "GEMINI_DEPENDENCY_MISSING",
                "Gemini SDK가 설치되어 있지 않습니다.",
                '`cd backend && python -m pip install -e ".[gemini]"`를 실행해 주세요.',
                500,
            ) from exc
        self._types = types
        return self._types

    @property
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise AppError(
                "GEMINI_API_KEY_REQUIRED",
                "Gemini API 키가 설정되어 있지 않습니다.",
                "GEMINI_API_KEY를 설정하거나 Secret Manager secret 이름을 지정해 주세요.",
                500,
            )
        try:
            from google import genai
        except ImportError as exc:
            raise AppError(
                "GEMINI_DEPENDENCY_MISSING",
                "Gemini SDK가 설치되어 있지 않습니다.",
                '`cd backend && python -m pip install -e ".[gemini]"`를 실행해 주세요.',
                500,
            ) from exc
        self._client = genai.Client(
            api_key=self.api_key,
            http_options=self.types.HttpOptions(timeout=self.timeout_seconds * 1000),
        )
        return self._client

    def _generate_config(self, student_level: str = "middle_high") -> Any:
        declarations = [
            self.types.FunctionDeclaration(
                name=tool.name,
                description=tool.description_ko,
                parameters_json_schema=tool.input_schema,
            )
            for tool in list_tools()
        ]
        config_kwargs = {
            "system_instruction": (
                f"{SYSTEM_PROMPT}\n\n{_student_level_instruction(student_level)}\n\n"
                "최종 답변은 다른 설명 없이 JSON 객체 하나만 출력한다."
            ),
            "tools": [self.types.Tool(function_declarations=declarations)],
            "automatic_function_calling": self.types.AutomaticFunctionCallingConfig(disable=True),
            "temperature": 0.2,
            "max_output_tokens": 2048,
        }
        if hasattr(self.types, "ThinkingConfig"):
            config_kwargs["thinking_config"] = self.types.ThinkingConfig(thinking_budget=0)
        return self.types.GenerateContentConfig(**config_kwargs)

    def _question_advisor_config(self, student_level: str = "middle_high") -> Any:
        system_instruction = f"{_question_advisor_prompt(student_level)}\n\n{_student_level_instruction(student_level)}"
        config_kwargs = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.25,
            "max_output_tokens": 8192,
        }
        if hasattr(self.types, "ThinkingConfig"):
            config_kwargs["thinking_config"] = self.types.ThinkingConfig(thinking_budget=0)
        return self.types.GenerateContentConfig(**config_kwargs)

    def _big_data_question_advisor_config(self, student_level: str = "middle_high") -> Any:
        system_instruction = (
            f"{_question_advisor_prompt(student_level)}\n\n"
            "추가 모드: 빅데이터/API 활용 계획 조언.\n"
            "학생이 직접 조사할 소규모 설문을 기본값으로 삼지 말고, 제공된 실제 통계 API 후보와 "
            "검색 결과를 바탕으로 탐구 질문을 현실적인 공개 통계 자료 탐구로 정교화한다.\n"
            "반드시 기존 question-advisor JSON schema를 지키고, data_source_plan 객체를 추가한다.\n"
            "data_source_plan schema: {"
            '"recommended_sources":[{"source_id":"","display_name":"","why_suitable":"","access_status":"","auto_fetch_available":false}],'
            '"candidate_datasets":[{"source_id":"","dataset_id":"","dataset_title":"","why_relevant":"","unit":"","period_range":"","access_status":""}],'
            '"kosis_recommendations":[{"dataset_title":"","source_agency":"","relation_to_research_question":"","period_range":"","unit":""}],'
            '"next_data_actions":["학생이 다음에 할 자료 확인 행동"],'
            '"limitations":["자료 해석 주의점"]'
            "}.\n"
            f"{_student_level_instruction(student_level)}"
        )
        config_kwargs = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "max_output_tokens": 8192,
        }
        if hasattr(self.types, "ThinkingConfig"):
            config_kwargs["thinking_config"] = self.types.ThinkingConfig(thinking_budget=0)
        return self.types.GenerateContentConfig(**config_kwargs)

    def _kosis_json_config(self, system_instruction: str, max_output_tokens: int) -> Any:
        config_kwargs = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "max_output_tokens": max_output_tokens,
        }
        if hasattr(self.types, "ThinkingConfig"):
            config_kwargs["thinking_config"] = self.types.ThinkingConfig(thinking_budget=0)
        return self.types.GenerateContentConfig(**config_kwargs)

    def _kosis_search_plan_prompt(self) -> str:
        return (
            "너는 한국 학생의 통계 탐구를 돕는 KOSIS 자료 검색 전략 에이전트이다. "
            "학생의 확정 탐구 질문에서 핵심 변수, 분석 관점, KOSIS 통합검색에 넣을 한국어 검색어를 만든다. "
            "하나의 정답 자료를 확정하지 말고 검색 전략만 만든다. JSON 객체 하나만 출력한다. "
            "schema: {"
            '"topic":"핵심 주제",'
            '"research_question":"학생 질문",'
            '"needed_variables":["필요한 변수"],'
            '"analysis_type":["비교|변화|관계|추정|의사결정"],'
            '"preferred_data_shape":"원하는 자료 형태",'
            '"preferred_dimensions":["연도","지역","성별","연령 등"],'
            '"search_keywords":["KOSIS 검색어 3~5개"]'
            "}"
        )

    def _kosis_recommendation_prompt(self) -> str:
        return (
            "너는 한국 학생의 통계 탐구를 돕는 KOSIS 자료 추천 에이전트이다. "
            "제공된 KOSIS 검색 결과와 메타데이터에 근거해서만 후보를 평가한다. "
            "통계표 이름, 기관, 기간, 분류, 단위는 입력에 있는 값만 사용하고 모르면 '확인 필요'라고 쓴다. "
            "후보 2~5개를 추천하되 하나를 정답처럼 단정하지 않는다. JSON 객체 하나만 출력한다. "
            "schema: {"
            '"student_question":"학생 질문",'
            '"data_need_summary":{"main_variables":[],"comparison_or_analysis_goal":"","preferred_dimensions":[],"preferred_measure":""},'
            '"recommended_datasets":[{'
            '"rank":1,"org_id":"","org_name":"","tbl_id":"","tbl_name":"","dataset_title":"",'
            '"source_agency":"","stat_name":"","fit_score":0,"why_recommended":"",'
            '"relation_to_research_question":"",'
            '"usable_analysis":[],"available_dimensions":[],"available_items":[],"period_range":"",'
            '"unit":"","csv_plan":{"rows_meaning":"","needed_columns":[],"recommended_filter":""},'
            '"student_friendly_summary":"","limitations":[],"cautions":[]'
            "}],"
            '"not_recommended_examples":[],"decision_guide_for_student":[],'
            '"fallback_if_no_good_kosis_data":{"message":"","alternative_plan":""}'
            "}"
        )

    def _analysis_recommendation_prompt(self, student_level: str = "middle_high") -> str:
        return (
            _function_calling_schema_prompt() + "\n\n" + _student_level_instruction(student_level) + "\n\n"
            "추가 역할: 너는 자료 단계에서 학생에게 사용할 자료 항목과 분석 방법을 추천하는 에이전트이다. "
            "반드시 function-calling schema의 registry 도구 중 분석 도구만 추천한다. "
            "tool_args에는 dataset_id를 넣지 않는다. 서버가 나중에 주입한다. "
            "컬럼명은 입력 schema의 name 값을 정확히 사용한다. "
            "표시명(display_name)은 label/description 설명에만 사용한다. "
            "각 후보는 학생이 바로 실행 가능한 tool_name과 tool_args를 가져야 한다. "
            "집단(학급·성별·지역 등)을 나누는 범주형 컬럼이 있으면 집단 사이의 분포 비교를 먼저 추천한다. "
            "즉 plot_boxplot(group_by=범주 컬럼)과 "
            "compute_descriptive_stats(group_by=범주 컬럼)를 상위 후보에 넣는다. "
            "집단 안에서의 상관분석(compute_grouped_correlation, plot_grouped_scatter)은 "
            "분포 차이를 묻는 질문에 답하지 못하므로 상위 후보로 넣지 않는다. "
            "고등학교 이상의 추론, p-value, 회귀식, 가설검정은 추천하지 않는다. "
            "JSON 객체 하나만 출력한다. "
            'schema: {"analysis_options":[{"tool_name":"","label":"","description":"","tool_args":{}}]}'
        )

    def _derived_variable_prompt(self) -> str:
        return (
            "너는 학생의 통계 탐구 자료 전처리를 돕는 에이전트이다. "
            "입력의 research_context를 먼저 읽고 탐구 질문에 필요한 변수를 확인한 뒤, "
            "schema의 컬럼만 사용해 행 단위 파생변수를 제안한다. "
            "단순히 컬럼이 두 개 있다는 이유로 차이/비율을 제안하지 말고, 질문 해결에 직접 필요한 경우만 제안한다. "
            "수식은 반드시 {컬럼명} 형태의 참조와 + - * / ^ &, 괄호, "
            "abs(), round(), sqrt(), left(), right(), mid()만 사용한다. "
            "시계열 전년 대비 변화처럼 행 순서나 그룹 계산이 필요한 수식은 제안하지 않는다. "
            "비율, 차이, 단위 변환, 코드 일부 추출, 문자열 결합처럼 학생이 해석하기 쉬운 파생변수만 추천한다. "
            "파생변수가 분석 질문에 도움이 되지 않거나 필요한 원자료 컬럼이 없으면 빈 배열을 반환한다. "
            "JSON 객체 하나만 출력한다. "
            'schema: {"derived_variables":[{"label":"","new_column":"","display_name":"",'
            '"formula":"","description":"","why":""}]}'
        )

    def _generate(self, contents: list[Any], config: Any) -> Any:
        try:
            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "GEMINI_REQUEST_FAILED",
                "Gemini 응답 생성에 실패했습니다.",
                "API 키, 모델 이름, 네트워크 상태를 확인해 주세요.",
                502,
                {"detail": str(exc)},
            ) from exc

    def _content(self, role: str, text: str) -> Any:
        return self.types.Content(role=role, parts=[self.types.Part.from_text(text=text)])

    def _prompt_for_hints(
        self,
        analysis: AnalysisResult,
        student_level: str,
        prompt_text: str,
    ) -> str:
        tool_result, truncated = self._compact_payload(analysis.result)
        payload = {
            "analysis_result_id": analysis.analysis_result_id,
            "dataset_id": analysis.dataset_id,
            "tool_name": analysis.tool_name,
            "tool_args": analysis.tool_args,
            "tool_result": tool_result,
            "chart_urls": analysis.chart_urls,
            "explanation_hint": analysis.explanation_hint,
        }
        comparison = _group_comparison_table(analysis)
        if comparison:
            payload["group_comparison"] = comparison
        return (
            "아래 분석 결과를 바탕으로 학생이 스스로 결론을 쓰도록 돕는 관찰점과 유도 질문을 만드세요.\n"
            "raw CSV 전체를 요청하거나 추정하지 말고, 제공된 dataset_id와 도구 결과만 사용하세요.\n"
            f"{_GROUP_COMPARISON_INSTRUCTION if comparison else ''}"
            f"{_TRUNCATION_INSTRUCTION + _TRUNCATION_TOOL_INSTRUCTION if truncated else ''}"
            "반드시 먼저 get_dataset_schema를 현재 dataset_id로 호출해 컬럼 구조를 확인하세요.\n"
            "필요할 때만 get_dataset_summary 또는 허용된 통계/차트 도구를 추가 호출하세요.\n"
            "학생의 결론문을 대신 작성하지 마세요.\n"
            "최종 응답은 JSON 객체 하나만 반환하세요.\n"
            "JSON schema: "
            '{"student_level":"middle|high|middle_high","observations":["관찰점"],'
            '"questions":["유도 질문"],"warning":"결론을 대신 쓰지 않는다는 안내"}\n\n'
            f"student_level: {student_level}\n"
            f"student_prompt: {prompt_text or '(없음)'}\n"
            "analysis_result:\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _prompt_for_interpretation_feedback(
        self,
        analysis: AnalysisResult,
        interpretation_text: str,
        student_level: str,
        research_question: str,
    ) -> str:
        tool_result, truncated = self._compact_payload(analysis.result)
        payload = {
            "dataset_id": analysis.dataset_id,
            "tool_name": analysis.tool_name,
            "tool_args": analysis.tool_args,
            "tool_result": tool_result,
            "explanation_hint": analysis.explanation_hint,
        }
        comparison = _group_comparison_table(analysis)
        if comparison:
            payload["group_comparison"] = comparison
        return (
            "학생이 아래 분석 결과를 보고 자기 해석을 썼습니다. 그 해석을 읽고 피드백을 만드세요.\n"
            "학생의 해석을 대신 고쳐 쓰거나 모범 해석을 제시하지 마세요.\n"
            "분석 결과에 실제로 나타난 내용만 근거로 삼고, 없는 수치를 지어내지 마세요.\n"
            f"{_GROUP_COMPARISON_INSTRUCTION if comparison else ''}"
            f"{_TRUNCATION_INSTRUCTION if truncated else ''}"
            "p-value·신뢰구간·가설검정·회귀계수는 언급하지 마세요.\n"
            "인과를 단정한 문장이나 자료 범위를 넘는 일반화가 있으면 improvements에 짚어 주세요.\n"
            "최종 응답은 JSON 객체 하나만 반환하세요.\n"
            "JSON schema: "
            '{"student_level":"middle|high|middle_high","summary":"한 문장 총평",'
            '"strengths":["잘한 점"],"improvements":["보완할 점"],'
            '"questions":["다시 생각해 볼 질문"],"warning":"해석을 대신 쓰지 않는다는 안내"}\n\n'
            f"student_level: {student_level}\n"
            f"research_question: {research_question or '(없음)'}\n"
            f"student_interpretation:\n{interpretation_text}\n\n"
            "analysis_result:\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _compact(
        self,
        value: Any,
        depth: int = 0,
        *,
        marks: list[str] | None = None,
        list_limit: int = _COMPACT_MAX_LIST_ITEMS,
    ) -> Any:

        def recurse(item: Any, next_depth: int) -> Any:
            return self._compact(item, next_depth, marks=marks, list_limit=list_limit)

        def mark(kind: str) -> None:
            if marks is not None:
                marks.append(kind)

        if depth > _COMPACT_MAX_DEPTH:
            mark("depth")
            return "<omitted>"
        if isinstance(value, dict):
            return {str(key): recurse(item, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            compacted = [recurse(item, depth + 1) for item in value[:list_limit]]
            if len(value) > list_limit:
                mark("list")
                compacted.append({"omitted_count": len(value) - list_limit})
            return compacted
        if isinstance(value, str) and len(value) > _COMPACT_MAX_STRING_CHARS:
            mark("string")
            return value[:_COMPACT_MAX_STRING_CHARS] + "...<truncated>"
        return value

    def _compact_payload(self, value: Any) -> tuple[Any, bool]:
        compacted: Any = None
        marks: list[str] = []
        for list_limit in _COMPACT_LIST_LIMITS:
            marks = []
            compacted = self._compact(value, marks=marks, list_limit=list_limit)
            if len(json.dumps(compacted, ensure_ascii=False)) <= _COMPACT_MAX_CHARS:
                break
        else:
            marks.append("budget")
        return compacted, bool(marks)

    def _extract_function_calls(self, response: Any) -> list[Any]:
        function_calls = getattr(response, "function_calls", None)
        if function_calls:
            return list(function_calls)

        calls = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    calls.append(function_call)
        return calls

    def _candidate_content(self, response: Any) -> Any | None:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        return getattr(candidates[0], "content", None)

    def _function_call_name(self, function_call: Any) -> str:
        name = getattr(function_call, "name", None)
        if name:
            return str(name)
        nested = getattr(function_call, "function_call", None)
        nested_name = getattr(nested, "name", None)
        if nested_name:
            return str(nested_name)
        raise AppError(
            "GEMINI_FUNCTION_CALL_INVALID",
            "Gemini가 올바르지 않은 도구 호출을 반환했습니다.",
            "분석을 다시 실행해 주세요.",
            502,
        )

    def _function_call_args(self, function_call: Any) -> dict[str, Any]:
        args = getattr(function_call, "args", None)
        if args is None:
            nested = getattr(function_call, "function_call", None)
            args = getattr(nested, "args", None)
        return dict(args or {})

    def _execute_tool_call(self, function_call: Any) -> dict:
        name = self._function_call_name(function_call)
        tool = get_tool(name)
        if not tool:
            raise AppError(
                "GEMINI_TOOL_NOT_ALLOWED",
                "Gemini가 허용되지 않은 도구를 요청했습니다.",
                "허용된 분석 도구 목록을 확인해 주세요.",
                502,
                {"tool_name": name},
            )
        args = self._function_call_args(function_call)
        return self._run_tool_with_timeout(name, tool.handler, args)

    def _run_tool_with_timeout(
        self,
        name: str,
        handler: Callable[..., dict],
        args: dict[str, Any],
    ) -> dict:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(handler, **args)
        try:
            return future.result(timeout=self.timeout_seconds)
        except TimeoutError:
            return error_response(
                "TOOL_TIMEOUT",
                "AI가 요청한 도구 실행 시간이 초과되었습니다.",
                "더 작은 자료나 단순한 분석을 선택해 주세요.",
                {"function": name, "timeout_seconds": self.timeout_seconds},
            )
        except AppError as exc:
            return error_response(
                exc.error_code,
                exc.error_message_ko,
                exc.suggested_fix,
                {"function": name, **exc.metadata},
            )
        except Exception as exc:
            return error_response(
                "TOOL_EXECUTION_FAILED",
                "AI가 요청한 도구 실행에 실패했습니다.",
                "입력값을 다시 확인해 주세요.",
                {"function": name, "detail": str(exc)},
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _parse_hints(self, response: Any, student_level: str) -> dict:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        observations = self._string_list(payload.get("observations"), limit=5)
        questions = self._string_list(payload.get("questions"), limit=3)
        if not observations or not questions:
            raise AppError(
                "GEMINI_RESPONSE_INVALID",
                "Gemini 응답에서 관찰점과 유도 질문을 읽을 수 없습니다.",
                "다시 시도하거나 규칙 기반 안내 모드로 확인해 주세요.",
                502,
            )
        return {
            "student_level": str(payload.get("student_level") or student_level),
            "observations": observations,
            "questions": questions,
            "warning": str(
                payload.get("warning") or "이 안내는 결론을 대신 작성하지 않으며, 관찰과 질문만 제공합니다."
            ),
        }

    def _parse_interpretation_feedback(self, response: Any, student_level: str) -> dict:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        strengths = self._string_list(payload.get("strengths"), limit=3)
        improvements = self._string_list(payload.get("improvements"), limit=3)
        if not strengths and not improvements:
            raise AppError(
                "GEMINI_RESPONSE_INVALID",
                "Gemini 응답에서 해석 피드백을 읽을 수 없습니다.",
                "잠시 뒤 다시 시도하거나 해석을 조금 더 자세히 적어 주세요.",
                502,
            )
        return {
            "student_level": str(payload.get("student_level") or student_level),
            "summary": str(payload.get("summary") or "해석을 읽고 잘한 점과 보완할 점을 정리했습니다."),
            "strengths": strengths,
            "improvements": improvements,
            "questions": self._string_list(payload.get("questions"), limit=3),
            "warning": str(
                payload.get("warning") or "이 피드백은 해석을 대신 써 주지 않습니다. 고쳐 쓰는 것은 학생이 합니다."
            ),
        }

    def _parse_question_advice(self, response: Any) -> dict:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        raw_candidates = payload.get("candidate_questions")
        if not isinstance(raw_candidates, list):
            raw_candidates = []

        candidates = []
        for item in raw_candidates[:5]:
            if not isinstance(item, dict):
                continue
            data_to_collect = item.get("data_to_collect")
            if not isinstance(data_to_collect, dict):
                data_to_collect = {}
            possible_results = []
            for result in item.get("possible_results") or []:
                if not isinstance(result, dict):
                    continue
                possible_results.append(
                    {
                        "result_pattern": str(result.get("result_pattern") or "").strip(),
                        "interpretation": str(result.get("interpretation") or "").strip(),
                        "decision_support": str(result.get("decision_support") or "").strip(),
                    }
                )
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            candidates.append(
                {
                    "title": str(item.get("title") or "탐구 질문 후보").strip(),
                    "question": question,
                    "type": str(item.get("type") or "탐구").strip(),
                    "why_it_fits_middle_school_statistics": str(
                        item.get("why_it_fits_middle_school_statistics") or ""
                    ).strip(),
                    "data_to_collect": {
                        "target": str(data_to_collect.get("target") or "").strip(),
                        "variables": self._string_list(data_to_collect.get("variables"), limit=8),
                        "collection_method": str(data_to_collect.get("collection_method") or "").strip(),
                        "sample_size_hint": str(data_to_collect.get("sample_size_hint") or "").strip(),
                    },
                    "recommended_analysis": self._string_list(item.get("recommended_analysis"), limit=8),
                    "possible_results": possible_results[:4],
                    "cautions": self._string_list(item.get("cautions"), limit=6),
                    "good_choice_when": str(item.get("good_choice_when") or "").strip(),
                }
            )

        if not candidates:
            raise AppError(
                "GEMINI_RESPONSE_INVALID",
                "Gemini 응답에서 탐구 질문 후보를 읽을 수 없습니다.",
                "입력을 조금 더 구체적으로 적어 다시 시도해 주세요.",
                502,
            )

        return {
            "student_input_summary": str(payload.get("student_input_summary") or "").strip(),
            "overall_advice": str(payload.get("overall_advice") or "").strip(),
            "candidate_questions": candidates,
            "refinement_tips": self._string_list(payload.get("refinement_tips"), limit=6),
            "student_decision_guide": self._string_list(payload.get("student_decision_guide"), limit=6),
            "next_questions_for_student": self._string_list(payload.get("next_questions_for_student"), limit=6),
        }

    def _parse_big_data_plan(self, payload: dict, evidence: dict) -> dict:
        raw_plan = payload.get("data_source_plan")
        if not isinstance(raw_plan, dict):
            raw_plan = {}
        evidence_plan = self._fallback_big_data_plan(evidence)
        recommended_sources = []
        for item in raw_plan.get("recommended_sources") or []:
            if not isinstance(item, dict):
                continue
            recommended_sources.append(
                {
                    "source_id": str(item.get("source_id") or "").strip(),
                    "display_name": str(item.get("display_name") or "").strip(),
                    "why_suitable": str(item.get("why_suitable") or "").strip(),
                    "access_status": str(item.get("access_status") or "").strip(),
                    "auto_fetch_available": bool(item.get("auto_fetch_available")),
                }
            )
        candidate_datasets = []
        for item in raw_plan.get("candidate_datasets") or []:
            if not isinstance(item, dict):
                continue
            candidate_datasets.append(
                {
                    "source_id": str(item.get("source_id") or "").strip(),
                    "dataset_id": str(item.get("dataset_id") or "").strip(),
                    "dataset_title": str(item.get("dataset_title") or "").strip(),
                    "why_relevant": str(item.get("why_relevant") or item.get("description") or "").strip(),
                    "unit": str(item.get("unit") or "").strip(),
                    "period_range": item.get("period_range") or "",
                    "access_status": str(item.get("access_status") or "").strip(),
                }
            )
        kosis_recommendations = []
        for item in raw_plan.get("kosis_recommendations") or []:
            if not isinstance(item, dict):
                continue
            kosis_recommendations.append(
                {
                    "dataset_title": str(item.get("dataset_title") or "").strip(),
                    "source_agency": str(item.get("source_agency") or "").strip(),
                    "relation_to_research_question": str(item.get("relation_to_research_question") or "").strip(),
                    "period_range": str(item.get("period_range") or "").strip(),
                    "unit": str(item.get("unit") or "").strip(),
                }
            )
        return {
            "recommended_sources": recommended_sources[:5] or evidence_plan["recommended_sources"],
            "candidate_datasets": candidate_datasets[:8] or evidence_plan["candidate_datasets"],
            "kosis_recommendations": kosis_recommendations[:5] or evidence_plan["kosis_recommendations"],
            "next_data_actions": self._string_list(raw_plan.get("next_data_actions"), limit=6)
            or evidence_plan["next_data_actions"],
            "limitations": self._string_list(raw_plan.get("limitations"), limit=6) or evidence_plan["limitations"],
        }

    def _fallback_big_data_plan(self, evidence: dict) -> dict:
        route_sources = evidence.get("stat_api", {}).get("route_sources", {})
        stat_search = evidence.get("stat_api", {}).get("search_datasets", {})
        recommended_sources = []
        for item in (route_sources.get("recommended_sources") or [])[:5]:
            access_info = item.get("access_info") or {}
            recommended_sources.append(
                {
                    "source_id": str(item.get("source_id") or ""),
                    "display_name": str(item.get("display_name") or ""),
                    "why_suitable": str(item.get("why_suitable") or ""),
                    "access_status": str(access_info.get("access_status") or ""),
                    "auto_fetch_available": bool(access_info.get("auto_fetch_available")),
                }
            )
        candidate_datasets = []
        for item in (stat_search.get("candidates") or [])[:8]:
            access_info = item.get("access_info") or {}
            candidate_datasets.append(
                {
                    "source_id": str(item.get("source_id") or ""),
                    "dataset_id": str(item.get("dataset_id") or ""),
                    "dataset_title": str(item.get("dataset_title") or ""),
                    "why_relevant": str(item.get("description") or ""),
                    "unit": str(item.get("unit") or ""),
                    "period_range": item.get("period_range") or "",
                    "access_status": str(access_info.get("access_status") or ""),
                }
            )
        kosis_recommendations = []
        kosis_items = (
            evidence.get("kosis", {}).get("recommendations", {}).get("recommended_datasets", [])
            if isinstance(evidence.get("kosis"), dict)
            else []
        )
        for item in kosis_items[:5]:
            kosis_recommendations.append(
                {
                    "dataset_title": str(item.get("dataset_title") or item.get("tbl_name") or ""),
                    "source_agency": str(item.get("source_agency") or item.get("org_name") or ""),
                    "relation_to_research_question": str(
                        item.get("relation_to_research_question") or item.get("why_recommended") or ""
                    ),
                    "period_range": str(item.get("period_range") or ""),
                    "unit": str(item.get("unit") or ""),
                }
            )
        return {
            "recommended_sources": recommended_sources,
            "candidate_datasets": candidate_datasets,
            "kosis_recommendations": kosis_recommendations,
            "next_data_actions": [
                "추천된 자료 후보의 단위와 기간을 확인합니다.",
                "자동 수집 가능한 후보부터 CSV로 가져올 수 있는지 확인합니다.",
                "같은 기준으로 비교할 지역, 국가, 기간을 정합니다.",
            ],
            "limitations": [
                "API 후보가 곧바로 자동 수집 가능하다는 뜻은 아니므로 접근 상태를 확인해야 합니다.",
                "집계자료로 개인 수준의 원인을 단정하지 않습니다.",
            ],
        }

    def _parse_kosis_search_plan(self, response: Any, research_question: str) -> dict:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        keywords = self._string_list(payload.get("search_keywords"), limit=5)
        if not keywords:
            raise AppError(
                "GEMINI_RESPONSE_INVALID",
                "Gemini 응답에서 KOSIS 검색어를 읽을 수 없습니다.",
                "탐구 질문을 조금 더 구체적으로 적어 다시 시도해 주세요.",
                502,
            )
        return {
            "topic": str(payload.get("topic") or "").strip(),
            "research_question": str(payload.get("research_question") or research_question).strip(),
            "needed_variables": self._string_list(payload.get("needed_variables"), limit=8),
            "analysis_type": self._string_list(payload.get("analysis_type"), limit=5),
            "preferred_data_shape": str(payload.get("preferred_data_shape") or "").strip(),
            "preferred_dimensions": self._string_list(payload.get("preferred_dimensions"), limit=8),
            "search_keywords": keywords,
        }

    def _parse_kosis_dataset_recommendations(self, response: Any, research_question: str) -> dict:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        raw_recommendations = payload.get("recommended_datasets")
        if not isinstance(raw_recommendations, list):
            raw_recommendations = []
        recommendations = []
        for index, item in enumerate(raw_recommendations[:5], start=1):
            if not isinstance(item, dict):
                continue
            csv_plan = item.get("csv_plan") if isinstance(item.get("csv_plan"), dict) else {}
            tbl_id = str(item.get("tbl_id") or "").strip()
            org_id = str(item.get("org_id") or "").strip()
            if not tbl_id or not org_id:
                continue
            recommendations.append(
                {
                    "rank": int(item.get("rank") or index),
                    "org_id": org_id,
                    "org_name": str(item.get("org_name") or "").strip(),
                    "tbl_id": tbl_id,
                    "tbl_name": str(item.get("tbl_name") or "").strip(),
                    "dataset_title": str(item.get("dataset_title") or item.get("tbl_name") or "").strip(),
                    "source_agency": str(item.get("source_agency") or item.get("org_name") or "").strip(),
                    "stat_name": str(item.get("stat_name") or "").strip(),
                    "fit_score": int(item.get("fit_score") or 0),
                    "why_recommended": str(item.get("why_recommended") or "").strip(),
                    "relation_to_research_question": str(
                        item.get("relation_to_research_question") or item.get("why_recommended") or ""
                    ).strip(),
                    "usable_analysis": self._string_list(item.get("usable_analysis"), limit=8),
                    "available_dimensions": self._string_list(item.get("available_dimensions"), limit=8),
                    "available_items": self._string_list(item.get("available_items"), limit=8),
                    "period_range": str(item.get("period_range") or "").strip(),
                    "unit": str(item.get("unit") or "").strip(),
                    "csv_plan": {
                        "rows_meaning": str(csv_plan.get("rows_meaning") or "").strip(),
                        "needed_columns": self._string_list(csv_plan.get("needed_columns"), limit=8),
                        "recommended_filter": str(csv_plan.get("recommended_filter") or "").strip(),
                    },
                    "student_friendly_summary": str(item.get("student_friendly_summary") or "").strip(),
                    "limitations": self._string_list(item.get("limitations"), limit=6),
                    "cautions": self._string_list(item.get("cautions"), limit=6),
                }
            )
        return {
            "student_question": str(payload.get("student_question") or research_question).strip(),
            "data_need_summary": payload.get("data_need_summary") or {},
            "recommended_datasets": recommendations,
            "not_recommended_examples": payload.get("not_recommended_examples") or [],
            "decision_guide_for_student": self._string_list(
                payload.get("decision_guide_for_student"),
                limit=6,
            ),
            "fallback_if_no_good_kosis_data": payload.get("fallback_if_no_good_kosis_data") or {},
        }

    def _parse_analysis_options(self, response: Any) -> list[dict]:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        raw_options = payload.get("analysis_options")
        if not isinstance(raw_options, list):
            raw_options = []
        options = []
        for item in raw_options[:5]:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or "").strip()
            tool = get_tool(tool_name)
            if tool_name not in ANALYSIS_TOOL_NAMES or not tool:
                continue
            tool_args = item.get("tool_args") if isinstance(item.get("tool_args"), dict) else {}
            tool_args.pop("dataset_id", None)
            required_args = [key for key in tool.input_schema.get("required", []) if key != "dataset_id"]
            if any(tool_args.get(key) in (None, "", []) for key in required_args):
                continue
            options.append(
                {
                    "tool_name": tool_name,
                    "label": str(item.get("label") or tool.description_ko).strip(),
                    "description": str(item.get("description") or tool.description_ko).strip(),
                    "tool_args": tool_args,
                }
            )
        return options

    def _parse_derived_variable_suggestions(self, response: Any) -> list[dict]:
        payload = self._loads_json_object(getattr(response, "text", "") or "")
        raw_items = payload.get("derived_variables")
        if not isinstance(raw_items, list):
            raw_items = []
        suggestions = []
        for item in raw_items[:4]:
            if not isinstance(item, dict):
                continue
            formula = str(item.get("formula") or "").strip()
            new_column = str(item.get("new_column") or "").strip()
            if not formula or not new_column:
                continue
            suggestions.append(
                {
                    "label": str(item.get("label") or new_column).strip(),
                    "new_column": new_column,
                    "display_name": str(item.get("display_name") or new_column).strip(),
                    "formula": formula,
                    "description": str(item.get("description") or "").strip(),
                    "why": str(item.get("why") or "").strip(),
                }
            )
        return suggestions

    def _loads_json_object(self, text: str) -> dict:
        candidates = [text.strip()]
        fenced_json_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        candidates.extend(match.group(1).strip() for match in re.finditer(fenced_json_pattern, text, re.DOTALL))
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start : end + 1])

        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

        raise AppError(
            "GEMINI_RESPONSE_INVALID",
            "Gemini가 JSON 형식의 안내를 반환하지 않았습니다.",
            "다시 시도하거나 규칙 기반 안내 모드로 확인해 주세요.",
            502,
        )

    def _string_list(self, value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items = [str(item).strip() for item in value if str(item).strip()]
        return items[:limit]
