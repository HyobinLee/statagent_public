import copy
import json
from functools import lru_cache

from app.core.errors import AppError

from lessons_app.config import LESSON_DEFS_PATH

VALID_LEVELS = ("middle", "high")
DEFAULT_LEVEL = "middle"

TRACKS_DIR = LESSON_DEFS_PATH.parent / "tracks"
SHARED_CARDS_PATH = LESSON_DEFS_PATH.parent / "shared_cards.json"

TEACHER_ONLY_PROMPT_KEYS = ("observe", "target", "answer")
RESUBMIT_SUFFIX = "__r2"


@lru_cache
def _load_lesson_defs() -> dict:
    with LESSON_DEFS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache
def _load_shared_cards() -> dict:
    if not SHARED_CARDS_PATH.exists():
        return {}
    with SHARED_CARDS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache
def _load_track_defs(track: str) -> dict | None:
    path = TRACKS_DIR / f"{track}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_card(card: dict) -> dict:
    ref = card.get("ref")
    if not ref:
        return card
    shared = _load_shared_cards().get(ref)
    if shared is None:
        raise AppError(
            "SHARED_CARD_NOT_FOUND",
            f"공통 카드를 찾을 수 없습니다: {ref}",
            "shared_cards.json에 해당 id가 있는지 확인해 주세요.",
            500,
        )
    merged = {**shared, **{key: value for key, value in card.items() if key != "ref"}}
    return merged


def _resolve_refs(lesson_def: dict) -> dict:
    resolved = dict(lesson_def)
    steps = []
    for step in lesson_def.get("steps") or []:
        if step.get("cards"):
            step = {**step, "cards": [_resolve_card(card) for card in step["cards"]]}
        else:
            step = _resolve_card(step)
        steps.append(step)
    resolved["steps"] = steps
    return resolved


def _lesson_not_found() -> AppError:
    return AppError(
        "LESSON_NOT_FOUND",
        "해당 차시를 찾을 수 없습니다.",
        "차시 주소를 다시 확인해 주세요.",
        404,
    )


def get_lesson_def(lesson_id: str, level: str | None = None) -> dict:
    defs = _load_lesson_defs()
    lesson_def = defs.get(lesson_id)
    if not lesson_def:
        raise _lesson_not_found()
    levels = lesson_def.get("levels")
    if not levels:
        return lesson_def
    level_def = levels.get(normalize_level(level))
    if not level_def:
        raise AppError(
            "LESSON_LEVEL_NOT_FOUND",
            "해당 학교급의 차시 내용을 찾을 수 없습니다.",
            "차시 주소의 level 값을 확인해 주세요.",
            404,
        )
    merged = {**lesson_def, **level_def}
    merged.pop("levels", None)
    return merged


def _scenario_stem(track: str, scenario: str) -> str | None:
    from lessons_app.services.tracks import normalize_scenario

    normalized = normalize_scenario(scenario)
    return None if normalized == "full" else f"{track}.{normalized}"


def _scenario_not_available(track: str, scenario: str) -> AppError:
    return AppError(
        "SCENARIO_NOT_AVAILABLE",
        f"{track} 트랙에는 {scenario} 시나리오 차시가 아직 없습니다.",
        "학급의 시나리오 설정을 확인하거나 full(정규 차시)로 되돌려 주세요.",
        404,
    )


def get_lesson_def_for_track(lesson_id: str, track: str, scenario: str = "full") -> dict:
    from lessons_app.services.tracks import normalize_track, track_level

    normalized = normalize_track(track)
    scenario_stem = _scenario_stem(normalized, scenario)
    if scenario_stem is not None:
        scenario_defs = _load_track_defs(scenario_stem)
        if scenario_defs is None:
            raise _scenario_not_available(normalized, scenario)
        lesson_def = scenario_defs.get(lesson_id)
        if lesson_def is None:
            raise _lesson_not_found()
        return _resolve_refs(lesson_def)
    track_defs = _load_track_defs(normalized)
    if track_defs is not None:
        lesson_def = track_defs.get(lesson_id)
        if lesson_def is not None:
            return _resolve_refs(lesson_def)
        raise _lesson_not_found()
    return get_lesson_def(lesson_id, track_level(normalized))


def list_lessons_for_track(track: str, scenario: str = "full") -> list[dict]:
    from lessons_app.services.tracks import normalize_track, track_level

    normalized = normalize_track(track)
    scenario_stem = _scenario_stem(normalized, scenario)
    if scenario_stem is not None:
        scenario_defs = _load_track_defs(scenario_stem)
        if scenario_defs is None:
            raise _scenario_not_available(normalized, scenario)
        track_defs = scenario_defs
    else:
        track_defs = _load_track_defs(normalized)
    if track_defs is not None:
        ids = sorted(track_defs.keys(), key=lambda lesson_id: (len(lesson_id), lesson_id))
        source = {lesson_id: track_defs[lesson_id] for lesson_id in ids}
    else:
        defs = _load_lesson_defs()
        ids = sorted(defs.keys(), key=lambda lesson_id: (len(lesson_id), lesson_id))
        level = track_level(normalized)
        source = {lesson_id: get_lesson_def(lesson_id, level) for lesson_id in ids}
    return [
        {
            "lesson_id": lesson_id,
            "title": lesson_def.get("title", ""),
            "topic_sentence": lesson_def.get("topic_sentence", ""),
            "mode": lesson_def.get("mode", ""),
        }
        for lesson_id, lesson_def in source.items()
    ]


def iter_lesson_defs(lesson_id: str):
    defs = _load_lesson_defs()
    lesson_def = defs.get(lesson_id)
    if lesson_def:
        if lesson_def.get("levels"):
            for level in lesson_def["levels"]:
                yield get_lesson_def(lesson_id, level)
        else:
            yield lesson_def
    if TRACKS_DIR.exists():
        for path in sorted(TRACKS_DIR.glob("*.json")):
            track_defs = _load_track_defs(path.stem)
            if track_defs and lesson_id in track_defs:
                yield _resolve_refs(track_defs[lesson_id])


def strip_teacher_only(lesson_def: dict) -> dict:
    stripped = copy.deepcopy(lesson_def)
    for step in stripped.get("steps") or []:
        for card in step.get("cards") or [step]:
            for prompt in card.get("prompts") or []:
                for key in TEACHER_ONLY_PROMPT_KEYS:
                    prompt.pop(key, None)
                for choice in prompt.get("choices") or []:
                    choice.pop("target", None)
            item = card.get("item")
            if item:
                for key in ("answer", "reason_answer", "target"):
                    item.pop(key, None)
                for choice in item.get("choices") or []:
                    choice.pop("target", None)
    return stripped


def normalize_level(level: str | None) -> str:
    value = (level or "").strip().lower()
    return value if value in VALID_LEVELS else DEFAULT_LEVEL
