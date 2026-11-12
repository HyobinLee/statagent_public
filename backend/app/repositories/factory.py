from functools import lru_cache

from app.config import get_settings
from app.repositories.firestore import FirestoreRepository
from app.repositories.local_json import LocalJsonRepository


@lru_cache
def get_repository():
    settings = get_settings()
    if settings.enable_firestore:
        return FirestoreRepository()
    return LocalJsonRepository()
