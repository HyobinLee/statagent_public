from html import escape as html_escape
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import get_settings
from app.core.errors import AppError
from app.core.time import now_utc
from app.models.project import InquiryStep
from app.models.report import Report
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService
from app.services.report_grid import (
    CELL_GAP_MM,
    COL_WIDTH_MM,
    DEFAULT_ACCENT_COLOR,
    DEFAULT_FONT_KEY,
    DEFAULT_PRIMARY_COLOR,
    GRID_COLS,
    MAX_PAGES,
    PAGE_HEIGHT_MM,
    PAGE_MARGIN_MM,
    PAGE_ROWS,
    PAGE_WIDTH_MM,
    REPORT_FONTS,
    ROW_HEIGHT_MM,
    clamp_rect,
    normalize_font_key,
    normalize_hex_color,
)
from app.services.report_media_storage import (
    is_stored_image_url,
    local_image_path,
    store_external_image,
    store_uploaded_image,
)
from app.services.topic_service import TopicService

MAX_REPORT_BLOCKS = 28
MAX_BLOCK_TEXT = 2000
MAX_BLOCK_TITLE = 80
ALLOWED_BLOCK_TYPES = {
    "heading",
    "topic",
    "dataset_source",
    "analysis",
    "synthesis",
    "chart",
    "image",
    "table",
    "conclusion",
    "text_note",
    "highlight",
    "divider",
}
ALLOWED_WIDTHS = {"full", "half", "third"}
ALLOWED_TEMPLATES = {"executive", "poster", "story"}
REQUIRED_BLOCK_TYPES = ("topic", "dataset_source", "conclusion")

MAX_TABLE_ROWS = 12
MAX_TABLE_COLS = 8
MAX_TABLE_CELL_TEXT = 120

ALLOWED_IMAGE_FITS = {"contain", "cover"}
ALLOWED_IMAGE_SOURCES = {"upload", "external"}

