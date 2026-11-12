from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])


class ConclusionRequest(BaseModel):
    conclusion_text: str


class FeedbackRequest(BaseModel):
    feedback_text: str


class ReportLayoutRequest(BaseModel):
    layout: dict


class ReflectionRequest(BaseModel):
    reflection: dict


class ReportImageLinkRequest(BaseModel):
    external_url: str = Field(..., min_length=1, max_length=2000)


@router.post("/api/projects/{project_id}/conclusion")
def submit_conclusion(
    project_id: str,
    payload: ConclusionRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    report = ReportService().submit_conclusion(project_id, payload.conclusion_text, user)
    return success_response(report.model_dump(mode="json"))


@router.patch("/api/projects/{project_id}/conclusion")
def update_conclusion(
    project_id: str,
    payload: ConclusionRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    report = ReportService().update_conclusion(project_id, payload.conclusion_text, user)
    return success_response(report.model_dump(mode="json"))


@router.get("/api/reports")
def list_reports(user: User = Depends(require_any_role(["student", "teacher", "admin"]))) -> dict:
    reports = [report.model_dump(mode="json") for report in ReportService().list_reports(user)]
    return success_response(reports, {"count": len(reports)})


@router.get("/api/reports/{report_id}")
def get_report(
    report_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    report = ReportService().get_report(report_id, user)
    return success_response(report.model_dump(mode="json"))


@router.patch("/api/reports/{report_id}/layout")
def save_report_layout(
    report_id: str,
    payload: ReportLayoutRequest,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    report = ReportService().save_layout(report_id, payload.layout, user)
    return success_response(report.model_dump(mode="json"))


@router.post("/api/reports/{report_id}/images")
async def upload_report_image(
    report_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    content = await file.read()
    url = ReportService().add_image(
        report_id, user, content=content, filename=file.filename, content_type=file.content_type
    )
    return success_response({"url": url, "source_kind": "upload"})


@router.post("/api/reports/{report_id}/images/link")
def link_report_image(
    report_id: str,
    payload: ReportImageLinkRequest,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> dict:
    url = ReportService().add_image(report_id, user, external_url=payload.external_url)
    return success_response({"url": url, "source_kind": "external"})


@router.get("/api/reports/{report_id}/export.pdf")
def export_report_pdf(
    report_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> Response:
    content = ReportService().export_pdf(report_id, user)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'},
    )


@router.get("/api/reports/{report_id}/export.pptx")
def export_report_pptx(
    report_id: str,
    user: User = Depends(require_any_role(["student", "teacher", "admin"])),
) -> Response:
    content = ReportService().export_pptx(report_id, user)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.pptx"'},
    )


@router.patch("/api/reports/{report_id}/reflection")
def save_reflection(
    report_id: str,
    payload: ReflectionRequest,
    user: User = Depends(require_role("student")),
) -> dict:
    report = ReportService().save_reflection(report_id, payload.reflection, user)
    return success_response(report.model_dump(mode="json"))


@router.post("/api/reports/{report_id}/feedback")
def save_feedback(
    report_id: str,
    payload: FeedbackRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    report = ReportService().save_feedback(report_id, payload.feedback_text, user)
    return success_response(report.model_dump(mode="json"))
