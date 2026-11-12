from app.core.time import now_utc
from app.repositories.factory import get_repository

from lessons_app.services import discuss_store, lesson_store
from lessons_app.services.lesson_defs import RESUBMIT_SUFFIX, iter_lesson_defs
from lessons_app.services.tracks import TRACK_SCENARIO_COMBOS

LESSON_IDS = ("lesson1", "lesson2", "lesson3", "lesson4", "lesson5", "lesson6", "lesson7")
CONNECTOR_KEYS = ("gg_library", "neis_meal", "kosis_private_edu")
DIAG_COLLECTION = "diagResponses"


def state_key(user_id: str, track: str, scenario: str, lesson_id: str) -> str:
    return f"lesson_state:{user_id}:{track}:{scenario}:{lesson_id}"


def connector_key(user_id: str, track: str, scenario: str, lesson_id: str, connector: str) -> str:
    return f"lesson_connector:{user_id}:{track}:{scenario}:{lesson_id}:{connector}"


def reset_marker_key(user_id: str, lesson_id: str) -> str:
    return f"lesson_reset:{user_id}:{lesson_id}"


def position_key(user_id: str, track: str, scenario: str, lesson_id: str) -> str:
    return f"lesson_position:{user_id}:{track}:{scenario}:{lesson_id}"


MAX_VISITED_CARDS = 300


def card_marker(step: int, card: int) -> str:
    return f"{int(step)}:{int(card)}"


def get_position(user_id: str, track: str, scenario: str, lesson_id: str) -> dict | None:
    setting = get_repository().get_setting(position_key(user_id, track, scenario, lesson_id))
    value = (setting.get("value") or {}) if setting else {}
    if "step" not in value:
        return None
    return {
        "step": int(value.get("step") or 0),
        "card": int(value.get("card") or 0),
        "visited": list(value.get("visited") or []),
        "updated_at": value.get("updated_at", ""),
    }


def save_position(user_id: str, track: str, scenario: str, lesson_id: str, step: int, card: int) -> dict:
    repo = get_repository()
    key = position_key(user_id, track, scenario, lesson_id)
    setting = repo.get_setting(key)
    previous = (setting.get("value") or {}) if setting else {}
    visited = [str(item) for item in (previous.get("visited") or [])]
    marker = card_marker(step, card)
    if marker not in visited and len(visited) < MAX_VISITED_CARDS:
        visited.append(marker)
    value = {
        "step": max(int(step), 0),
        "card": max(int(card), 0),
        "visited": visited,
        "updated_at": now_utc().isoformat(),
    }
    repo.upsert_setting(key, value)
    return value


def reset_marker(user_id: str, lesson_id: str) -> str:
    setting = get_repository().get_setting(reset_marker_key(user_id, lesson_id))
    return (setting.get("value") or {}).get("reset_at", "") if setting else ""


def _prompt_ids(lesson_id: str) -> list[str]:
    prompt_ids: list[str] = []
    try:
        variants = list(iter_lesson_defs(lesson_id))
    except Exception:
        return []
    for definition in variants:
        for step in definition.get("steps") or []:
            for card in step.get("cards") or [step]:
                for prompt in card.get("prompts") or []:
                    prompt_id = prompt.get("prompt_id")
                    if prompt_id and prompt_id not in prompt_ids:
                        prompt_ids.append(prompt_id)
                        prompt_ids.append(f"{prompt_id}{RESUBMIT_SUFFIX}")
    return prompt_ids


def summarize(user_id: str, settings_by_key: dict[str, dict] | None = None) -> dict[str, dict]:
    if settings_by_key is None:
        settings_by_key = {setting.get("key"): setting for setting in get_repository().list_settings()}

    summary: dict[str, dict] = {}
    for lesson_id in LESSON_IDS:
        started = False
        for track, scenario in TRACK_SCENARIO_COMBOS:
            setting = settings_by_key.get(state_key(user_id, track, scenario, lesson_id))
            if setting and (setting.get("value") or {}).get("project_id"):
                started = True
                break

        connectors = 0
        for connector in CONNECTOR_KEYS:
            if any(
                (
                    (settings_by_key.get(connector_key(user_id, track, scenario, lesson_id, connector)) or {}).get(
                        "value"
                    )
                    or {}
                ).get("dataset_id")
                for track, scenario in TRACK_SCENARIO_COMBOS
            ):
                connectors += 1

        responses = len(lesson_store.list_docs(discuss_store.COLLECTION, lesson_id=lesson_id, user_id=user_id))

        position = None
        for track, scenario in TRACK_SCENARIO_COMBOS:
            setting = settings_by_key.get(position_key(user_id, track, scenario, lesson_id))
            value = (setting.get("value") or {}) if setting else {}
            if "step" in value and (position is None or value.get("updated_at", "") > position.get("updated_at", "")):
                position = value

        marker = settings_by_key.get(reset_marker_key(user_id, lesson_id))
        summary[lesson_id] = {
            "started": started,
            "connectors": connectors,
            "responses": responses,
            "position": position,
            "reset_at": (marker.get("value") or {}).get("reset_at", "") if marker else "",
        }
    return summary


def reset_lesson(user_id: str, lesson_id: str) -> dict:
    repo = get_repository()
    cleared_states = 0
    for track, scenario in TRACK_SCENARIO_COMBOS:
        key = state_key(user_id, track, scenario, lesson_id)
        if repo.get_setting(key):
            repo.upsert_setting(key, {})
            cleared_states += 1

    cleared_connectors = 0
    for connector in CONNECTOR_KEYS:
        for track, scenario in TRACK_SCENARIO_COMBOS:
            key = connector_key(user_id, track, scenario, lesson_id, connector)
            if repo.get_setting(key):
                repo.upsert_setting(key, {})
                cleared_connectors += 1

    for track, scenario in TRACK_SCENARIO_COMBOS:
        key = position_key(user_id, track, scenario, lesson_id)
        if repo.get_setting(key):
            repo.upsert_setting(key, {})

    cleared_responses = 0
    for prompt_id in _prompt_ids(lesson_id):
        rid = discuss_store.response_id(lesson_id, prompt_id, user_id)
        if discuss_store.get_response(rid):
            discuss_store.delete_response(rid)
            cleared_responses += 1

    cleared_diag = 0
    for record in lesson_store.list_docs(DIAG_COLLECTION, user_id=user_id, lesson_id=lesson_id):
        doc_id = f"{user_id}:{record.get('track', '')}:{record.get('scenario', '')}:{record.get('item_id', '')}"
        lesson_store.delete_doc(DIAG_COLLECTION, doc_id)
        cleared_diag += 1

    reset_at = now_utc().isoformat()
    repo.upsert_setting(reset_marker_key(user_id, lesson_id), {"reset_at": reset_at})

    return {
        "lesson_id": lesson_id,
        "reset_at": reset_at,
        "cleared": {
            "projects": cleared_states,
            "connector_datasets": cleared_connectors,
            "responses": cleared_responses,
            "diag_responses": cleared_diag,
        },
    }