WIDTH_TO_COLS = {"full": GRID_COLS, "half": GRID_COLS // 2, "third": GRID_COLS // 3}
DEFAULT_BLOCK_ROWS = {
    "heading": 2,
    "divider": 1,
    "topic": 4,
    "dataset_source": 5,
    "analysis": 7,
    "synthesis": 7,
    "chart": 7,
    "image": 6,
    "table": 5,
    "highlight": 3,
    "text_note": 3,
    "conclusion": 4,
}
DEFAULT_BLOCK_ROWS_FALLBACK = 4

ACCENT_COLORS = {
    "none": "#cbd5d1",
    "teal": "#287c7a",
    "amber": "#b3701a",
    "violet": "#6d5bd0",
    "rose": "#c2415f",
}
ALLOWED_ACCENTS = set(ACCENT_COLORS)

BLOCK_DEFAULT_TITLES = {
    "topic": "탐구 질문",
    "dataset_source": "사용한 자료와 출처",
    "analysis": "분석 결과",
    "synthesis": "자료 종합 비교",
    "chart": "그래프",
    "image": "그림",
    "table": "표",
    "conclusion": "결론",
    "text_note": "메모",
    "highlight": "핵심 발견",
    "heading": "",
}

UNCAPTIONED_BLOCK_TYPES = {"divider"}

TOOL_LABELS_KO = {
    "compute_descriptive_stats": "요약 통계",
    "compute_correlation": "상관계수",
    "compute_grouped_correlation": "집단별 상관계수(층화분석)",
    "plot_grouped_scatter": "집단별 산점도",
    "plot_map": "지도",
    "plot_bar": "막대그래프",
    "plot_histogram": "히스토그램",
    "plot_boxplot": "상자그림",
    "plot_scatter": "산점도",
    "plot_line": "선그래프",
    "plot_frequency_polygon": "도수분포다각형",
    "plot_stem_leaf": "줄기와 잎 그림",
    "plot_pie": "원그래프",
    "create_frequency_table": "도수분포표",
    "create_crosstab": "교차표",
    "plot_choropleth": "지도 시각화",
    "compute_cross_dataset_comparison": "교차 대표값 비교",
    "compute_cross_correlation": "교차 상관계수",
    "plot_comparative_line": "비교 선그래프",
    "plot_comparative_bar": "비교 막대그래프",
}


def tool_label_ko(tool_name: str) -> str:
    return TOOL_LABELS_KO.get(tool_name or "", tool_name or "분석")


def _mm(value: float):
    from pptx.util import Mm

    return Mm(value)


class ReportService:
    def __init__(self) -> None:
        self.repo = get_repository()
        self.topics = TopicService()
        self.datasets = DatasetService()

    def submit_conclusion(self, project_id: str, conclusion_text: str, user: User) -> Report:
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
                "다른 사용자의 프로젝트에 결론을 제출할 수 없습니다.",
                "로그인 계정 또는 관리자 대리 접근 대상을 확인해 주세요.",
                403,
            )
        if project.status != "analysis_done" or not project.latest_analysis_result_id:
            raise AppError(
                "WORKFLOW_STEP_VIOLATION",
                "분석 결과가 있어야 결론을 제출할 수 있습니다.",
                "자료 선택과 분석 실행을 먼저 완료해 주세요.",
            )
        topic_title = self._topic_title(project)
        dataset_sources = self._dataset_sources(project)
        dataset_names = [item["name"] for item in dataset_sources]
        analyses = self._project_analyses(project)
        syntheses = self._project_syntheses(project)
        analysis = analyses[-1] if analyses else None
        chart_urls = self._analysis_chart_urls(analyses, syntheses)
        latest_synthesis_id = syntheses[-1].synthesis_result_id if syntheses else None
        result_specs = self._result_specs(analyses, syntheses)
        report = Report(
            report_id=f"report_{uuid4().hex[:12]}",
            project_id=project.project_id,
            student_user_id=project.owner_user_id,
            teacher_user_id="teacher-001",
            topic_title=topic_title,
            dataset_name=dataset_names[-1] if dataset_names else "선택 자료",
            dataset_names=dataset_names,
            dataset_sources=dataset_sources,
            analysis_summary=analysis.result if analysis else {},
            analysis_summaries=[item.result for item in analyses],
            chart_urls=chart_urls,
            analysis_result_ids=[item.analysis_result_id for item in analyses],
            synthesis_result_ids=[item.synthesis_result_id for item in syntheses],
            conclusion_text=conclusion_text.strip(),
            layout=self.default_layout(
                chart_urls,
                latest_synthesis_id,
                result_specs=result_specs,
                topic_title=topic_title,
            ),
        )
        self.repo.create_report(report)
        project.report_id = report.report_id
        project.status = "conclusion_submitted"
        project.steps.append(
            InquiryStep(
                step_id=f"step_{uuid4().hex[:12]}",
                step_type="reflection_written",
                payload={"report_id": report.report_id},
            )
        )
        self.repo.update_project(project)
        return report

    def update_conclusion(self, project_id: str, conclusion_text: str, user: User) -> "Report":
        project = self.repo.get_project(project_id)
        if not project:
            raise AppError(
                "PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.", "프로젝트 목록을 새로고침해 주세요.", 404
            )
        if user.role == "student" and project.owner_user_id != user.user_id:
            raise AppError("FORBIDDEN", "다른 사용자의 프로젝트 결론을 수정할 수 없습니다.", "", 403)
        if not project.report_id:
            raise AppError(
                "WORKFLOW_STEP_VIOLATION", "보고서가 없어 결론을 저장할 수 없습니다.", "보고서를 먼저 만들어 주세요."
            )
        report = self.repo.get_report(project.report_id)
        if not report:
            raise AppError("REPORT_NOT_FOUND", "보고서를 찾을 수 없습니다.", "", 404)
        report.conclusion_text = conclusion_text.strip()
        self.repo.update_report(report)
        return report

    def _topic_title(self, project) -> str:
        if project.custom_topic_question:
            return project.custom_topic_title or project.custom_topic_question
        try:
            return self.topics.get_topic(project.topic_id or "").title
        except AppError:
            return project.custom_topic_title or "탐구 주제"

    def _dataset_sources(self, project) -> list[dict]:
        dataset_ids = project.dataset_ids or ([project.dataset_id] if project.dataset_id else [])
        sources = []
        seen = set()
        for dataset_id in dataset_ids:
            try:
                dataset = self.datasets.get_dataset(dataset_id)
            except AppError:
                continue
            if dataset.dataset_id in seen:
                continue
            seen.add(dataset.dataset_id)
            sources.append(
                {
                    "dataset_id": dataset.dataset_id,
                    "name": dataset.name,
                    "source": dataset.source,
                    "source_note": dataset.source_note,
                    "description": dataset.description,
                    "time_range": dataset.time_range,
                    "geographic_unit": dataset.geographic_unit,
                    "column_count": len(dataset.columns),
                }
            )
        return sources

    def _project_analyses(self, project) -> list:
        analysis_ids = project.analysis_result_ids or (
            [project.latest_analysis_result_id] if project.latest_analysis_result_id else []
        )
        analyses = []
        for analysis_id in analysis_ids:
            analysis = self.repo.get_analysis_result(analysis_id)
            if analysis:
                analyses.append(analysis)
        return analyses

    def _project_syntheses(self, project) -> list:
        syntheses = []
        for synthesis_id in project.synthesis_result_ids or []:
            synthesis = self.repo.get_synthesis_result(synthesis_id)
            if synthesis:
                syntheses.append(synthesis)
        return syntheses

    def _analysis_chart_urls(self, analyses: list, syntheses: list | None = None) -> list[str]:
        collected: list[str] = []
        for source in [*analyses, *(syntheses or [])]:
            collected.extend(source.chart_urls or [])
        return self._unique_chart_urls(collected)

    def _canonical_chart_url(self, url: str) -> str:
        text = str(url or "")
        if text.lower().endswith(".svg"):
            return f"{text[:-4]}.png"
        return text

    def _unique_chart_urls(self, urls: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for raw in urls:
            url = self._canonical_chart_url(raw)
            if not url:
                continue
            key = self._chart_key(url)
            if key in seen:
                continue
            seen.add(key)
            unique.append(url)
        return unique

    def _resolve_chart_ref(self, ref_id: str, chart_urls: list[str]) -> str:
        candidate = self._canonical_chart_url(ref_id)
        if candidate in chart_urls:
            return candidate
        key = self._chart_key(candidate)
        for url in chart_urls:
            if self._chart_key(url) == key:
                return url
        return ""

    def list_reports(self, user: User) -> list[Report]:
        reports = self.repo.list_reports()
        if user.role == "student":
            return [report for report in reports if report.student_user_id == user.user_id]
        return reports

    def get_report(self, report_id: str, user: User) -> Report:
        report = self.repo.get_report(report_id)
        if not report:
            raise AppError(
                "REPORT_NOT_FOUND",
                "보고서를 찾을 수 없습니다.",
                "보고서 목록을 새로고침해 주세요.",
                404,
            )
        if user.role == "student" and report.student_user_id != user.user_id:
            raise AppError(
                "FORBIDDEN",
                "다른 사용자의 보고서를 볼 수 없습니다.",
                "로그인 계정 또는 관리자 대리 접근 대상을 확인해 주세요.",
                403,
            )
        if not isinstance(report.layout, dict) or report.layout.get("version") != 3:
            report.layout = self._sanitize_layout(report.layout, report)
        return report

    def save_feedback(self, report_id: str, feedback_text: str, teacher: User) -> Report:
        if teacher.role not in {"teacher", "admin"}:
            raise AppError(
                "FORBIDDEN",
                "교사 또는 관리자만 피드백을 저장할 수 있습니다.",
                "교사 또는 관리자 계정으로 로그인해 주세요.",
                403,
            )
        report = self.get_report(report_id, teacher)
        if not feedback_text.strip():
            raise AppError(
                "INVALID_ARGUMENT",
                "피드백 내용을 입력해야 합니다.",
                "학생이 다음에 개선할 점을 짧게 적어 주세요.",
            )
        report.feedback_text = feedback_text.strip()
        report.teacher_user_id = teacher.user_id
        report.status = "feedback_given"
        report.feedback_at = now_utc()
        return self.repo.update_report(report)

    def save_reflection(self, report_id: str, reflection: dict, user: User) -> "Report":
        report = self.get_report(report_id, user)
        if user.role == "student" and report.student_user_id != user.user_id:
            raise AppError("FORBIDDEN", "자신의 보고서에만 성찰을 저장할 수 있습니다.", "", 403)
        report.student_reflection = reflection
        return self.repo.update_report(report)

    def add_image(
        self,
        report_id: str,
        user: User,
        content: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        external_url: str | None = None,
    ) -> str:
        self.get_report(report_id, user)
        if external_url:
            return store_external_image(external_url)
        if content is None:
            raise AppError(
                "INVALID_ARGUMENT",
                "올릴 그림이 없습니다.",
                "그림 파일을 고르거나 그림 주소를 넣어 주세요.",
                400,
            )
        return store_uploaded_image(filename or "image", content, content_type)

    def save_layout(self, report_id: str, layout: dict, user: User) -> Report:
        report = self.get_report(report_id, user)
        sanitized = self._sanitize_layout(layout, report)
        report.layout = sanitized
        return self.repo.update_report(report)

    def _new_block(
        self,
        block_type: str,
        ref_id: str = "",
        title: str = "",
        text: str = "",
        width: str = "full",
        accent: str = "none",
        repeat: bool = False,
    ) -> dict:
        return {
            "block_id": f"blk_{uuid4().hex[:8]}",
            "type": block_type,
            "ref_id": ref_id,
            "title": title[:MAX_BLOCK_TITLE],
            "text": text[:MAX_BLOCK_TEXT],
            "width": width,
            "accent": accent,
            "repeat": repeat,
            "order": 0,
        }

    def _block_rows(self, block: dict) -> int:
        return DEFAULT_BLOCK_ROWS.get(str(block.get("type")), DEFAULT_BLOCK_ROWS_FALLBACK)

    def _auto_place(self, blocks: list[dict]) -> list[dict]:
        pages: list[list[dict]] = [[]]
        cursor_x = 0
        cursor_y = 0
        row_height = 0
        for block in blocks:
            cols = WIDTH_TO_COLS.get(str(block.get("width") or "full"), GRID_COLS)
            cols = max(1, min(cols, GRID_COLS))
            rows = max(1, min(self._block_rows(block), PAGE_ROWS))
            if cursor_x + cols > GRID_COLS:
                cursor_x = 0
                cursor_y += row_height
                row_height = 0
            if cursor_y + rows > PAGE_ROWS:
                if len(pages) >= MAX_PAGES:
                    break
                pages.append([])
                cursor_x = 0
                cursor_y = 0
                row_height = 0
            block["x"], block["y"], block["w"], block["h"] = clamp_rect(cursor_x, cursor_y, cols, rows)
            block.pop("width", None)
            pages[-1].append(block)
            cursor_x += cols
            row_height = max(row_height, rows)
        return [{"page_id": f"pg_{uuid4().hex[:8]}", "blocks": page} for page in pages]

    def _finalize_layout(self, template: str, blocks: list[dict], theme: dict | None = None) -> dict:
        for index, block in enumerate(blocks, start=1):
            block["order"] = index
        return {
            "version": 3,
            "template": template,
            "paper": "a4",
            "theme": self._sanitize_theme(theme),
            "pages": self._auto_place(blocks),
        }

    def _sanitize_theme(self, theme: object) -> dict:
        raw = theme if isinstance(theme, dict) else {}
        return {
            "font": normalize_font_key(raw.get("font")),
            "primary": normalize_hex_color(raw.get("primary"), DEFAULT_PRIMARY_COLOR),
            "accent": normalize_hex_color(raw.get("accent"), DEFAULT_ACCENT_COLOR),
        }

    def _result_specs(self, analyses: list, syntheses: list | None = None) -> list[dict]:
        specs: list[dict] = []
        for analysis in analyses or []:
            specs.append(
                {
                    "kind": "analysis",
                    "ref_id": analysis.analysis_result_id,
                    "chart_urls": self._unique_chart_urls(analysis.chart_urls or []),
                    "label": tool_label_ko(analysis.tool_name),
                    "caption": self._result_caption(analysis.result),
                }
            )
        for synthesis in syntheses or []:
            specs.append(
                {
                    "kind": "synthesis",
                    "ref_id": synthesis.synthesis_result_id,
                    "chart_urls": self._unique_chart_urls(synthesis.chart_urls or []),
                    "label": tool_label_ko(synthesis.tool_name),
                    "caption": self._result_caption(synthesis.result),
                }
            )
        return specs

    def _result_caption(self, result: dict) -> str:
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and data.get("alt_text"):
            return str(data["alt_text"])[:MAX_BLOCK_TEXT]
        return self._analysis_result_summary_text(result if isinstance(result, dict) else {})[:MAX_BLOCK_TEXT]

    def default_layout(
        self,
        chart_urls: list[str] | None = None,
        latest_synthesis_result_id: str | None = None,
        result_specs: list[dict] | None = None,
        topic_title: str = "",
    ) -> dict:
        specs = result_specs
        if specs is None:
            specs = self._specs_from_chart_urls(chart_urls, latest_synthesis_result_id)

        blocks = [
            self._new_block("heading", title=topic_title or "통계 탐구 포스터", text="통계 탐구 포스터", accent="teal"),
            self._new_block("topic", width="half"),
            self._new_block("dataset_source", width="half"),
        ]
        blocks.extend(self._default_result_blocks(specs))
        blocks.append(self._new_block("conclusion", width="full", accent="teal"))
        return self._finalize_layout("poster", blocks)

    def _specs_from_chart_urls(
        self, chart_urls: list[str] | None, latest_synthesis_result_id: str | None
    ) -> list[dict]:
        specs: list[dict] = [{"kind": "analysis", "ref_id": "", "chart_urls": [], "label": "분석 결과", "caption": ""}]
        for url in self._unique_chart_urls(list(chart_urls or [])):
            specs.append({"kind": "chart", "ref_id": "", "chart_urls": [url], "label": "", "caption": ""})
        if latest_synthesis_result_id:
            specs.append(
                {
                    "kind": "synthesis",
                    "ref_id": latest_synthesis_result_id,
                    "chart_urls": [],
                    "label": "자료 종합 비교",
                    "caption": "",
                }
            )
        return specs

    def _default_result_blocks(self, specs: list[dict]) -> list[dict]:
        blocks: list[dict] = []
        for spec in specs:
            if spec["kind"] == "synthesis":
                blocks.append(
                    self._new_block("synthesis", ref_id=spec.get("ref_id", ""), text=spec.get("caption") or "")
                )
            elif spec["kind"] == "chart":
                blocks.append(
                    self._new_block(
                        "chart",
                        ref_id=(spec.get("chart_urls") or [""])[0],
                        title=spec.get("label") or "",
                        text=spec.get("caption") or "",
                    )
                )
            else:
                blocks.append(
                    self._new_block(
                        "analysis",
                        ref_id=spec.get("ref_id", ""),
                        title=spec.get("label") or "",
                        text=spec.get("caption") or "",
                    )
                )
        for index, block in enumerate(blocks):
            last_and_odd = index == len(blocks) - 1 and len(blocks) % 2 == 1
            block["width"] = "full" if len(blocks) <= 1 or last_and_odd else "half"
        return blocks

    def _migrate_layout_v1(self, layout: dict, report: Report) -> dict:
        items = layout.get("items") if isinstance(layout.get("items"), dict) else {}
        key_to_type = {
            "topic": "topic",
            "dataset": "dataset_source",
            "analysis": "analysis",
            "conclusion": "conclusion",
        }
        ordered_keys = sorted(
            (key for key in key_to_type if isinstance(items.get(key), dict) and items[key].get("include", True)),
            key=lambda key: items[key].get("order", 0),
        )
        blocks = [self._new_block(key_to_type[key], width="full") for key in ordered_keys]

        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        raw_selected = layout.get("selected_chart_urls")
        if isinstance(raw_selected, list):
            selected = self._unique_chart_urls(
                [resolved for url in raw_selected if (resolved := self._resolve_chart_ref(str(url), chart_urls))]
            )
        else:
            selected = chart_urls
        chart_width = "full" if len(selected) <= 1 else "half"
        chart_blocks = [self._new_block("chart", ref_id=url, width=chart_width) for url in selected]

        analysis_index = next((index for index, block in enumerate(blocks) if block["type"] == "analysis"), None)
        if analysis_index is not None:
            blocks[analysis_index + 1 : analysis_index + 1] = chart_blocks
        else:
            conclusion_index = next(
                (index for index, block in enumerate(blocks) if block["type"] == "conclusion"),
                len(blocks),
            )
            blocks[conclusion_index:conclusion_index] = chart_blocks

        return self._finalize_layout(str(layout.get("template") or "executive"), blocks)

    def _sanitize_layout(self, layout: dict, report: Report) -> dict:
        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        if not isinstance(layout, dict):
            return self.default_layout(chart_urls, topic_title=report.topic_title)
        has_pages = isinstance(layout.get("pages"), list)
        has_blocks = isinstance(layout.get("blocks"), list)
        if not has_pages and not has_blocks and "items" in layout:
            layout = self._migrate_layout_v1(layout, report)
            has_pages = True

        template = str(layout.get("template") or "poster")
        if template not in ALLOWED_TEMPLATES:
            template = "poster"
        theme = self._sanitize_theme(layout.get("theme"))
        context = self._layout_context(report)

        if has_pages:
            pages = self._sanitize_pages(layout.get("pages") or [], context)
        else:
            blocks = self._sanitize_flat_blocks(layout.get("blocks") or [], context)
            pages = self._auto_place(blocks)

        self._append_required_blocks(pages, context)
        order = 0
        for page in pages:
            for block in page["blocks"]:
                order += 1
                block["order"] = order
        return {"version": 3, "template": template, "paper": "a4", "theme": theme, "pages": pages}

    def _layout_context(self, report: Report) -> dict:
        return {
            "chart_urls": self._unique_chart_urls(list(report.chart_urls or [])),
            "analysis_ids": set(report.analysis_result_ids or []),
            "synthesis_ids": set(report.synthesis_result_ids or []),
            "placed_chart_keys": set(),
            "types": set(),
            "count": 0,
        }

    def _sanitize_flat_blocks(self, raw_blocks: list, context: dict) -> list[dict]:
        ordered = [raw for raw in raw_blocks[:200] if isinstance(raw, dict)]
        ordered.sort(key=lambda raw: self._block_order(raw))
        blocks: list[dict] = []
        for raw in ordered:
            block = self._sanitize_block(raw, context)
            if block is None:
                continue
            width = str(raw.get("width") or "full")
            if width not in ALLOWED_WIDTHS or block["type"] in {"heading", "divider"}:
                width = "full"
            block["width"] = width
            blocks.append(block)
        return blocks

    def _sanitize_pages(self, raw_pages: list, context: dict) -> list[dict]:
        pages: list[dict] = []
        for raw_page in raw_pages[:MAX_PAGES]:
            if not isinstance(raw_page, dict):
                continue
            raw_blocks = raw_page.get("blocks")
            if not isinstance(raw_blocks, list):
                raw_blocks = []
            blocks: list[dict] = []
            for raw in raw_blocks[:200]:
                if not isinstance(raw, dict):
                    continue
                block = self._sanitize_block(raw, context)
                if block is None:
                    continue
                block["x"], block["y"], block["w"], block["h"] = clamp_rect(
                    raw.get("x"), raw.get("y"), raw.get("w"), raw.get("h")
                )
                blocks.append(block)
            page_id = str(raw_page.get("page_id") or "")
            if not page_id.startswith("pg_"):
                page_id = f"pg_{uuid4().hex[:8]}"
            pages.append({"page_id": page_id, "blocks": blocks})
        return pages or [{"page_id": f"pg_{uuid4().hex[:8]}", "blocks": []}]

    def _sanitize_block(self, raw: dict, context: dict) -> dict | None:
        if context["count"] >= MAX_REPORT_BLOCKS:
            return None
        block_type = str(raw.get("type") or "")
        if block_type not in ALLOWED_BLOCK_TYPES:
            return None

        ref_id = str(raw.get("ref_id") or "")
        repeat = bool(raw.get("repeat"))
        if block_type == "chart":
            ref_id = self._resolve_chart_ref(ref_id, context["chart_urls"])
            if not ref_id:
                return None
            chart_key = self._chart_key(ref_id)
            if chart_key in context["placed_chart_keys"] and not repeat:
                return None
            context["placed_chart_keys"].add(chart_key)
        elif block_type == "analysis":
            if ref_id and ref_id not in context["analysis_ids"]:
                return None
        elif block_type == "synthesis":
            if ref_id and ref_id not in context["synthesis_ids"]:
                return None
        elif block_type == "image":
            ref_id = self._sanitize_image_ref(ref_id)
            if not ref_id:
                return None
        else:
            ref_id = ""

        if block_type in UNCAPTIONED_BLOCK_TYPES:
            title, text = "", ""
        else:
            title = str(raw.get("title") or "")[:MAX_BLOCK_TITLE]
            text = str(raw.get("text") or "")[:MAX_BLOCK_TEXT]

        accent = str(raw.get("accent") or "none")
        if accent not in ALLOWED_ACCENTS and accent != "custom":
            accent = "none"

        block_id = str(raw.get("block_id") or "")
        if not block_id.startswith("blk_"):
            block_id = f"blk_{uuid4().hex[:8]}"

        block = {
            "block_id": block_id,
            "type": block_type,
            "ref_id": ref_id,
            "title": title,
            "text": text,
            "accent": accent,
            "custom_color": normalize_hex_color(raw.get("custom_color"), DEFAULT_ACCENT_COLOR),
            "repeat": repeat and block_type == "chart",
            "order": self._block_order(raw),
        }
        if block_type == "image":
            source_kind = str(raw.get("source_kind") or "upload")
            block["source_kind"] = source_kind if source_kind in ALLOWED_IMAGE_SOURCES else "upload"
            block["alt_text"] = str(raw.get("alt_text") or "")[:MAX_BLOCK_TITLE]
            fit = str(raw.get("fit") or "contain")
            block["fit"] = fit if fit in ALLOWED_IMAGE_FITS else "contain"
        if block_type == "table":
            block["rows"] = self._sanitize_table_rows(raw.get("rows"))
            block["has_header"] = bool(raw.get("has_header", True))

        context["count"] += 1
        context["types"].add(block_type)
        return block

    def _sanitize_image_ref(self, ref_id: str) -> str:
        return ref_id if is_stored_image_url(ref_id) else ""

    def _sanitize_table_rows(self, raw_rows: object) -> list[list[str]]:
        if not isinstance(raw_rows, list):
            return [["", ""], ["", ""]]
        rows: list[list[str]] = []
        for raw_row in raw_rows[:MAX_TABLE_ROWS]:
            if not isinstance(raw_row, list):
                continue
            rows.append([str(cell or "")[:MAX_TABLE_CELL_TEXT] for cell in raw_row[:MAX_TABLE_COLS]])
        if not rows:
            return [["", ""], ["", ""]]
        width = max(len(row) for row in rows)
        return [row + [""] * (width - len(row)) for row in rows]

    def _append_required_blocks(self, pages: list[dict], context: dict) -> None:
        for required in REQUIRED_BLOCK_TYPES:
            if required in context["types"]:
                continue
            block = self._new_block(required, width="full")
            block.pop("width", None)
            rows = self._block_rows(block)
            page = pages[-1]
            top = max((item["y"] + item["h"] for item in page["blocks"]), default=0)
            if top + rows > PAGE_ROWS:
                if len(pages) < MAX_PAGES:
                    page = {"page_id": f"pg_{uuid4().hex[:8]}", "blocks": []}
                    pages.append(page)
                    top = 0
                else:
                    top = max(0, PAGE_ROWS - rows)
            block["x"], block["y"], block["w"], block["h"] = clamp_rect(0, top, GRID_COLS, rows)
            page["blocks"].append(block)
            context["types"].add(required)

    def _block_order(self, raw: dict) -> float:
        try:
            return float(raw.get("order", 0))
        except (TypeError, ValueError):
            return 0.0

    def export_pdf(self, report_id: str, user: User) -> bytes:
        report = self.get_report(report_id, user)
        return self._rich_pdf(report)

    def export_pptx(self, report_id: str, user: User) -> bytes:
        report = self.get_report(report_id, user)
        return self._rich_pptx(report)

    def _layout_pages(self, report: Report) -> list[dict]:
        layout = report.layout if isinstance(report.layout, dict) else {}
        pages = layout.get("pages")
        if isinstance(pages, list):
            return [page for page in pages if isinstance(page, dict)]
        blocks = layout.get("blocks")
        if isinstance(blocks, list):
            return [{"page_id": "pg_legacy", "blocks": [b for b in blocks if isinstance(b, dict)]}]
        return []

    def _layout_blocks(self, report: Report) -> list[dict]:
        blocks: list[dict] = []
        for page in self._layout_pages(report):
            raw = page.get("blocks")
            if isinstance(raw, list):
                blocks.extend(block for block in raw if isinstance(block, dict))
        return blocks

    def _selected_chart_urls(self, report: Report) -> list[str]:
        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        blocks = self._layout_blocks(report)
        if not blocks:
            layout = report.layout if isinstance(report.layout, dict) else {}
            raw = layout.get("selected_chart_urls")
            if not isinstance(raw, list):
                return chart_urls
            return [resolved for url in raw if (resolved := self._resolve_chart_ref(str(url), chart_urls))]
        ordered = sorted(blocks, key=lambda block: self._block_order(block))
        selected: list[str] = []
        seen: set[str] = set()
        for block in ordered:
            for url in self._block_chart_urls(block, report):
                key = self._chart_key(url)
                if key in seen:
                    continue
                seen.add(key)
                selected.append(url)
        return selected

    PDF_CARD_PADDING = 7

    def _rich_pdf(self, report: Report) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen.canvas import Canvas
        except ImportError as exc:
            raise AppError(
                "REPORT_EXPORT_DEPENDENCY_MISSING",
                "보고서 PDF 생성 패키지가 설치되어 있지 않습니다.",
                "`cd backend && python -m pip install -e .`를 실행한 뒤 다시 시도해 주세요.",
                500,
            ) from exc

        theme = self._report_theme(report)
        regular_font, bold_font = self._register_pdf_fonts(theme["font"])
        fonts = (regular_font, bold_font)
        styles = self._pdf_styles(regular_font, bold_font, theme)

        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=A4)
        canvas.setTitle(report.topic_title)
        pages = self._layout_pages(report) or [{"blocks": []}]
        for index, page in enumerate(pages):
            if index:
                canvas.showPage()
            self._pdf_draw_page(canvas, page, report, styles, fonts, theme)
        canvas.save()
        return buffer.getvalue()

    def _pdf_draw_page(
        self, canvas, page: dict, report: Report, styles: dict, fonts: tuple[str, str], theme: dict
    ) -> None:
        from reportlab.platypus import Frame

        raw_blocks = page.get("blocks")
        blocks = [block for block in raw_blocks if isinstance(block, dict)] if isinstance(raw_blocks, list) else []
        for block in sorted(blocks, key=lambda item: self._block_order(item)):
            left, bottom, width, height = self._pdf_block_rect(block)
            self._pdf_draw_block_chrome(canvas, block, (left, bottom, width, height), theme)
            inner_width = width - 2 * self.PDF_CARD_PADDING
            inner_height = height - 2 * self.PDF_CARD_PADDING
            if inner_width <= 0 or inner_height <= 0:
                continue
            flowables = self._pdf_block_flowables(
                block, report, styles, fonts, max_width=inner_width, max_height=inner_height
            )
            if not flowables:
                continue
            frame = Frame(
                left,
                bottom,
                width,
                height,
                leftPadding=self.PDF_CARD_PADDING,
                rightPadding=self.PDF_CARD_PADDING,
                topPadding=self.PDF_CARD_PADDING,
                bottomPadding=self.PDF_CARD_PADDING,
                showBoundary=0,
            )
            frame.addFromList(list(flowables), canvas)

    def _pdf_block_rect(self, block: dict) -> tuple[float, float, float, float]:
        from reportlab.lib.units import mm

        left_mm = PAGE_MARGIN_MM + int(block.get("x", 0)) * COL_WIDTH_MM
        top_mm = PAGE_MARGIN_MM + int(block.get("y", 0)) * ROW_HEIGHT_MM
        width_mm = max(int(block.get("w", 1)), 1) * COL_WIDTH_MM - CELL_GAP_MM
        height_mm = max(int(block.get("h", 1)), 1) * ROW_HEIGHT_MM - CELL_GAP_MM
        bottom_mm = PAGE_HEIGHT_MM - top_mm - height_mm
        return left_mm * mm, bottom_mm * mm, width_mm * mm, height_mm * mm

    def _pdf_draw_block_chrome(self, canvas, block: dict, rect: tuple, theme: dict) -> None:
        from reportlab.lib.colors import HexColor

        left, bottom, width, height = rect
        block_type = str(block.get("type") or "")
        accent = HexColor(self._block_accent_color(block, theme))
        if block_type == "divider":
            canvas.setStrokeColor(accent)
            canvas.setLineWidth(0.9)
            canvas.line(left, bottom + height / 2, left + width, bottom + height / 2)
            return
        if block_type == "heading":
            canvas.setStrokeColor(accent)
            canvas.setLineWidth(2.2)
            canvas.line(left, bottom + 2, left + width, bottom + 2)
            return
        canvas.setFillColor(HexColor("#f2f7f6") if block_type == "highlight" else HexColor("#f7faf9"))
        canvas.rect(left, bottom, width, height, stroke=0, fill=1)
        canvas.setFillColor(accent)
        canvas.rect(left, bottom, 3, height, stroke=0, fill=1)

    def _flowables_height(self, flowables: list, width: float) -> float:
        total = 0.0
        for flowable in flowables:
            try:
                total += flowable.wrap(width, 0)[1]
            except Exception:
                total += 12
        return total

    def _block_heading_text(self, block: dict) -> str:
        title = str(block.get("title") or "").strip()
        return title or BLOCK_DEFAULT_TITLES.get(str(block.get("type")), "")

    def _report_theme(self, report: Report) -> dict:
        layout = report.layout if isinstance(report.layout, dict) else {}
        return self._sanitize_theme(layout.get("theme"))

    def _block_accent_color(self, block: dict, theme: dict | None = None) -> str:
        accent = str(block.get("accent") or "none")
        if accent == "custom":
            return normalize_hex_color(block.get("custom_color"), (theme or {}).get("accent") or DEFAULT_ACCENT_COLOR)
        if accent == "none" and theme:
            return ACCENT_COLORS["none"]
        return ACCENT_COLORS.get(accent, ACCENT_COLORS["none"])

    def _pdf_heading(self, block: dict, styles: dict, fallback: str = ""):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        text = self._block_heading_text(block) or fallback
        if not text:
            return None
        style = styles["heading"]
        accent = str(block.get("accent") or "none")
        if accent != "none":
            color = self._block_accent_color(block, styles.get("_theme"))
            style = ParagraphStyle("HeadingAccent", parent=style, textColor=HexColor(color))
        return Paragraph(html_escape(text), style)

    def _pdf_caption(self, block: dict, styles: dict) -> list:
        from reportlab.platypus import Paragraph

        text = str(block.get("text") or "").strip()
        return [Paragraph(html_escape(text), styles["caption"])] if text else []

    def _pdf_block_flowables(
        self,
        block: dict,
        report: Report,
        styles: dict,
        fonts: tuple[str, str],
        max_width: float,
        max_height: float,
    ) -> list:
        from reportlab.platypus import Paragraph

        block_type = block.get("type")
        heading = self._pdf_heading(block, styles)
        if block_type == "heading":
            return self._pdf_poster_heading_flowables(block, styles, max_width)
        if block_type == "divider":
            return []
        if block_type == "highlight":
            return self._pdf_highlight_flowables(block, styles, fonts, max_width)
        if block_type == "topic":
            return [
                *([heading] if heading else []),
                Paragraph(html_escape(report.topic_title), styles["body"]),
                *self._pdf_caption(block, styles),
            ]
        if block_type == "dataset_source":
            return [
                *([heading] if heading else []),
                *self._pdf_dataset_table(report, styles, fonts, max_width=max_width),
                *self._pdf_caption(block, styles),
            ]
        if block_type == "analysis":
            return self._pdf_analysis_flowables(block, report, styles, max_width, max_height)
        if block_type == "chart":
            return self._pdf_chart_block_flowables(block, report, styles, max_width, max_height)
        if block_type == "image":
            return self._pdf_image_block_flowables(block, styles, max_width, max_height)
        if block_type == "table":
            return self._pdf_table_block_flowables(block, styles, fonts, max_width)
        if block_type == "text_note":
            return [
                *([heading] if heading else []),
                Paragraph(html_escape(str(block.get("text") or "")), styles["body"]),
            ]
        if block_type == "synthesis":
            return self._pdf_synthesis_flowables(block, report, styles, max_width, max_height)
        if block_type == "conclusion":
            return [
                *([heading] if heading else []),
                Paragraph(html_escape(report.conclusion_text or "아직 결론을 쓰지 않았습니다."), styles["body"]),
                *self._pdf_caption(block, styles),
            ]
        return []

    def _pdf_scaled_image(self, content: bytes, max_width: float, max_height: float):
        from PIL import Image as PilImage
        from reportlab.platypus import Image

        if max_width <= 0 or max_height <= 0:
            return None
        width_px, height_px = PilImage.open(BytesIO(content)).size
        if not width_px or not height_px:
            return None
        scale = min(max_width / width_px, max_height / height_px)
        return Image(BytesIO(content), width=width_px * scale, height=height_px * scale)

    def _pdf_chart_images(self, block: dict, report: Report, max_width: float, max_height: float) -> list:
        flowables: list = []
        urls = self._block_chart_urls(block, report)[:2]
        if not urls or max_height <= 0:
            return []
        each_height = max_height / len(urls)
        for url in urls:
            source = self._chart_source_for_url(url)
            if not source:
                continue
            image = self._pdf_scaled_image(source["content"], max_width, each_height)
            if image is not None:
                flowables.append(image)
        return flowables

    def _pdf_interpretation(self, block: dict, report: Report, styles: dict) -> list:
        from reportlab.platypus import Paragraph

        text = self._block_interpretation(block, report)
        if not text:
            return []
        return [
            Paragraph("내 해석", styles["highlight_title"]),
            Paragraph(html_escape(text), styles["body"]),
        ]

    def _pdf_poster_heading_flowables(self, block: dict, styles: dict, width: float) -> list:
        from reportlab.platypus import Paragraph

        flowables: list = []
        eyebrow = str(block.get("text") or "").strip()
        if eyebrow:
            flowables.append(Paragraph(html_escape(eyebrow), styles["eyebrow"]))
        title = str(block.get("title") or "").strip()
        if title:
            flowables.append(Paragraph(html_escape(title), styles["section_title"]))
        return flowables

    def _pdf_grid_table(
        self,
        cells: list[list[str]],
        styles: dict,
        fonts: tuple[str, str],
        max_width: float,
        has_header: bool = True,
    ):
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Table, TableStyle

        regular_font, bold_font = fonts
        col_count = max(len(row) for row in cells)
        data = [
            [Paragraph(html_escape(str(cell)), styles["table"]) for cell in row]
            + [Paragraph("", styles["table"])] * (col_count - len(row))
            for row in cells
        ]
        table = Table(data, colWidths=[max_width / col_count] * col_count, hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, -1), regular_font),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5d1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if has_header:
            style.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f0ee")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173f3d")),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7faf9")]),
                ]
            )
        table.setStyle(TableStyle(style))
        return table

    def _pdf_highlight_flowables(self, block: dict, styles: dict, fonts: tuple[str, str], width: float) -> list:
        from reportlab.lib import colors
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import Paragraph, Table, TableStyle

        accent = HexColor(self._block_accent_color(block))
        inner = []
        heading_text = self._block_heading_text(block)
        if heading_text:
            inner.append(Paragraph(html_escape(heading_text), styles["highlight_title"]))
        body = str(block.get("text") or "").strip()
        if body:
            inner.append(Paragraph(html_escape(body), styles["highlight_body"]))
        if not inner:
            return []
        table = Table([[inner]], colWidths=[width], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f7f6")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return [table]

    def _pdf_dataset_table(self, report: Report, styles: dict, fonts: tuple[str, str], max_width: float) -> list:
        from reportlab.platypus import Paragraph

        if not report.dataset_sources:
            return [Paragraph("자료 출처 정보가 없습니다.", styles["body"])]
        cells = [["자료", "출처", "범위", "설명"]]
        for source in report.dataset_sources:
            scope = " · ".join(str(part) for part in [source.get("time_range"), source.get("geographic_unit")] if part)
            cells.append(
                [
                    str(source.get("name") or "-"),
                    str(source.get("source") or "출처 확인 필요"),
                    scope or "확인 필요",
                    str(source.get("source_note") or source.get("description") or "-"),
                ]
            )
        return [self._pdf_grid_table(cells, styles, fonts, max_width, has_header=True)]

    def _pdf_analysis_flowables(
        self, block: dict, report: Report, styles: dict, max_width: float, max_height: float
    ) -> list:
        from reportlab.platypus import Paragraph

        ref_id = block.get("ref_id")
        if not ref_id:
            heading = self._pdf_heading(block, styles, fallback="분석")
            return [
                *([heading] if heading else []),
                Paragraph(html_escape(self._analysis_export_summary(report)), styles["body"]),
                *self._pdf_caption(block, styles),
            ]
        summary = self._analysis_result_by_id(report, ref_id)
        if summary is None:
            heading = self._pdf_heading(block, styles, fallback="분석")
            return [
                *([heading] if heading else []),
                Paragraph("분석 결과를 찾을 수 없습니다.", styles["body"]),
            ]
        function_name = (summary.get("metadata") or {}).get("function") or ""
        heading = self._pdf_heading(block, styles, fallback=f"분석: {function_name}" if function_name else "분석")
        text_flowables = [
            *([heading] if heading else []),
            *self._pdf_caption(block, styles),
            *self._pdf_interpretation(block, report, styles),
        ]
        remaining = max_height - self._flowables_height(text_flowables, max_width)
        images = self._pdf_chart_images(block, report, max_width, remaining)
        body = "" if images else self._analysis_result_summary_text(summary)
        return [
            *([heading] if heading else []),
            *images,
            *([Paragraph(html_escape(body), styles["body"])] if body else []),
            *self._pdf_caption(block, styles),
            *self._pdf_interpretation(block, report, styles),
        ]

    def _pdf_chart_block_flowables(
        self, block: dict, report: Report, styles: dict, max_width: float, max_height: float
    ) -> list:
        from reportlab.platypus import Paragraph

        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        ref_id = self._resolve_chart_ref(str(block.get("ref_id") or ""), chart_urls)
        index = chart_urls.index(ref_id) + 1 if ref_id in chart_urls else 0
        source = self._chart_source_for_url(ref_id) if ref_id else None
        heading = self._pdf_heading(block, styles, fallback=f"그래프 {index}" if index else "그래프")
        if not source:
            return [
                *([heading] if heading else []),
                Paragraph("그래프 이미지를 불러올 수 없습니다.", styles["body"]),
            ]
        text_flowables = [
            *([heading] if heading else []),
            *self._pdf_caption(block, styles),
            *self._pdf_interpretation(block, report, styles),
        ]
        remaining = max_height - self._flowables_height(text_flowables, max_width)
        image = self._pdf_scaled_image(source["content"], max_width, remaining)
        return [
            *([heading] if heading else []),
            *([image] if image is not None else []),
            *self._pdf_caption(block, styles),
            *self._pdf_interpretation(block, report, styles),
        ]

    def _pdf_image_block_flowables(self, block: dict, styles: dict, max_width: float, max_height: float) -> list:
        from reportlab.platypus import Paragraph

        heading = self._pdf_heading(block, styles)
        content = self._read_report_image(str(block.get("ref_id") or ""))
        if not content:
            return [
                *([heading] if heading else []),
                Paragraph("그림을 불러올 수 없습니다.", styles["body"]),
            ]
        text_flowables = [*([heading] if heading else []), *self._pdf_caption(block, styles)]
        remaining = max_height - self._flowables_height(text_flowables, max_width)
        image = self._pdf_scaled_image(content, max_width, remaining)
        if image is None:
            return [
                *([heading] if heading else []),
                Paragraph("그림 형식을 읽을 수 없습니다.", styles["body"]),
            ]
        return [
            *([heading] if heading else []),
            image,
            *self._pdf_caption(block, styles),
        ]

    def _pdf_table_block_flowables(self, block: dict, styles: dict, fonts: tuple[str, str], max_width: float) -> list:
        from reportlab.platypus import Paragraph

        heading = self._pdf_heading(block, styles)
        rows = block.get("rows") if isinstance(block.get("rows"), list) else []
        cells = [[str(cell or "") for cell in row] for row in rows if isinstance(row, list) and row]
        if not cells:
            return [
                *([heading] if heading else []),
                Paragraph("표 내용이 비어 있습니다.", styles["body"]),
            ]
        table = self._pdf_grid_table(cells, styles, fonts, max_width, has_header=bool(block.get("has_header", True)))
        return [
            *([heading] if heading else []),
            table,
            *self._pdf_caption(block, styles),
        ]

    def _pdf_synthesis_flowables(
        self, block: dict, report: Report, styles: dict, max_width: float, max_height: float
    ) -> list:
        from reportlab.platypus import Paragraph

        ref_id = block.get("ref_id")
        getter = getattr(self.repo, "get_synthesis_result", None)
        synthesis = getter(ref_id) if getter and ref_id else None
        heading = self._pdf_heading(block, styles, fallback="자료 종합 비교")
        if not synthesis:
            return [
                *([heading] if heading else []),
                Paragraph("종합 비교 결과를 찾을 수 없습니다.", styles["body"]),
            ]
        dataset_ids = set(synthesis.dataset_ids)
        dataset_names = (
            ", ".join(
                source.get("name", "") for source in report.dataset_sources if source.get("dataset_id") in dataset_ids
            )
            or "결합 자료"
        )
        source_line = Paragraph(html_escape(f"사용 자료: {dataset_names}"), styles["body"])
        text_flowables = [*([heading] if heading else []), source_line, *self._pdf_caption(block, styles)]
        remaining = max_height - self._flowables_height(text_flowables, max_width)
        images = self._pdf_chart_images(block, report, max_width, remaining)
        return [
            *([heading] if heading else []),
            source_line,
            *images,
            *(
                []
                if images
                else [Paragraph(html_escape(self._analysis_result_summary_text(synthesis.result)), styles["body"])]
            ),
            *self._pdf_caption(block, styles),
        ]

    def _analysis_result_by_id(self, report: Report, ref_id: str) -> dict | None:
        ids = report.analysis_result_ids or []
        summaries = report.analysis_summaries or []
        for analysis_id, summary in zip(ids, summaries, strict=False):
            if analysis_id == ref_id:
                return summary
        return None

    def _analysis_record(self, report: Report, ref_id: str):
        if not ref_id or ref_id not in set(report.analysis_result_ids or []):
            return None
        return self.repo.get_analysis_result(ref_id)

    def _block_chart_urls(self, block: dict, report: Report) -> list[str]:
        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        block_type = str(block.get("type") or "")
        ref_id = str(block.get("ref_id") or "")
        if block_type == "chart":
            resolved = self._resolve_chart_ref(ref_id, chart_urls)
            return [resolved] if resolved else []
        if block_type == "analysis":
            record = self._analysis_record(report, ref_id)
            source_urls = record.chart_urls if record else []
        elif block_type == "synthesis":
            getter = getattr(self.repo, "get_synthesis_result", None)
            synthesis = getter(ref_id) if getter and ref_id else None
            source_urls = synthesis.chart_urls if synthesis else []
        else:
            return []
        return [
            resolved
            for url in self._unique_chart_urls(list(source_urls or []))
            if (resolved := self._resolve_chart_ref(url, chart_urls))
        ]

    def _chart_owner_record(self, report: Report, ref_id: str):
        chart_urls = self._unique_chart_urls(list(report.chart_urls or []))
        resolved = self._resolve_chart_ref(ref_id, chart_urls)
        if not resolved:
            return None
        for analysis_id in report.analysis_result_ids or []:
            record = self.repo.get_analysis_result(analysis_id)
            if record is None:
                continue
            if any(self._resolve_chart_ref(url, chart_urls) == resolved for url in record.chart_urls or []):
                return record
        return None

    def _block_interpretation(self, block: dict, report: Report) -> str:
        ref_id = str(block.get("ref_id") or "")
        if str(block.get("type") or "") == "chart":
            record = self._chart_owner_record(report, ref_id)
        else:
            record = self._analysis_record(report, ref_id)
        return (record.interpretation or "").strip() if record else ""

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

    def _statistics_line(self, statistics: dict) -> str:
        parts = [
            f"{self.STAT_LABELS_KO.get(key, key)} {value}"
            for key, value in statistics.items()
            if not isinstance(value, (dict, list))
        ]
        return ", ".join(parts)

    def _grouped_statistics_text(self, data: dict) -> str:
        groups = data.get("groups")
        group_by = data.get("group_by")
        if not group_by or not isinstance(groups, list) or not groups:
            return ""
        columns = data.get("columns") or list((groups[0].get("statistics") or {}).keys())
        lines = []
        for column in columns:
            entries = []
            for group in groups:
                statistics = (group.get("statistics") or {}).get(column) or {}
                line = self._statistics_line(statistics)
                if line:
                    entries.append(f"{group.get('group')}(n={group.get('sample_sizes', {}).get(column, '')}) {line}")
            if entries:
                lines.append(f"{column} · " + " / ".join(entries))
        if not lines:
            return ""
        return f"{group_by} 집단별 비교 — " + " ; ".join(lines)

    def _analysis_result_summary_text(self, result: dict) -> str:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            return "그래프 등 시각 자료로 표현된 결과입니다."
        grouped = self._grouped_statistics_text(data)
        if grouped:
            return grouped
        statistics = data.get("statistics")
        if isinstance(statistics, dict) and statistics:
            lines = [
                f"{column} · {self._statistics_line(values)}"
                for column, values in statistics.items()
                if isinstance(values, dict) and self._statistics_line(values)
            ]
            if lines:
                return " ; ".join(lines)
        parts = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                continue
            parts.append(f"{key}: {value}")
            if len(parts) >= 6:
                break
        return ", ".join(parts) if parts else "그래프 등 시각 자료로 표현된 결과입니다."

    def _chart_source_for_url(self, url: str) -> dict | None:
        for candidate in self._image_url_candidates(url):
            content = self._read_chart_image(candidate)
            if content:
                return {"url": candidate, "content": content}
        return None

    def _rich_pptx(self, report: Report) -> bytes:
        try:
            from pptx import Presentation
            from pptx.util import Mm
        except ImportError as exc:
            raise AppError(
                "REPORT_EXPORT_DEPENDENCY_MISSING",
                "보고서 PPTX 생성 패키지가 설치되어 있지 않습니다.",
                "`cd backend && python -m pip install -e .`를 실행한 뒤 다시 시도해 주세요.",
                500,
            ) from exc

        theme = self._report_theme(report)
        font_name = self._office_font_name(theme["font"])
        presentation = Presentation()
        presentation.slide_width = Mm(PAGE_WIDTH_MM)
        presentation.slide_height = Mm(PAGE_HEIGHT_MM)

        for page in self._layout_pages(report) or [{"blocks": []}]:
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            raw_blocks = page.get("blocks")
            blocks = [b for b in raw_blocks if isinstance(b, dict)] if isinstance(raw_blocks, list) else []
            for block in sorted(blocks, key=lambda item: self._block_order(item)):
                self._add_pptx_block(slide, block, report, font_name, theme)

        output = BytesIO()
        presentation.save(output)
        return output.getvalue()

    def _pptx_block_rect(self, block: dict) -> tuple:
        from pptx.util import Mm

        left = PAGE_MARGIN_MM + int(block.get("x", 0)) * COL_WIDTH_MM
        top = PAGE_MARGIN_MM + int(block.get("y", 0)) * ROW_HEIGHT_MM
        width = max(int(block.get("w", 1)), 1) * COL_WIDTH_MM - CELL_GAP_MM
        height = max(int(block.get("h", 1)), 1) * ROW_HEIGHT_MM - CELL_GAP_MM
        return Mm(left), Mm(top), Mm(width), Mm(height)

    def _add_pptx_block(self, slide, block: dict, report: Report, font_name: str, theme: dict) -> None:
        left, top, width, height = self._pptx_block_rect(block)
        block_type = str(block.get("type") or "")
        if block_type == "divider":
            return
        if block_type == "table":
            self._add_pptx_table_block(slide, block, font_name, (left, top, width, height))
            return

        image_content = self._pptx_block_image(block, report)
        title = self._block_heading_text(block)
        lines = [] if image_content else self._pptx_block_lines(block, report)
        caption = str(block.get("text") or "").strip()
        if image_content:
            interpretation = self._block_interpretation(block, report)
            lines = [
                *([caption] if caption else []),
                *([f"내 해석: {interpretation}"] if interpretation else []),
            ]

        if title:
            self._add_pptx_text(slide, left, top, width, font_name, [title], size=13, bold=True, theme=theme)
        body_top = top + (_mm(6) if title else 0)
        body_height = max(height - (_mm(6) if title else 0), _mm(4))
        if image_content:
            self._add_pptx_picture(slide, image_content, left, body_top, width, body_height, lines, font_name)
        elif lines:
            self._add_pptx_text(slide, left, body_top, width, font_name, lines, size=10)

    def _pptx_block_image(self, block: dict, report: Report) -> bytes | None:
        block_type = str(block.get("type") or "")
        if block_type == "image":
            return self._read_report_image(str(block.get("ref_id") or ""))
        if block_type not in {"chart", "analysis", "synthesis"}:
            return None
        url = next(iter(self._block_chart_urls(block, report)), "")
        source = self._chart_source_for_url(url) if url else None
        return source["content"] if source else None

    def _pptx_block_lines(self, block: dict, report: Report) -> list[str]:
        block_type = str(block.get("type") or "")
        caption = str(block.get("text") or "").strip()
        if block_type == "topic":
            return [report.topic_title, *([caption] if caption else [])]
        if block_type == "dataset_source":
            return [*self._dataset_export_lines(report), *(["", caption] if caption else [])]
        if block_type == "conclusion":
            return [
                report.conclusion_text or "아직 결론을 쓰지 않았습니다.",
                *(["", caption] if caption else []),
            ]
        if block_type == "analysis":
            ref_id = block.get("ref_id")
            summary = self._analysis_result_by_id(report, ref_id) if ref_id else None
            base = (
                self._analysis_result_summary_text(summary)
                if summary is not None
                else self._analysis_export_summary(report)
            )
            interpretation = self._block_interpretation(block, report)
            return [
                base,
                *(["", caption] if caption else []),
                *(["", f"내 해석: {interpretation}"] if interpretation else []),
            ]
        if block_type == "synthesis":
            getter = getattr(self.repo, "get_synthesis_result", None)
            synthesis = getter(block.get("ref_id")) if getter and block.get("ref_id") else None
            if not synthesis:
                return ["종합 비교 결과를 찾을 수 없습니다."]
            return [
                self._analysis_result_summary_text(synthesis.result),
                *(["", caption] if caption else []),
            ]
        if block_type == "chart":
            interpretation = self._block_interpretation(block, report)
            return [
                *([caption] if caption else []),
                *([f"내 해석: {interpretation}"] if interpretation else []),
            ]
        return [caption] if caption else []

    def _add_pptx_table_block(self, slide, block: dict, font_name: str, rect: tuple) -> None:
        from pptx.util import Pt

        left, top, width, height = rect
        rows = [row for row in (block.get("rows") or []) if isinstance(row, list) and row]
        if not rows:
            return
        col_count = max(len(row) for row in rows)
        shape = slide.shapes.add_table(len(rows), col_count, left, top, width, height)
        for row_index, row in enumerate(rows):
            for col_index in range(col_count):
                cell = shape.table.cell(row_index, col_index)
                cell.text = str(row[col_index]) if col_index < len(row) else ""
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = font_name
                        run.font.size = Pt(9)

    def _add_pptx_picture(
        self, slide, content: bytes, left, top, width, height, caption_lines: list[str], font_name: str
    ) -> None:
        from PIL import Image as PilImage

        caption_height = _mm(6) * len(caption_lines) if caption_lines else 0
        picture_height = max(height - caption_height, _mm(4))
        image = PilImage.open(BytesIO(content))
        if not image.width or not image.height:
            return
        scale = min(width / image.width, picture_height / image.height)
        draw_width = int(image.width * scale)
        draw_height = int(image.height * scale)
        slide.shapes.add_picture(
            BytesIO(content),
            int(left + (width - draw_width) / 2),
            int(top),
            width=draw_width,
            height=draw_height,
        )
        if caption_lines:
            self._add_pptx_text(slide, left, int(top + draw_height), width, font_name, caption_lines, size=9)

    def _add_pptx_text(
        self,
        slide,
        left,
        top,
        width,
        font_name: str,
        lines: list[str],
        size: int,
        bold: bool = False,
        theme: dict | None = None,
    ) -> None:
        box = slide.shapes.add_textbox(left, top, width, _mm(6) * max(len(lines), 1))
        self._fill_pptx_text(box.text_frame, lines, font_name, size=size, bold=bold, theme=theme)

    def _pdf_styles(self, regular_font: str, bold_font: str, theme: dict | None = None) -> dict[str, object]:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.styles import ParagraphStyle

        theme = theme or self._sanitize_theme(None)
        primary = HexColor(theme["primary"])
        accent = HexColor(theme["accent"])
        return {
            "_theme": theme,
            "eyebrow": ParagraphStyle(
                "Eyebrow",
                fontName=bold_font,
                fontSize=9,
                leading=12,
                textColor=accent,
                spaceAfter=2,
            ),
            "title": ParagraphStyle(
                "Title",
                fontName=bold_font,
                fontSize=18,
                leading=24,
                textColor=primary,
                spaceAfter=10,
            ),
            "heading": ParagraphStyle(
                "Heading",
                fontName=bold_font,
                fontSize=12,
                leading=17,
                textColor=primary,
                spaceBefore=4,
                spaceAfter=5,
            ),
            "body": ParagraphStyle(
                "Body",
                fontName=regular_font,
                fontSize=10,
                leading=15,
                textColor=HexColor("#24302f"),
                spaceAfter=4,
            ),
            "table": ParagraphStyle(
                "Table",
                fontName=regular_font,
                fontSize=8,
                leading=11,
                textColor=HexColor("#24302f"),
            ),
            "caption": ParagraphStyle(
                "Caption",
                fontName=regular_font,
                fontSize=8.5,
                leading=12,
                textColor=HexColor("#52605d"),
                spaceBefore=3,
                spaceAfter=3,
            ),
            "section_title": ParagraphStyle(
                "SectionTitle",
                fontName=bold_font,
                fontSize=15,
                leading=20,
                textColor=primary,
                spaceAfter=3,
            ),
            "highlight_title": ParagraphStyle(
                "HighlightTitle",
                fontName=bold_font,
                fontSize=11,
                leading=15,
                textColor=primary,
                spaceAfter=3,
            ),
            "highlight_body": ParagraphStyle(
                "HighlightBody",
                fontName=regular_font,
                fontSize=10,
                leading=15,
                textColor=HexColor("#24302f"),
            ),
        }

    def _register_pdf_fonts(self, font_key: str = "") -> tuple[str, str]:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        key = normalize_font_key(font_key)
        spec = REPORT_FONTS[key]
        regular_path = self._first_existing_font(spec["regular"])
        if not regular_path and key != DEFAULT_FONT_KEY:
            key = DEFAULT_FONT_KEY
            spec = REPORT_FONTS[key]
            regular_path = self._first_existing_font(spec["regular"])
        if not regular_path:
            return "Helvetica", "Helvetica-Bold"
        bold_path = self._first_existing_font([*spec["bold"], str(regular_path)])

        regular_name = f"StatAgent-{key}"
        bold_name = f"StatAgent-{key}-Bold" if bold_path else regular_name
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_path and bold_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        return regular_name, bold_name

    def _office_font_name(self, font_key: str = "") -> str:
        spec = REPORT_FONTS[normalize_font_key(font_key)]
        candidates = [*spec["regular"], *spec["bold"]]
        if self._first_existing_font(candidates):
            return spec["office"][0]
        return spec["office"][-1]

    def _read_report_image(self, url: str) -> bytes | None:
        if not is_stored_image_url(url):
            return None
        path = local_image_path(url)
        if path and path.exists():
            return path.read_bytes()
        if url.startswith("https://"):
            try:
                request = Request(url, headers={"User-Agent": "stat-agent-report-export/1.0"})
                with urlopen(request, timeout=10) as response:
                    return response.read()
            except OSError:
                return None
        return None

    def _first_existing_font(self, candidates: list[str]) -> Path | None:
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.exists():
                return path
        return None

    def _dataset_export_lines(self, report: Report) -> list[str]:
        if not report.dataset_sources:
            return ["자료 출처 정보가 없습니다."]
        lines = []
        for source in report.dataset_sources:
            scope = " · ".join(str(part) for part in [source.get("time_range"), source.get("geographic_unit")] if part)
            lines.append(
                f"{source.get('name', '자료')}: {source.get('source', '출처 확인 필요')}"
                f"{f' ({scope})' if scope else ''}"
            )
            note = source.get("source_note") or source.get("description")
            if note:
                lines.append(f"  - {note}")
        return lines

    def _analysis_export_summary(self, report: Report) -> str:
        analysis_count = len(
            report.analysis_summaries or ([report.analysis_summary] if report.analysis_summary else [])
        )
        chart_count = len(self._selected_chart_sources(report))
        return f"분석 결과 {analysis_count}건을 보고서에 포함했고, 선택한 그래프 {chart_count}개를 함께 제시합니다."

    def _selected_chart_sources(self, report: Report) -> list[dict]:
        sources = []
        seen = set()
        for url in self._selected_chart_urls(report):
            for candidate in self._image_url_candidates(url):
                key = self._chart_key(candidate)
                if key in seen:
                    break
                content = self._read_chart_image(candidate)
                if content:
                    seen.add(key)
                    sources.append(
                        {
                            "url": candidate,
                            "content": content,
                            "label": f"{Path(urlparse(candidate).path).name or 'chart'}",
                        }
                    )
                    break
        return sources

    def _image_url_candidates(self, url: str) -> list[str]:
        parsed = urlparse(url)
        path = parsed.path or url
        suffix = Path(path).suffix.lower()
        candidates = []
        if suffix == ".svg":
            png_path = path[: -len(suffix)] + ".png"
            if parsed.scheme:
                candidates.append(parsed._replace(path=png_path).geturl())
            else:
                candidates.append(png_path)
        candidates.append(url)
        return candidates

    def _chart_key(self, url: str) -> str:
        path = urlparse(url).path or url
        return Path(path).stem or url

    def _read_chart_image(self, url: str) -> bytes | None:
        path = urlparse(url).path or url
        if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            return None
        local_path = self._local_chart_path(url)
        if local_path and local_path.exists():
            return local_path.read_bytes()
        if url.startswith(("http://", "https://")):
            try:
                request = Request(url, headers={"User-Agent": "stat-agent-report-export/1.0"})
                with urlopen(request, timeout=10) as response:
                    return response.read()
            except OSError:
                return None
        return None

    def _local_chart_path(self, url: str) -> Path | None:
        parsed = urlparse(url)
        path = unquote(parsed.path if parsed.scheme else url)
        marker = "/static/charts/"
        if marker not in path:
            return None
        filename = Path(path).name
        if not filename:
            return None
        return get_settings().local_chart_dir / filename

    def _fill_pptx_text(
        self,
        text_frame,
        lines: list[str],
        font_name: str,
        size: int,
        bold: bool = False,
        theme: dict | None = None,
    ) -> None:
        from pptx.dml.color import RGBColor
        from pptx.util import Pt

        color = RGBColor.from_string((theme["primary"] if theme and bold else "#24302f").lstrip("#").upper())
        text_frame.clear()
        text_frame.word_wrap = True
        for index, line in enumerate(lines):
            paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
            paragraph.space_after = Pt(3)
            run = paragraph.add_run()
            run.text = line
            run.font.name = font_name
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
