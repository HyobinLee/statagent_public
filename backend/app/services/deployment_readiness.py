from typing import Any

from app.config import REPO_ROOT, Settings, get_settings

PRODUCTION_ENVS = {"prod", "production"}


def _check(check_id: str, title: str, status: str, detail: str, action: str = "") -> dict[str, str]:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "detail": detail,
        "action": action,
    }


def _firebase_web_configured(settings: Settings) -> bool:
    return all(
        [
            settings.firebase_web_api_key,
            settings.firebase_auth_domain,
            settings.firebase_project_id or settings.google_cloud_project,
            settings.firebase_app_id,
        ]
    )


def _firestore_rules_deny_browser_access() -> bool:
    rules_path = REPO_ROOT / "firestore.rules"
    if not rules_path.exists():
        return False
    rules = rules_path.read_text(encoding="utf-8")
    compact = " ".join(rules.split())
    return "allow read, write: if false" in compact


def build_deployment_readiness(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    is_production = settings.app_env.strip().lower() in PRODUCTION_ENVS
    checks = [
        _check(
            "student_age_scope",
            "학생 참여 범위",
            "completed" if settings.min_student_age >= 14 else "blocked",
            (
                f"MIN_STUDENT_AGE={settings.min_student_age}. 앱은 생년월일을 저장하지 않고, "
                "학교/교사 명단과 Secret Manager whitelist로 만 14세 이상 참여자만 허용합니다."
            ),
            "14세 미만 참여가 생기면 별도 법정대리인 동의 절차를 설계해야 합니다.",
        ),
        _check(
            "dev_auth",
            "배포 개발 인증 차단",
            "completed" if not is_production or not settings.dev_auth_enabled else "blocked",
            f"APP_ENV={settings.app_env}, DEV_AUTH_ENABLED={settings.dev_auth_enabled}.",
            "운영 배포에서는 DEV_AUTH_ENABLED=false로 유지하세요.",
        ),
        _check(
            "firebase_auth",
            "Firebase Google 로그인",
            "completed" if _firebase_web_configured(settings) else "blocked",
            "프론트엔드 Firebase Web 설정과 백엔드 ID token 검증 설정을 확인합니다.",
            "Firebase Web App 설정값과 Google sign-in provider를 확인하세요.",
        ),
        _check(
            "secret_whitelist",
            "Secret Manager whitelist",
            "completed" if settings.enable_secret_manager and bool(settings.firebase_whitelist_secret) else "blocked",
            "실제 로그인 허용 이메일은 repository가 아니라 Secret Manager secret으로 관리합니다.",
            "ENABLE_SECRET_MANAGER=true와 FIREBASE_WHITELIST_SECRET을 설정하세요.",
        ),
        _check(
            "auto_provision",
            "자동 사용자 등록 경계",
            "completed" if not settings.auto_provision_firebase_users else "blocked",
            "화이트리스트는 admin 로스터 전용이므로, AUTO_PROVISION_FIREBASE_USERS가 켜져 있으면 "
            "유효한 Google 계정은 누구나 teacher/student로 자동 등록됩니다.",
            "운영에서는 AUTO_PROVISION_FIREBASE_USERS를 끄고 users 컬렉션에 관리자가 직접 등록하세요.",
        ),
        _check(
            "firestore_repository",
            "Firestore 운영 저장소",
            "completed" if settings.enable_firestore else "blocked",
            "프로젝트, 보고서, 사용자 메타데이터, 업로드 자료 manifest를 Firestore repository에 저장합니다.",
            "ENABLE_FIRESTORE=true로 배포하세요.",
        ),
        _check(
            "cloud_storage_dataset",
            "업로드/KOSIS CSV 저장소",
            "completed" if settings.enable_cloud_storage and bool(settings.gcs_dataset_bucket) else "blocked",
            "운영에서는 학생 업로드와 KOSIS CSV를 비공개 Cloud Storage 객체로 저장하고 manifest만 Firestore에 둡니다.",
            "ENABLE_CLOUD_STORAGE=true와 비공개 GCS_DATASET_BUCKET을 설정하세요. 공개 차트 버킷과 섞지 마세요.",
        ),
        _check(
            "firestore_rules",
            "브라우저 직접 Firestore 접근",
            "completed" if settings.enable_firestore or _firestore_rules_deny_browser_access() else "attention",
            "현재 구조는 브라우저가 Firestore에 직접 접근하지 않고 백엔드 역할 검사를 통과한 API만 사용합니다.",
            "직접 Firestore 접근을 열 계획이면 학생/교사/관리자별 규칙을 새로 작성하세요.",
        ),
        _check(
            "llm_minimization",
            "외부 LLM 전송 최소화",
            "completed",
            (
                "AI 호출은 raw CSV 전체 대신 dataset_id, schema, summary, tool result, "
                "학생 입력 일부만 사용하도록 설계되어 있습니다."
            ),
            "개인정보 처리방침과 수업 안내문에 외부 LLM 전송 항목과 목적을 고지하세요.",
        ),
        _check(
            "usage_logging",
            "감사/사용량 로그",
            "attention",
            (
                "AI 호출은 prompt 원문 대신 hash와 길이를 기록하고, 도구 호출/차단/해제 이벤트를 "
                "남깁니다. 실제 Gemini token usage와 비용 로그는 후속 보강 대상입니다."
            ),
            "운영 전 사용자별 일일 AI 한도와 실제 token usage 기록을 추가하세요.",
        ),
        _check(
            "retention_policy",
            "보관/삭제 정책",
            "completed",
            "privacy-notes에 학기/수업 종료 후 삭제, 프로젝트 반환, 감사 로그 보관 원칙을 문서화합니다.",
            "학교 정책에 맞는 최종 보관 기간을 확정하세요.",
        ),
    ]
    blocked = [item for item in checks if item["status"] == "blocked"]
    attention = [item for item in checks if item["status"] == "attention"]
    return {
        "ready_for_controlled_pilot": not blocked,
        "app_env": settings.app_env,
        "min_student_age": settings.min_student_age,
        "privacy_policy_url": settings.privacy_policy_url,
        "checks": checks,
        "summary": {
            "completed": len([item for item in checks if item["status"] == "completed"]),
            "attention": len(attention),
            "blocked": len(blocked),
        },
    }
