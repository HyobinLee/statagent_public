from datetime import UTC, datetime, timedelta

from app.core.errors import success_response
from app.dependencies import require_any_role, require_role
from app.models.user import User
from app.repositories.factory import get_repository
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from lessons_app.services import gg_library, kosis_private_edu, neis_meal, schools, tracks
from lessons_app.services.connector_provisioning import provision_connector_dataset
from lessons_app.services.lesson_defs import get_lesson_def_for_track
from lessons_app.services.progress import connector_key as connector_setting_key
from lessons_app.services.provisioning import ensure_lesson_project

router = APIRouter(prefix="/api/lessons", tags=["lesson-connectors"])

LESSON2_ID = "lesson2"
NEIS_LOOKBACK_DAYS = 30


@router.get("/connectors/school")
def get_school(user: User = Depends(require_any_role(["student", "teacher", "admin"]))) -> dict:
    return success_response({"current": schools.get_current_school(), "options": schools.FIXED_SCHOOLS})


class SetSchoolRequest(BaseModel):
    school_id: str


@router.post("/connectors/school")
def set_school(
    payload: SetSchoolRequest,
    user: User = Depends(require_any_role(["teacher", "admin"])),
) -> dict:
    school = schools.set_current_school(payload.school_id)
    return success_response({"current": school, "options": schools.FIXED_SCHOOLS})


@router.post("/connectors/gg-library")
def connect_gg_library(track: str = "", user: User = Depends(require_role("student"))) -> dict:
    effective_track, scenario = tracks.resolve(user, track)
    lesson_def = get_lesson_def_for_track(LESSON2_ID, effective_track, scenario)
    project = ensure_lesson_project(user, LESSON2_ID, lesson_def, effective_track, scenario)
    result = provision_connector_dataset(
        user=user,
        project=project,
        track=effective_track,
        scenario=scenario,
        lesson_id=LESSON2_ID,
        connector_key="gg_library",
        fetch_live=lambda: gg_library.fetch_school_library(),
        fallback_csv="gg_school_library.csv",
        dataset_name="경기 학교도서관 현황",
        live_source_label="경기데이터드림 학교도서관 현황 API",
        fallback_source_label="탑재된 대체 자료 (경기데이터드림 2025년 저장본)",
        fallback_dataset_name="경기 학교도서관 현황 (2025년 저장본)",
        fallback_source_note=(
            "실시간 호출이 안 될 때 쓰는 저장본입니다. 경기데이터드림 학교도서관 현황 "
            "API에서 2026-10-25에 내려받은 2025년 자료 그대로입니다."
        ),
        select_into_project=not lesson_def.get("dataset_file"),
    )
    return success_response(result)


@router.post("/connectors/kosis-private-edu")
def connect_kosis_private_edu(track: str = "", user: User = Depends(require_role("student"))) -> dict:
    effective_track, scenario = tracks.resolve(user, track)
    lesson_def = get_lesson_def_for_track(LESSON2_ID, effective_track, scenario)
    project = ensure_lesson_project(user, LESSON2_ID, lesson_def, effective_track, scenario)
    result = provision_connector_dataset(
        user=user,
        project=project,
        track=effective_track,
        scenario=scenario,
        lesson_id=LESSON2_ID,
        connector_key="kosis_private_edu",
        fetch_live=lambda: kosis_private_edu.fetch_private_edu_distribution(),
        fallback_csv="kosis_private_edu_dist_2025.csv",
        dataset_name="사교육비 지출금액 구간별 분포 (KOSIS)",
        live_source_label="KOSIS 초중고사교육비조사 통계표 DT_1PE401 API",
        fallback_source_label="탑재된 대체 자료 (KOSIS 2025년 저장본)",
        fallback_dataset_name="사교육비 지출금액 구간별 분포 (2025년 저장본)",
        fallback_source_note=(
            "실시간 호출이 안 될 때 쓰는 저장본입니다. KOSIS 통계표 DT_1PE401에서 "
            "2026-10-29에 받은 2025년 자료 그대로입니다."
        ),
        select_into_project=False,
    )
    return success_response(result)


@router.post("/connectors/neis-meal")
def connect_neis_meal(track: str = "", user: User = Depends(require_role("student"))) -> dict:
    effective_track, scenario = tracks.resolve(user, track)
    lesson_def = get_lesson_def_for_track(LESSON2_ID, effective_track, scenario)
    project = ensure_lesson_project(user, LESSON2_ID, lesson_def, effective_track, scenario)
    school = schools.get_current_school()
    today = datetime.now(UTC).date()
    from_ymd = (today - timedelta(days=NEIS_LOOKBACK_DAYS)).strftime("%Y%m%d")
    to_ymd = today.strftime("%Y%m%d")

    result = provision_connector_dataset(
        user=user,
        project=project,
        track=effective_track,
        scenario=scenario,
        lesson_id=LESSON2_ID,
        connector_key="neis_meal",
        fetch_live=lambda: neis_meal.fetch_meal_service(
            atpt_ofcdc_sc_code=school["atpt_ofcdc_sc_code"],
            sd_schul_code=school["sd_schul_code"],
            mlsv_from_ymd=from_ymd,
            mlsv_to_ymd=to_ymd,
        ),
        fallback_csv="neis_meal_sample.csv",
        dataset_name=f"{school['school_name']} 급식 정보",
        live_source_label=f"NEIS 급식식단정보 API ({school['school_name']})",
        fallback_source_label="탑재된 대체 자료 (예시 학교 급식 정보)",
    )
    return success_response({**result, "school": school})


@router.get("/connectors/state/{lesson_id}")
def connector_state(
    lesson_id: str,
    track: str = "",
    user: User = Depends(require_role("student")),
) -> dict:
    effective_track, scenario = tracks.resolve(user, track)
    repo = get_repository()
    state = {}
    for connector in ("gg_library", "neis_meal", "kosis_private_edu"):
        setting = repo.get_setting(connector_setting_key(user.user_id, effective_track, scenario, lesson_id, connector))
        if setting:
            state[connector] = setting.get("value")
    return success_response(state)
