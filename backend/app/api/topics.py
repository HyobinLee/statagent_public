from fastapi import APIRouter, Depends, Query

from app.core.errors import success_response
from app.dependencies import get_current_user
from app.models.project import normalize_school_level
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService
from app.services.kosis_service import KosisDatasetService
from app.services.topic_service import TopicService

router = APIRouter(prefix="/api/topics", tags=["topics"])
KOSIS_TOPIC_SUGGESTION_SCHEMA_VERSION = 1


def _kosis_suggestion_cache_key(topic_id: str, grade_level: str) -> str:
    return f"kosis_topic_dataset_suggestions:{topic_id}:{grade_level}"


@router.get("")
def list_topics(
    school_level: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
) -> dict:
    topics = [
        topic.model_dump() for topic in TopicService().list_topics(school_level=normalize_school_level(school_level))
    ]
    return success_response(topics, {"count": len(topics)})


@router.get("/{topic_id}")
def get_topic(
    topic_id: str,
    school_level: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
) -> dict:
    topic = TopicService().get_topic(topic_id, school_level=normalize_school_level(school_level))
    return success_response(topic.model_dump())


@router.get("/{topic_id}/datasets")
def list_topic_datasets(topic_id: str, _user: User = Depends(get_current_user)) -> dict:
    TopicService().get_topic(topic_id)
    owner_user_id = _user.user_id if _user.role == "student" else None
    datasets = [
        dataset.model_dump() for dataset in DatasetService().list_for_topic(topic_id, owner_user_id=owner_user_id)
    ]
    return success_response(datasets, {"count": len(datasets)})


@router.get("/{topic_id}/dataset-suggestions")
def get_topic_dataset_suggestions(
    topic_id: str,
    school_level: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
) -> dict:
    level = normalize_school_level(school_level)
    topic = TopicService().get_topic(topic_id, school_level=level)
    grade_level = level or topic.level
    repo = get_repository()
    cache_key = _kosis_suggestion_cache_key(topic_id, grade_level)
    cached = repo.get_setting(cache_key)
    cached_value = cached.get("value", {}) if cached else {}
    if (
        isinstance(cached_value, dict)
        and cached_value.get("schema_version") == KOSIS_TOPIC_SUGGESTION_SCHEMA_VERSION
        and cached_value.get("topic_id") == topic_id
        and cached_value.get("topic_question") == topic.question
        and isinstance(cached_value.get("result"), dict)
    ):
        result = dict(cached_value["result"])
        result["metadata"] = {
            **(result.get("metadata") or {}),
            "cache_hit": True,
            "topic_id": topic.topic_id,
            "topic_title": topic.title,
        }
        return success_response(result, {"cached": True})

    result = KosisDatasetService().recommend(
        research_question=topic.question,
        grade_level=grade_level,
    )
    result["metadata"] = {
        **(result.get("metadata") or {}),
        "cache_hit": False,
        "topic_id": topic.topic_id,
        "topic_title": topic.title,
    }
    repo.upsert_setting(
        cache_key,
        {
            "schema_version": KOSIS_TOPIC_SUGGESTION_SCHEMA_VERSION,
            "topic_id": topic.topic_id,
            "topic_question": topic.question,
            "result": result,
        },
    )
    return success_response(result, {"cached": False})
