from app.core.errors import AppError
from app.models.user import User
from app.repositories.factory import get_repository
from app.services.dataset_service import DatasetService

LESSON_STATE_PREFIX = "lesson_state:"


def list_group_datasets(user: User) -> list[dict]:
    if not user.group_id:
        return []
    repo = get_repository()
    peers = {
        peer.user_id: peer
        for peer in repo.list_users()
        if peer.role == "student" and peer.group_id == user.group_id and peer.user_id != user.user_id
    }
    if not peers:
        return []

    dataset_service = DatasetService()
    candidates: list[dict] = []
    seen_dataset_ids: set[str] = set()
    for setting in repo.list_settings():
        key = setting.get("key", "")
        if not key.startswith(LESSON_STATE_PREFIX):
            continue
        parts = key.split(":")
        if len(parts) < 3 or parts[1] not in peers:
            continue
        value = setting.get("value") or {}
        dataset_id = value.get("dataset_id")
        if not dataset_id or dataset_id in seen_dataset_ids:
            continue
        try:
            dataset = dataset_service.get_dataset(dataset_id)
        except AppError:
            continue
        seen_dataset_ids.add(dataset_id)
        owner = peers[parts[1]]
        candidates.append(
            {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "source": dataset.source,
                "owner_user_id": owner.user_id,
                "owner_display_name": owner.display_name,
            }
        )
    return candidates


def copy_group_dataset(*, source_dataset_id: str, topic_id: str, owner_user_id: str) -> dict:
    service = DatasetService()
    source = service.get_dataset(source_dataset_id)
    df = service.read_dataframe(source_dataset_id)
    content = df.to_csv(index=False).encode("utf-8-sig")
    return service.create_uploaded_dataset(
        filename=f"{source.name}.csv",
        content=content,
        topic_id=topic_id,
        owner_user_id=owner_user_id,
        dataset_name=f"{source.name} (모둠 공유)",
        source=f"모둠원 공유 자료 · {source.source}",
        source_note=f"모둠원이 등록한 자료를 복사했습니다. 원본 출처: {source.source_note or source.source}",
    )
