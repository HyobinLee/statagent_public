import json
import threading
import time
from pathlib import Path

from app.config import get_settings
from app.repositories.factory import get_repository


def _firestore_collection_name(name: str) -> str:
    prefix = get_settings().firestore_collection_prefix.strip()
    if not prefix:
        return name
    separator = "" if prefix.endswith("_") else "_"
    return f"{prefix}{separator}{name}"


def _use_firestore() -> bool:
    return get_settings().enable_firestore


def _local_path(collection: str) -> Path:
    root = get_settings().local_data_dir
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{collection}.json"


_LOCAL_LOCK = threading.RLock()


def _local_read(collection: str) -> list[dict]:
    path = _local_path(collection)
    with _LOCAL_LOCK:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)


def _local_write(collection: str, items: list[dict]) -> None:
    path = _local_path(collection)
    tmp = path.with_suffix(".json.tmp")
    with _LOCAL_LOCK:
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(items, file, ensure_ascii=False, indent=2)
        for attempt in range(5):
            try:
                tmp.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))


def get_doc(collection: str, doc_id: str) -> dict | None:
    if _use_firestore():
        client = get_repository().client
        snapshot = client.collection(_firestore_collection_name(collection)).document(doc_id).get()
        return snapshot.to_dict() if snapshot.exists else None
    items = _local_read(collection)
    match = next((item for item in items if item.get("_id") == doc_id), None)
    if match is None:
        return None
    return {key: value for key, value in match.items() if key != "_id"}


def set_doc(collection: str, doc_id: str, payload: dict) -> dict:
    if _use_firestore():
        client = get_repository().client
        client.collection(_firestore_collection_name(collection)).document(doc_id).set(payload)
        return payload
    with _LOCAL_LOCK:
        items = _local_read(collection)
        record = {**payload, "_id": doc_id}
        for index, existing in enumerate(items):
            if existing.get("_id") == doc_id:
                items[index] = record
                _local_write(collection, items)
                return payload
        items.append(record)
        _local_write(collection, items)
        return payload


def update_doc(collection: str, doc_id: str, patch: dict) -> dict | None:
    with _LOCAL_LOCK:
        existing = get_doc(collection, doc_id)
        if existing is None:
            return None
        merged = {**existing, **patch}
        return set_doc(collection, doc_id, merged)


def list_docs(collection: str, **equals: object) -> list[dict]:
    if _use_firestore():
        from google.cloud.firestore_v1 import FieldFilter

        client = get_repository().client
        query = client.collection(_firestore_collection_name(collection))
        for field, value in equals.items():
            query = query.where(filter=FieldFilter(field, "==", value))
        return [snapshot.to_dict() for snapshot in query.stream()]
    items = _local_read(collection)
    matches = [item for item in items if all(item.get(field) == value for field, value in equals.items())]
    return [{key: value for key, value in item.items() if key != "_id"} for item in matches]


def delete_doc(collection: str, doc_id: str) -> None:
    if _use_firestore():
        client = get_repository().client
        client.collection(_firestore_collection_name(collection)).document(doc_id).delete()
        return
    with _LOCAL_LOCK:
        items = _local_read(collection)
        items = [item for item in items if item.get("_id") != doc_id]
        _local_write(collection, items)
