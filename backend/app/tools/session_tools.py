from app.tools.schemas import start_timer, tool_success


def save_inquiry_step(project_id: str, step_type: str, payload: dict) -> dict:
    start = start_timer()
    return tool_success(
        "save_inquiry_step",
        None,
        {"project_id": project_id, "step_type": step_type, "payload": payload, "status": "stub"},
        "탐구 단계 저장은 workflow API에서 실제 처리하며, 도구 함수는 v0.1 stub입니다.",
        start,
    )


def save_conclusion(project_id: str, conclusion_text: str) -> dict:
    start = start_timer()
    return tool_success(
        "save_conclusion",
        None,
        {"project_id": project_id, "conclusion_text": conclusion_text, "status": "stub"},
        "결론 저장은 report API에서 실제 처리하며, 도구 함수는 v0.1 stub입니다.",
        start,
    )


def get_inquiry_history(project_id: str) -> dict:
    start = start_timer()
    return tool_success(
        "get_inquiry_history",
        None,
        {"project_id": project_id, "steps": [], "status": "stub"},
        "탐구 이력 조회는 project API에서 실제 처리하며, 도구 함수는 v0.1 stub입니다.",
        start,
    )
