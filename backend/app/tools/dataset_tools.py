from app.core.errors import AppError
from app.services.dataset_service import DatasetService
from app.services.topic_service import TopicService
from app.tools.schemas import start_timer, tool_failure, tool_success


def list_topics() -> dict:
    start = start_timer()
    try:
        topics = [topic.model_dump() for topic in TopicService().list_topics()]
        return tool_success(
            "list_topics",
            None,
            topics,
            "탐구 주제 목록입니다. 관심 있는 질문을 하나 선택해 보세요.",
            start,
        )
    except AppError as exc:
        return tool_failure("list_topics", None, exc, start)


def list_datasets_for_topic(topic_id: str) -> dict:
    start = start_timer()
    try:
        TopicService().get_topic(topic_id)
        datasets = [dataset.model_dump() for dataset in DatasetService().list_for_topic(topic_id)]
        return tool_success(
            "list_datasets_for_topic",
            None,
            datasets,
            "선택한 주제에 사용할 수 있는 자료 후보입니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("list_datasets_for_topic", None, exc, start)


def get_dataset_schema(dataset_id: str) -> dict:
    start = start_timer()
    try:
        data = DatasetService().schema(dataset_id)
        return tool_success(
            "get_dataset_schema",
            dataset_id,
            data,
            "자료의 컬럼과 의미를 먼저 확인했습니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("get_dataset_schema", dataset_id, exc, start)


def get_dataset_summary(dataset_id: str) -> dict:
    start = start_timer()
    try:
        data = DatasetService().summary(dataset_id)
        return tool_success(
            "get_dataset_summary",
            dataset_id,
            data,
            "자료의 행 수, 결측치, 수치형 컬럼의 대표값을 요약했습니다.",
            start,
        )
    except AppError as exc:
        return tool_failure("get_dataset_summary", dataset_id, exc, start)
