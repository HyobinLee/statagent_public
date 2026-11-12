import re

from app.config import get_settings
from app.models.analysis import AnalysisResult
from app.models.dataset import Dataset
from app.models.project import Project
from app.models.topic import Topic


def build_rule_based_coach(
    project: Project,
    topic: Topic | None = None,
    dataset: Dataset | None = None,
    analysis: AnalysisResult | None = None,
    source: str = "mock",
) -> dict:
    guardrail = "AI 코치는 결론을 대신 쓰지 않고, 다음에 확인할 관찰 포인트만 제안합니다."
    if project.status == "created":
        message = (
            "먼저 스스로 궁금한 질문을 고르세요. 좋은 탐구 주제는 숫자로 비교하거나 변화 흐름을 볼 수 있어야 합니다."
        )
        next_actions = [
            "카드의 질문을 읽고 가장 설명해 보고 싶은 주제를 고르기",
            "그래프나 통계량으로 확인할 수 있는 주제인지 생각하기",
        ]
    elif project.status == "topic_selected":
        title = topic.title if topic else (project.custom_topic_title or "선택한 주제")
        message = f"{title}에 맞는 자료를 고르는 단계입니다. 자료 설명, 기간, 항목을 먼저 비교해 보세요."
        next_actions = ["자료의 기간과 단위를 확인하기", "질문에 직접 연결되는 수치형 항목이 있는지 보기"]
        if topic and topic.guidance:
            next_actions.insert(0, topic.guidance)
    elif project.status == "dataset_chosen":
        name = dataset.name if dataset else "선택한 자료"
        message = f"{name}로 분석 방법을 고르는 단계입니다. 시간 흐름은 선그래프, 두 변수 관계는 산점도가 잘 맞습니다."
        next_actions = ["질문이 변화, 비교, 관계 중 어디에 가까운지 고르기", "분석 전 컬럼의 유형과 요약값 확인하기"]
    elif project.status == "analysis_done" and analysis:
        message = "분석 결과를 바로 결론으로 옮기기 전에, 눈에 보이는 사실과 추측을 분리해 보세요."
        next_actions = [
            "가장 큰 값과 가장 작은 값 찾기",
            "전체 흐름이나 튀는 값을 한 문장으로 적기",
            "자료만으로 말할 수 없는 원인 추측은 따로 표시하기",
        ]
    elif project.status == "conclusion_submitted":
        message = "보고서 제출이 끝났습니다. 교사 피드백을 받으면 관찰 근거가 충분한지 다시 점검해 보세요."
        next_actions = ["피드백 확인하기", "수정할 때는 숫자 근거와 그래프 관찰을 함께 적기"]
    elif project.status == "stopped":
        message = "프로젝트가 중단되었습니다. 다시 시작하려면 새 프로젝트를 만들고 더 작은 질문부터 선택해 보세요."
        next_actions = ["새 프로젝트 시작하기", "분석 가능한 자료가 있는 주제 선택하기"]
    else:
        message = "현재 단계에서 다음에 확인할 자료와 숫자 근거를 차근차근 살펴보세요."
        next_actions = ["현재 선택을 다시 확인하기", "다음 단계로 넘어가기 전에 근거가 충분한지 점검하기"]

    return {
        "role_name": "AI 탐구 코치",
        "project_status": project.status,
        "message": message,
        "next_actions": next_actions,
        "guardrail": guardrail,
        "metadata": {"source": source},
    }


