from app.models.user import User

VALID_TRACKS = ("m1", "m3", "high", "gifted")
DEFAULT_TRACK = "m3"
VALID_SCENARIOS = ("full", "exp2")
DEFAULT_SCENARIO = "full"

TRACK_LABELS = {
    "m1": "중학교 1학년",
    "m3": "중학교 3학년",
    "high": "고등학교",
    "gifted": "영재학교",
}
SCENARIO_LABELS = {"full": "정규 7차시", "exp2": "실험수업 2차시"}

TRACK_SCENARIO_COMBOS = tuple((track, scenario) for track in VALID_TRACKS for scenario in VALID_SCENARIOS)


def normalize_track(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in VALID_TRACKS else DEFAULT_TRACK


def normalize_scenario(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in VALID_SCENARIOS else DEFAULT_SCENARIO


def track_level(track: str) -> str:
    return "high" if normalize_track(track) in ("high", "gifted") else "middle"


def class_track_scenario(class_id: str | None) -> tuple[str, str] | None:
    if not class_id:
        return None
    from lessons_app.services import student_accounts

    record = student_accounts.get_class_record(class_id)
    if not record:
        return None
    return normalize_track(record.get("track")), normalize_scenario(record.get("scenario"))


def resolve(user: User, requested_track: str | None = None, requested_scenario: str | None = None) -> tuple[str, str]:
    from_class = class_track_scenario(user.class_id)
    if from_class:
        return from_class
    return normalize_track(requested_track), normalize_scenario(requested_scenario)
