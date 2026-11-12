import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.core.time import now_utc
from app.models.user import User
from app.services.workflow_service import WorkflowService

from lessons_app.config import LESSON_CSV_DIR
from lessons_app.services import lesson_store
from lessons_app.services.lesson_defs import get_lesson_def_for_track
from lessons_app.services.provisioning import ensure_lesson_project

COLLECTION = "fixedAnalysisCache"

TTL_DAYS = int(os.getenv("FIXED_ANALYSIS_TTL_DAYS", "60"))


def find_fixed_tool(lesson_def: dict, key: str) -> dict | None:
    for step in lesson_def.get("steps", []):
        for card in step.get("cards") or [step]:
            for reveal in card.get("reveals") or []:
                if reveal.get("key") == key and reveal.get("tool_name"):
                    return {"tool_name": reveal["tool_name"], "tool_args": reveal.get("tool_args") or {}}
            if card.get("kind") == "analysis" and card.get("id") == key and card.get("tool_name"):
                return {"tool_name": card["tool_name"], "tool_args": card.get("tool_args") or {}}
    return None


@lru_cache(maxsize=64)
def _csv_fingerprint(filename: str, mtime_ns: int) -> str:
    _ = mtime_ns
    path = LESSON_CSV_DIR / filename
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8]


def dataset_fingerprint(provisioning_def: dict) -> str:
    filename = provisioning_def.get("dataset_file")
    if not filename or not (LESSON_CSV_DIR / filename).is_file():
        return ""
    stat = (LESSON_CSV_DIR / filename).stat()
    return _csv_fingerprint(filename, stat.st_mtime_ns)


def resolve_provisioning_def(lesson_def: dict, lesson_id: str, track: str, scenario: str) -> tuple[str, dict]:
    project_lesson_id = lesson_def.get("project_lesson_id", lesson_id)
    if project_lesson_id == lesson_id:
        return lesson_id, lesson_def
    return project_lesson_id, get_lesson_def_for_track(project_lesson_id, track, scenario)


def doc_id_for(track: str, scenario: str, lesson_id: str, key: str, fixed: dict, fingerprint: str) -> str:
    args_hash = hashlib.sha1(
        json.dumps([fixed["tool_name"], fixed["tool_args"]], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    return ":".join([track, scenario, lesson_id, key, args_hash, fingerprint])


def _expired(doc: dict) -> bool:
    stamp = (doc or {}).get("expires_at")
    if not stamp:
        stamp = (doc or {}).get("cached_at")
        if not stamp:
            return False
        try:
            return datetime.fromisoformat(stamp).replace(tzinfo=UTC) + timedelta(days=TTL_DAYS) < now_utc()
        except ValueError:
            return False
    try:
        expires = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires < now_utc()


def read_cached(doc_id: str) -> dict | None:
    doc = lesson_store.get_doc(COLLECTION, doc_id)
    if not doc or not doc.get("payload"):
        return None
    if _expired(doc):
        return None
    return doc["payload"]


def store(doc_id: str, lesson_id: str, key: str, payload: dict) -> None:
    now = now_utc()
    lesson_store.set_doc(
        COLLECTION,
        doc_id,
        {
            "payload": payload,
            "cached_at": now.isoformat(),
            "expires_at": (now + timedelta(days=TTL_DAYS)).isoformat(),
            "lesson_id": lesson_id,
            "key": key,
        },
    )


def get_or_run(user: User, lesson_id: str, key: str, track: str, scenario: str, lesson_def: dict) -> dict | None:
    fixed = find_fixed_tool(lesson_def, key)
    if not fixed:
        return None

    project_lesson_id, provisioning_def = resolve_provisioning_def(lesson_def, lesson_id, track, scenario)
    doc_id = doc_id_for(track, scenario, lesson_id, key, fixed, dataset_fingerprint(provisioning_def))

    cached = read_cached(doc_id)
    if cached:
        return cached

    project = ensure_lesson_project(user, project_lesson_id, provisioning_def, track, scenario)
    analysis = WorkflowService().run_analysis(project.project_id, fixed["tool_name"], fixed["tool_args"], user)
    payload = analysis.model_dump(mode="json")
    store(doc_id, lesson_id, key, payload)
    return payload