class MockGuideService:
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
        _ = student_level
        return [analysis.model_dump() for analysis in dataset.recommended_analyses[:3]]

    COLUMN_NAME_HINTS = {
        "score": "점수",
        "grade": "성적",
        "class": "학급",
        "student": "학생",
        "gender": "성별",
        "sex": "성별",
        "age": "나이",
        "year": "연도",
        "month": "월",
        "date": "날짜",
        "time": "시간",
        "count": "수",
        "rate": "비율",
        "ratio": "비율",
        "percent": "비율",
        "price": "가격",
        "cost": "비용",
        "region": "지역",
        "area": "지역",
        "city": "도시",
        "name": "이름",
        "id": "번호",
        "total": "합계",
        "avg": "평균",
        "mean": "평균",
        "height": "키",
        "weight": "몸무게",
        "hours": "시간",
        "population": "인구",
    }

    def column_meanings(
        self,
        dataset: Dataset,
        research_question: str = "",
        student_level: str = "middle_high",
    ) -> list[dict]:
        _ = (research_question, student_level)
        meanings: list[dict] = []
        for column in dataset.columns:
            lowered = re.sub(r"[^a-z가-힣0-9]+", " ", column.name.lower())
            matched = [korean for token, korean in self.COLUMN_NAME_HINTS.items() if token in lowered]
            display_name = " ".join(dict.fromkeys(matched)) if matched else column.display_name
            kind = "수치형" if column.dtype == "numeric" else "범주형"
            meanings.append(
                {
                    "name": column.name,
                    "display_name": display_name or column.name,
                    "description": (
                        f"'{column.name}' 항목입니다. {kind} 자료로 읽었습니다."
                        if not matched
                        else f"{display_name}을(를) 나타내는 {kind} 항목으로 보입니다."
                    ),
                    "unit": column.unit,
                    "confident": bool(matched),
                }
            )
        return meanings

    def derived_variable_suggestions(
        self,
        dataset: Dataset,
        research_question: str = "",
        topic_title: str = "",
        student_level: str = "middle_high",
    ) -> list[dict]:
        _ = student_level
        numeric = [column for column in dataset.columns if column.dtype == "numeric"]
        question_context = " ".join(part for part in [topic_title, research_question] if part).strip()
        question_tokens = self._kosis_keywords(question_context) if question_context else []
        matched_numeric = [
            column
            for column in numeric
            if question_context
            and (
                column.display_name in question_context
                or column.name in question_context
                or any(token in column.display_name or token in column.name for token in question_tokens)
            )
        ]
        numeric_pool = matched_numeric if len(matched_numeric) >= 2 else numeric
        suggestions: list[dict] = []
        question_needs_gap = not question_context or any(
            word in question_context for word in ("차이", "격차", "비교", "관계", "관련", "사이")
        )
        question_needs_ratio = any(word in question_context for word in ("비율", "율", "비중", "대비", "당", "per"))
        if len(numeric_pool) >= 2:
            first, second = numeric_pool[0], numeric_pool[1]
            if question_needs_gap:
                suggestions.append(
                    {
                        "label": f"{first.display_name}와 {second.display_name}의 차이",
                        "new_column": f"{first.name}_minus_{second.name}",
                        "display_name": f"{first.display_name}-{second.display_name}",
                        "formula": "{" + first.name + "} - {" + second.name + "}",
                        "description": "두 수치형 항목의 차이를 행마다 계산해 비교합니다.",
                        "why": (
                            "탐구 질문에서 두 변수의 차이나 관계를 확인해야 하므로, "
                            "행별 격차를 따로 만들면 분석에 바로 쓸 수 있습니다."
                            if question_context
                            else "두 값의 격차가 탐구 질문과 관련될 수 있을 때 유용합니다."
                        ),
                        "needed_variable_check": {
                            "research_question": research_question,
                            "uses_question_relevant_columns": bool(matched_numeric),
                        },
                    }
                )
            if question_needs_ratio or not suggestions:
                suggestions.append(
                    {
                        "label": f"{second.display_name}/{first.display_name} 비율",
                        "new_column": f"{second.name}_per_{first.name}",
                        "display_name": f"{second.display_name}/{first.display_name}",
                        "formula": "{" + second.name + "} / {" + first.name + "}",
                        "description": "두 수치형 항목의 상대적 크기를 행마다 계산합니다.",
                        "why": (
                            "탐구 질문에서 비율, 비중, 단위당 값을 확인해야 하므로 단순 크기보다 상대값이 필요합니다."
                            if question_context
                            else "단순 크기보다 비율이 의미 있을 때 사용할 수 있습니다."
                        ),
                        "needed_variable_check": {
                            "research_question": research_question,
                            "uses_question_relevant_columns": bool(matched_numeric),
                        },
                    }
                )
        if any(column.name == "value" for column in numeric):
            question_allows_abs = not question_context or any(
                word in question_context for word in ("변화량", "크기", "절댓값")
            )
            if question_allows_abs:
                suggestions.append(
                    {
                        "label": "수치값의 절댓값",
                        "new_column": "value_abs",
                        "display_name": "수치값 절댓값",
                        "formula": "abs({value})",
                        "description": "음수와 양수를 같은 크기 기준으로 비교할 수 있게 합니다.",
                        "why": "변화량의 방향보다 크기 자체를 보고 싶을 때만 사용합니다.",
                        "needed_variable_check": {
                            "research_question": research_question,
                            "uses_question_relevant_columns": "value" in question_context or not question_context,
                        },
                    }
                )
        return suggestions[:3]

    def question_advice(self, student_input: str, student_level: str = "middle_high") -> dict:
        topic = student_input.strip() or "관심 있는 현상"
        level_label = {
            "middle": "중학교",
            "high": "고등학교",
            "middle_high": "중·고등학교",
        }.get(student_level, "중·고등학교")
        return {
            "student_input_summary": f"학생은 '{topic}'을(를) 자료로 탐구하고 싶어 합니다.",
            "overall_advice": (
                "관심사를 바로 결론으로 정하지 말고, 조사 대상과 측정할 변수를 정하면 "
                f"{level_label} 통계 수업에서 탐구할 수 있는 질문이 됩니다."
            ),
            "candidate_questions": [
                {
                    "title": "분포 살펴보기",
                    "question": f"{topic}에 대한 우리 반 학생들의 응답은 어떻게 분포할까?",
                    "type": "분포",
                    "why_it_fits_middle_school_statistics": (
                        "도수, 상대도수, 대푯값으로 응답의 퍼짐을 살필 수 있습니다."
                    ),
                    "data_to_collect": {
                        "target": "우리 반 또는 학년 학생",
                        "variables": ["응답 점수", "응답 범주"],
                        "collection_method": "익명 설문",
                        "sample_size_hint": "20명 이상이면 분포를 비교적 살펴보기 좋습니다.",
                    },
                    "recommended_analysis": ["도수분포표", "막대그래프", "평균", "중앙값"],
                    "possible_results": [
                        {
                            "result_pattern": "응답이 한쪽에 많이 모인다.",
                            "interpretation": "많은 학생이 비슷하게 느끼는 경향이 있을 수 있습니다.",
                            "decision_support": "왜 그런 응답이 많은지 후속 질문을 만들 수 있습니다.",
                        },
                        {
                            "result_pattern": "응답이 여러 범주에 고르게 퍼진다.",
                            "interpretation": "학생마다 경험이나 생각의 차이가 클 수 있습니다.",
                            "decision_support": "집단별 비교 질문으로 발전시킬 수 있습니다.",
                        },
                    ],
                    "cautions": ["개인정보를 모으지 않기", "질문 기준을 분명히 쓰기"],
                    "good_choice_when": "먼저 전체 경향을 간단히 확인하고 싶을 때 좋습니다.",
                },
                {
                    "title": "두 집단 비교하기",
                    "question": f"{topic}에 대한 응답은 학년이나 성별 등 두 집단에서 차이가 있을까?",
                    "type": "비교",
                    "why_it_fits_middle_school_statistics": (
                        "두 집단의 평균, 중앙값, 상대도수, 상자그림을 비교할 수 있습니다."
                    ),
                    "data_to_collect": {
                        "target": "비교할 수 있는 두 학생 집단",
                        "variables": ["집단 구분", "응답 점수 또는 범주"],
                        "collection_method": "익명 설문 또는 관찰 기록",
                        "sample_size_hint": "각 집단 15명 이상을 권장합니다.",
                    },
                    "recommended_analysis": ["평균 비교", "상자그림", "상대도수"],
                    "possible_results": [
                        {
                            "result_pattern": "두 집단의 대푯값이 비슷하다.",
                            "interpretation": "집단에 따른 큰 차이가 보이지 않을 수 있습니다.",
                            "decision_support": "다른 기준으로 나누어 다시 살펴볼 수 있습니다.",
                        },
                        {
                            "result_pattern": "한 집단의 값이 더 높거나 낮다.",
                            "interpretation": "집단별 경험이나 조건 차이가 관련될 수 있습니다.",
                            "decision_support": "차이가 나는 이유를 단정하지 않고 추가 자료를 생각할 수 있습니다.",
                        },
                    ],
                    "cautions": ["민감한 집단 구분은 피하기", "표본 수 차이가 너무 크지 않게 하기"],
                    "good_choice_when": "두 조건이나 두 집단의 차이를 보고 싶을 때 좋습니다.",
                },
            ],
            "refinement_tips": [
                "조사 대상을 '우리 반', '우리 학교 학생'처럼 좁혀 보세요.",
                "측정할 값을 숫자나 선택지로 바꾸어 보세요.",
                "비교 기준을 하나만 정하면 질문이 더 선명해집니다.",
            ],
            "student_decision_guide": [
                "자료를 쉽게 모을 수 있는 질문을 먼저 고르세요.",
                "개인정보나 민감한 내용은 익명으로 줄이거나 다른 변수로 바꾸세요.",
            ],
            "next_questions_for_student": [
                "누구에게 자료를 모을 수 있나요?",
                "응답을 숫자로 기록할 수 있나요?",
            ],
            "metadata": {"source": "mock", "prompt": "question-advisor", "student_level": student_level},
        }

    def big_data_question_advice(
        self,
        student_input: str,
        student_level: str = "middle_high",
        evidence: dict | None = None,
    ) -> dict:
        topic = student_input.strip() or "관심 있는 현상"
        evidence = evidence or {}
        stat_search = evidence.get("stat_api", {}).get("search_datasets", {})
        route_sources = evidence.get("stat_api", {}).get("route_sources", {})
        candidates = stat_search.get("candidates") if isinstance(stat_search, dict) else []
        sources = route_sources.get("recommended_sources") if isinstance(route_sources, dict) else []
        first_candidate = candidates[0] if candidates else {}
        first_source = sources[0] if sources else {}
        dataset_title = first_candidate.get("dataset_title") or first_source.get("display_name") or "공개 통계 자료"
        source_name = first_candidate.get("provider") or first_source.get("display_name") or "공식 통계 API"
        dimensions = first_candidate.get("available_dimensions") or route_sources.get(
            "data_need",
            {},
        ).get("dimensions", [])
        measures = first_candidate.get("available_measures") or route_sources.get(
            "data_need",
            {},
        ).get("main_variables", [])
        kosis_recommendations = (
            evidence.get("kosis", {}).get("recommendations", {}).get("recommended_datasets", [])
            if isinstance(evidence.get("kosis"), dict)
            else []
        )
        kosis_hint = ""
        if kosis_recommendations:
            kosis_title = kosis_recommendations[0].get("dataset_title") or kosis_recommendations[0].get("tbl_name")
            kosis_hint = f"KOSIS에서도 '{kosis_title}' 후보를 함께 확인할 수 있습니다."
        return {
            "student_input_summary": f"학생은 '{topic}'을(를) 실제 공개 통계/API 자료로 탐구하고 싶어 합니다.",
            "overall_advice": (
                f"먼저 {source_name}의 '{dataset_title}' 같은 실제 자료 후보를 기준으로, "
                "탐구 질문을 기간·지역·비교 대상·측정 지표가 드러나는 문장으로 좁히면 좋습니다. "
                f"{kosis_hint}"
            ).strip(),
            "candidate_questions": [
                {
                    "title": "공개 통계 변화 살펴보기",
                    "question": f"{topic}와 관련된 지표는 최근 기간에 어떻게 변했을까?",
                    "type": "빅데이터 변화",
                    "why_it_fits_middle_school_statistics": (
                        "실제 API 자료에서 기간별 값을 가져와 선그래프와 증감 비교로 탐구할 수 있습니다."
                    ),
                    "data_to_collect": {
                        "target": source_name,
                        "variables": measures[:5] or ["기간", "지역 또는 국가", "지표값"],
                        "collection_method": f"{dataset_title} API 또는 CSV 다운로드",
                        "sample_size_hint": "최근 5~10년, 여러 지역 또는 국가처럼 행이 충분한 집계자료를 사용합니다.",
                    },
                    "recommended_analysis": ["선그래프", "막대그래프", "요약 통계", "지역/국가별 비교"],
                    "possible_results": [
                        {
                            "result_pattern": "기간에 따라 꾸준히 증가하거나 감소한다.",
                            "interpretation": "정책, 사회 변화, 경제 상황 등과 관련된 추세를 생각해 볼 수 있습니다.",
                            "decision_support": "원인을 단정하지 않고 추가 지표와 비교할 계획을 세웁니다.",
                        },
                        {
                            "result_pattern": "지역이나 국가별 차이가 크다.",
                            "interpretation": "집계 단위의 조건 차이가 결과와 관련될 수 있습니다.",
                            "decision_support": "비교 기준과 단위를 맞추어 해석합니다.",
                        },
                    ],
                    "cautions": ["단위와 기준연도 확인하기", "상관이나 차이를 원인으로 단정하지 않기"],
                    "good_choice_when": "직접 설문보다 넓은 지역·기간의 실제 통계로 주제를 보고 싶을 때 좋습니다.",
                },
                {
                    "title": "두 공개 지표 관계 탐구",
                    "question": f"{topic}와 관련된 두 지표는 지역이나 국가별로 함께 높고 낮게 나타날까?",
                    "type": "빅데이터 관계",
                    "why_it_fits_middle_school_statistics": (
                        "두 수치형 지표를 산점도나 상관계수로 비교하면서 관계의 방향을 탐구할 수 있습니다."
                    ),
                    "data_to_collect": {
                        "target": ", ".join(dimensions[:3]) or "지역 또는 국가 단위 공개 통계",
                        "variables": measures[:5] or ["비교 지표 A", "비교 지표 B", "지역/국가", "연도"],
                        "collection_method": "공식 통계 API 후보를 검색해 같은 기간·단위로 맞춥니다.",
                        "sample_size_hint": "같은 기준의 지역/국가가 15개 이상 있으면 산점도 해석에 도움이 됩니다.",
                    },
                    "recommended_analysis": ["산점도", "상관계수", "집단별 색상 구분", "요약 통계"],
                    "possible_results": [
                        {
                            "result_pattern": "두 지표가 함께 높아지는 경향이 보인다.",
                            "interpretation": "두 현상이 같은 사회적 조건과 관련될 가능성을 생각해 볼 수 있습니다.",
                            "decision_support": "다른 기간에도 같은 관계가 보이는지 확인합니다.",
                        },
                        {
                            "result_pattern": "뚜렷한 관계가 보이지 않는다.",
                            "interpretation": "입력한 주제가 다른 변수나 더 좁은 집단에서만 설명될 수 있습니다.",
                            "decision_support": "자료 범위나 지표 정의를 바꾸어 다시 탐색합니다.",
                        },
                    ],
                    "cautions": [
                        "지표 정의가 서로 다른 자료를 무리하게 합치지 않기",
                        "개인 수준 결론으로 확대하지 않기",
                    ],
                    "good_choice_when": "대규모 자료로 관계를 살펴보고 싶을 때 좋습니다.",
                },
            ],
            "refinement_tips": [
                "질문에 기간, 지역/국가, 비교할 지표 이름을 넣어 보세요.",
                "API 후보의 단위와 분류가 질문에 맞는지 먼저 확인하세요.",
                "자동 수집이 안 되는 후보는 CSV/XLS 다운로드 후 업로드하는 계획으로 바꾸세요.",
            ],
            "student_decision_guide": [
                "실제로 찾은 자료 후보가 있는 질문을 우선 고르세요.",
                "단위가 같고 기간이 겹치는 자료끼리 비교하세요.",
                "자료가 집계자료인지 개인자료인지 구분해 해석 범위를 정하세요.",
            ],
            "next_questions_for_student": [
                "내 질문에 필요한 지표는 정확히 무엇인가요?",
                "비교할 기간과 지역/국가는 어디까지로 정할까요?",
                "자동 API 수집이 가능한가요, 아니면 CSV 다운로드가 필요한가요?",
            ],
            "metadata": {"source": "mock", "prompt": "big-data-question-advisor", "student_level": student_level},
        }

    def kosis_search_plan(self, research_question: str, grade_level: str = "middle_high") -> dict:
        keywords = self._kosis_keywords(research_question)
        analysis_type = []
        if any(word in research_question for word in ("변화", "추이", "최근", "연도", "시계열")):
            analysis_type.append("변화")
        if any(word in research_question for word in ("지역", "성별", "연령", "집단", "차이", "비교")):
            analysis_type.append("비교")
        if any(word in research_question for word in ("관계", "상관", "관련")):
            analysis_type.append("관계")
        if not analysis_type:
            analysis_type.append("비교")
        preferred_dimensions = []
        for label in ("연도", "지역", "성별", "연령"):
            if label in research_question or label == "연도":
                preferred_dimensions.append(label)
        return {
            "topic": keywords[0] if keywords else research_question,
            "research_question": research_question,
            "needed_variables": keywords[:5],
            "analysis_type": analysis_type,
            "preferred_data_shape": "연도와 분류를 포함한 long format 집계표",
            "preferred_dimensions": preferred_dimensions[:4],
            "search_keywords": keywords,
            "metadata": {"source": "mock", "prompt": "kosis-search-plan", "grade_level": grade_level},
        }

    def kosis_dataset_recommendations(
        self,
        research_question: str,
        grade_level: str,
        search_plan: dict,
        candidates: list[dict],
    ) -> dict:
        keywords = set(self._kosis_keywords(research_question) + search_plan.get("search_keywords", []))

        def score(candidate: dict) -> int:
            haystack = " ".join(
                str(candidate.get(key) or "")
                for key in ("tbl_name", "stat_name", "contents", "available_dimensions", "available_items")
            )
            match_score = sum(1 for keyword in keywords if keyword and keyword in haystack)
            period_bonus = 8 if candidate.get("period_range") and candidate.get("period_range") != "확인 필요" else 0
            dimension_bonus = min(len(candidate.get("available_dimensions") or []), 4) * 3
            return 45 + match_score * 8 + period_bonus + dimension_bonus

        ranked = sorted(candidates, key=score, reverse=True)[:5]
        recommended = []
        for index, candidate in enumerate(ranked, start=1):
            recommended.append(
                {
                    "rank": index,
                    "org_id": candidate.get("org_id"),
                    "org_name": candidate.get("org_name"),
                    "tbl_id": candidate.get("tbl_id"),
                    "tbl_name": candidate.get("tbl_name"),
                    "dataset_title": candidate.get("tbl_name"),
                    "source_agency": candidate.get("org_name"),
                    "stat_name": candidate.get("stat_name"),
                    "fit_score": min(score(candidate), 100),
                    "why_recommended": "검색어와 통계표 설명이 탐구 질문의 핵심 표현과 연결됩니다.",
                    "relation_to_research_question": (
                        "학생이 입력한 검색어로 실제 KOSIS에서 찾은 통계표이며, "
                        "탐구 질문의 변수나 비교 기준을 확인하는 데 사용할 수 있습니다."
                    ),
                    "usable_analysis": ["시점별 변화 확인", "분류별 비교", "막대그래프 또는 꺾은선그래프"],
                    "available_dimensions": candidate.get("available_dimensions") or ["확인 필요"],
                    "available_items": candidate.get("available_items") or ["확인 필요"],
                    "period_range": candidate.get("period_range") or "확인 필요",
                    "unit": candidate.get("unit") or "확인 필요",
                    "csv_plan": {
                        "rows_meaning": "한 행은 특정 시점, 항목, 분류값의 집계 수치를 뜻합니다.",
                        "needed_columns": ["period", "dimension_1_value", "item", "unit", "value"],
                        "recommended_filter": "앱은 최근 5개 시점과 전체 항목/분류를 우선 가져옵니다.",
                    },
                    "student_friendly_summary": (
                        "이 자료를 쓰면 시점별 변화나 분류별 차이를 표와 그래프로 살펴볼 수 있습니다."
                    ),
                    "limitations": ["개인별 원자료가 아니라 KOSIS 집계자료입니다."],
                    "cautions": ["차이가 보이더라도 원인을 바로 단정하지 않습니다."],
                }
            )
        return {
            "student_question": research_question,
            "data_need_summary": {
                "main_variables": search_plan.get("needed_variables", []),
                "comparison_or_analysis_goal": ", ".join(search_plan.get("analysis_type", [])),
                "preferred_dimensions": search_plan.get("preferred_dimensions", []),
                "preferred_measure": "비율/인원/평균 등 통계표 단위 확인",
            },
            "recommended_datasets": recommended,
            "not_recommended_examples": [],
            "decision_guide_for_student": [
                "내 탐구 질문의 대상과 통계표의 분류가 맞는지 확인하세요.",
                "단위가 비율인지 인원인지 먼저 확인하세요.",
            ],
            "fallback_if_no_good_kosis_data": {
                "message": "KOSIS 후보가 부족하면 직접 설문이나 다른 공공데이터를 함께 고려하세요.",
                "alternative_plan": "조사 대상과 변수를 좁혀 CSV를 직접 수집합니다.",
            },
            "metadata": {"source": "mock", "prompt": "kosis-dataset-recommendation", "grade_level": grade_level},
        }

    def _kosis_keywords(self, text: str) -> list[str]:
        cleaned = re.sub(r"[^\w가-힣\s]", " ", text)
        words = [word for word in cleaned.split() if len(word) >= 2]
        stopwords = {"어떻게", "사이에", "있는지", "있는가", "대해", "최근", "동안", "차이", "관계"}
        core_words = [word for word in words if word not in stopwords][:8]
        keywords = [" ".join(core_words[:3]).strip(), " ".join(core_words[:2]).strip(), *core_words[:5]]
        unique = []
        for keyword in keywords:
            if keyword and keyword not in unique:
                unique.append(keyword)
        return unique[:5] or [text.strip()]

    def interpretation_hints(
        self,
        analysis: AnalysisResult,
        student_level: str = "middle_high",
        prompt_text: str = "",
    ) -> dict:
        tool_name = analysis.tool_name
        observations = [
            "그래프나 통계량에서 가장 큰 값과 가장 작은 값을 먼저 찾아보세요.",
            "값이 꾸준히 변하는지, 특정 시점에 크게 달라지는지 확인해 보세요.",
            "자료가 보여 주는 사실과 추측을 구분해 적어 보세요.",
        ]
        questions = [
            "이 결과만으로 말할 수 있는 사실은 무엇인가요?",
            "자료만으로는 알 수 없는 이유나 배경은 무엇인가요?",
        ]
        if tool_name == "compute_correlation":
            observations.insert(0, "상관계수의 부호와 절댓값을 확인해 관계의 방향과 강도를 살펴보세요.")
            questions.append("상관관계가 있다고 해서 한 변수가 다른 변수를 반드시 일으킨다고 말할 수 있을까요?")
        if tool_name.startswith("plot_"):
            observations.insert(0, "차트에서 전체적인 모양, 튀는 값, 반복되는 패턴을 차례로 확인해 보세요.")
        if analysis.tool_args.get("group_by") and tool_name in {
            "plot_boxplot",
            "compute_descriptive_stats",
        }:
            observations.insert(0, "집단별 중앙값(또는 평균)이 어느 쪽이 더 큰지 먼저 비교해 보세요.")
            observations.insert(1, "대표값이 비슷해도 상자의 길이나 표준편차가 다르면 퍼진 정도가 다른 것입니다.")
            questions.insert(0, "두 집단의 차이는 대표값 차이인가요, 퍼진 정도의 차이인가요?")
        return {
            "student_level": student_level,
            "observations": observations[:5],
            "questions": questions[:3],
            "warning": "이 안내는 결론을 대신 작성하지 않으며, 관찰과 질문만 제공합니다.",
        }

    CAUSAL_MARKERS = ("때문에", "때문이", "원인은", "원인이", "탓에", "덕분에", "영향을 준", "영향을 미친")
    OVERREACH_MARKERS = ("항상", "무조건", "절대", "모든 사람", "누구나", "반드시")

    def interpretation_feedback(
        self,
        analysis: AnalysisResult,
        interpretation_text: str,
        student_level: str = "middle_high",
        research_question: str = "",
    ) -> dict:
        text = (interpretation_text or "").strip()
        strengths: list[str] = []
        improvements: list[str] = []
        questions = [
            "이 해석에서 자료로 확인한 사실과 내 추측은 어떻게 구분되나요?",
            "탐구 질문에 답하려면 어떤 내용을 더 적어야 할까요?",
        ]

        has_number = bool(re.search(r"\d", text))
        sentence_count = len([part for part in re.split(r"[.!?\n]+", text) if part.strip()])

        if has_number:
            strengths.append("분석 결과의 수치를 인용해서 근거가 분명합니다.")
        else:
            improvements.append("그래프나 표에서 읽은 값을 한 개라도 적어 보세요. 숫자가 있으면 근거가 분명해집니다.")

        if sentence_count >= 2:
            strengths.append("한 문장으로 끝내지 않고 관찰한 내용을 나누어 적었습니다.")
        else:
            improvements.append("관찰한 사실 한 문장, 그것이 탐구 질문에 어떤 뜻인지 한 문장으로 나누어 적어 보세요.")

        if any(marker in text for marker in self.CAUSAL_MARKERS):
            improvements.append(
                "원인을 단정하는 표현이 있습니다. 이 자료로 확인한 것은 함께 나타나는 관계이므로 "
                "'~때문이다' 대신 '~와 함께 나타난다'처럼 적어 보세요."
            )
            questions.insert(0, "이 자료만으로 원인을 말할 수 있나요, 아니면 관계만 말할 수 있나요?")

        if any(marker in text for marker in self.OVERREACH_MARKERS):
            improvements.append(
                "'항상', '모든'처럼 자료 범위를 넘는 표현이 있습니다. 자료가 다루는 기간과 대상 안에서만 말해 주세요."
            )

        if analysis.tool_args.get("group_by"):
            questions.append("두 집단의 차이는 대표값 차이인가요, 퍼진 정도의 차이인가요?")
        if analysis.tool_name in {"compute_correlation", "compute_grouped_correlation", "plot_scatter"}:
            questions.append("관계의 방향(같이 커지는지, 반대로 가는지)을 해석에 적었나요?")

        if not strengths:
            strengths.append("결과를 직접 읽고 자기 문장으로 옮기려는 시도가 보입니다.")
        if not improvements:
            improvements.append("자료가 답해 주지 못하는 부분이 무엇인지 한 문장 덧붙이면 더 좋아집니다.")

        return {
            "student_level": student_level,
            "summary": "해석을 읽고 잘한 점과 보완할 점을 정리했습니다. 고쳐 쓴 뒤 저장해 보세요.",
            "strengths": strengths[:3],
            "improvements": improvements[:3],
            "questions": questions[:3],
            "warning": "이 피드백은 해석을 대신 써 주지 않습니다. 고쳐 쓰는 것은 학생이 합니다.",
            "metadata": {"source": "mock"},
        }

    def coach(
        self,
        project: Project,
        topic: Topic | None = None,
        dataset: Dataset | None = None,
        analysis: AnalysisResult | None = None,
        student_level: str = "middle_high",
        prompt_text: str = "",
    ) -> dict:
        coach = build_rule_based_coach(project, topic, dataset, analysis, source="mock")
        coach["metadata"]["student_level"] = student_level
        return coach


def get_guide_service():
    if get_settings().enable_gemini:
        from app.ai.gemini_adapter import GeminiGuideService

        return GeminiGuideService()
    return MockGuideService()
