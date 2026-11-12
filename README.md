# 통계 에이전트: 설치와 서버 설정 안내

"데이터 처리는 AI가, 통찰은 내가" 수업에 쓴 통계 에이전트의 공개 소스입니다(저장소: https://github.com/HyobinLee/statagent_public). 코드는 MIT, 수업 자료는 CC BY 4.0입니다(7절). 이 소스에는 API 키, 서버 주소, 클라우드 프로젝트 정보가 들어 있지 않습니다. 쓰려는 사람이 자기 키를 발급받아 넣고, 자기 서버(Google Cloud)에 올려야 학생이 접속할 수 있습니다.

## 1. 구성

| 폴더 | 내용 | 서버 |
| --- | --- | --- |
| `backend/` | 주 백엔드(FastAPI). 통계 도구, 자료, 로그인 확인, 생성형 AI 연결 | Cloud Run 서비스 1 |
| `frontend/` | 주 앱 화면(자유 탐구, 교사, 관리자). 정적 파일 | Firebase Hosting |
| `lessons/backend/` | 차시 앱 백엔드. 주 백엔드의 도구를 가져다 쓴다 | Cloud Run 서비스 2 |
| `lessons/frontend/` | 차시 앱 화면(학생 카드, 교사 진행 화면, 학급 명단). 차시 백엔드가 `/lessons`로 함께 낸다 | 서비스 2에 포함 |
| `lessons/backend/lessons_app/data/` | 트랙별 차시 정의, 공유 카드, 수업용 자료, 학교 정보(`schools.json`) | |
| `firebase.json`, `firestore.rules` | Hosting 경로 연결과 Firestore 보안 규칙 | |

학생 기기는 브라우저만 있으면 됩니다. 외부 AI와 공공데이터 호출은 모두 서버가 하므로 학교 보안 네트워크에서도 학생 기기가 외부 API를 직접 부르지 않습니다.

## 2. 내 컴퓨터에서 먼저 실행해 보기

키와 클라우드 없이 "개발 인증" 모드로 돌려 볼 수 있습니다. 이 모드는 로그인 없이 개발용 계정(관리자, 교사, 학생)을 골라 들어가므로 **내 컴퓨터에서만** 씁니다.

준비물: Python 3.11 이상.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS, Linux: source .venv/bin/activate
pip install -e "./backend[google-cloud,gemini]"
pip install -e "./lessons/backend"
cp .env.example .env        # Windows: copy .env.example .env
```

`.env`의 `DEV_AUTH_ENABLED=true`인지 확인하고, 터미널 네 개에서 다음을 실행합니다.

```bash
# 1) 주 백엔드
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 18080

# 2) 주 앱 화면
python -m http.server 8000 -d frontend

# 3) 차시 백엔드 (주 백엔드 주소를 알려 준다)
#    macOS, Linux: export MAIN_BACKEND_URL=http://127.0.0.1:18080
#    Windows PowerShell: $env:MAIN_BACKEND_URL="http://127.0.0.1:18080"
cd lessons/backend && uvicorn lessons_app.main:app --host 127.0.0.1 --port 18081

# 4) 차시 앱 화면
python -m http.server 8001 -d lessons/frontend
```

- 주 앱: http://127.0.0.1:8000/
- 차시 앱: http://127.0.0.1:8001/
- 포트를 바꾸려면 `frontend/js/api.js`(18080), `lessons/frontend/js/api.js`(18081), `.env`의 `CORS_ORIGINS`를 함께 고칩니다.
- 키가 없어도 수업은 돌아갑니다. KOSIS, 경기데이터드림, NEIS 카드는 앱에 들어 있는 저장본 자료로 바뀌고 화면에 "대체 자료 사용"이 뜹니다. 생성형 AI 기능은 규칙 기반 안내로 바뀝니다.

## 3. API 키 발급

키는 모두 선택입니다. 넣은 만큼 실시간 기능이 켜집니다.

| 키 | 쓰는 곳 | 발급처 | 없을 때 |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | 주 앱의 분석 추천, 관찰점과 유도 질문, 해석 피드백 | Google AI Studio (aistudio.google.com) | 규칙 기반 안내 |
| `KOSIS_API_KEY` | KOSIS 통계표 검색과 불러오기, 실험수업 2차시 사교육비 표 | KOSIS 공유서비스 (kosis.kr/openapi) | 저장본(2025) 사용 |
| `GG_API_KEY` | 차시 앱 2차시 경기도 학교도서관 현황 | 경기데이터드림 (data.gg.go.kr) | 저장본(2025) 사용 |
| `NEIS_API_KEY` | 차시 앱 2차시 우리 학교 급식 정보 | NEIS 교육정보 개방 포털 (open.neis.go.kr) | 예시 급식 자료 사용 |
| `SGIS_SERVICE_ID`, `SGIS_SECURITY_KEY` | 지역 지도의 시도 경계 | 통계청 SGIS | 지역 중심점에 원으로 표시 |
| `DATA_GO_KR_SERVICE_KEY`, `ECOS_API_KEY` 등 | 주 앱의 추가 공공데이터 검색 | 공공데이터포털, 한국은행 ECOS | 해당 검색 숨김 |

내 컴퓨터에서는 `.env`에 바로 적습니다. 서버에서는 4절처럼 Secret Manager에 넣습니다. **키를 코드나 저장소에 적지 마세요.**

## 4. 서버에 올리기 (Google Cloud와 Firebase)

아래 명령의 `<...>`는 직접 정하는 값입니다. 예시는 서울 리전(`asia-northeast3`)과 서비스 이름 `stat-agent-backend`, `stat-agent-lessons-backend`를 씁니다. 이름이나 리전을 바꾸면 `firebase.json`의 `serviceId`와 `region`도 같이 바꿉니다.

준비물: Google 계정, 결제 계정, [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)(`gcloud`), [Firebase CLI](https://firebase.google.com/docs/cli)(`firebase`).

### 4-1. 프로젝트 만들기

```bash
gcloud auth login
gcloud projects create <PROJECT_ID>
gcloud config set project <PROJECT_ID>
gcloud billing projects link <PROJECT_ID> --billing-account <BILLING_ACCOUNT_ID>

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com identitytoolkit.googleapis.com firebase.googleapis.com
```

### 4-2. Firebase 연결과 Google 로그인

1. [Firebase 콘솔](https://console.firebase.google.com)에서 "프로젝트 추가"로 위 `<PROJECT_ID>`를 고릅니다.
2. Authentication, 로그인 방법에서 Google을 사용 설정합니다.
3. 프로젝트 설정, 내 앱에서 웹 앱을 추가하면 `firebaseConfig`가 나옵니다. 그 값을 5절의 `FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID`, `FIREBASE_MESSAGING_SENDER_ID`에 옮깁니다. 이 값은 브라우저용 설정이라 비밀 값이 아닙니다.
4. Authentication, 설정, 승인된 도메인에 Hosting 주소(`<PROJECT_ID>.web.app`)가 있는지 확인합니다. 학교 도메인을 따로 연결하면 그 도메인도 더합니다.

### 4-3. Firestore와 Cloud Storage

```bash
gcloud firestore databases create --location=asia-northeast3

gcloud storage buckets create gs://<PROJECT_ID>-charts --location=asia-northeast3
gcloud storage buckets create gs://<PROJECT_ID>-datasets --location=asia-northeast3
gcloud storage buckets add-iam-policy-binding gs://<PROJECT_ID>-charts \
  --member=allUsers --role=roles/storage.objectViewer
```

- 차트 버킷은 브라우저가 그림을 보여 주도록 공개 읽기로 둡니다. 학생 자료는 넣지 않습니다.
- 자료 버킷(학생이 올린 CSV)은 공개하지 않습니다.

### 4-4. 키와 관리자 명단을 Secret Manager에 넣기

```bash
printf "<GEMINI_API_KEY>" | gcloud secrets create gemini-api-key --data-file=-
printf "<KOSIS_API_KEY>"  | gcloud secrets create kosis-api-key --data-file=-
gcloud secrets create stat-api-keys --data-file=stat-api-keys.json
gcloud secrets create admin-whitelist --data-file=admin-whitelist.json
```

`stat-api-keys.json`에는 나머지 키를 이름과 값의 쌍으로 담습니다. 쓰지 않는 키는 빼도 됩니다.

```json
{
  "GG_API_KEY": { "value": "<경기데이터드림 키>" },
  "NEIS_API_KEY": { "value": "<NEIS 키>" },
  "SGIS_SERVICE_ID": { "value": "<SGIS 서비스 ID>" },
  "SGIS_SECURITY_KEY": { "value": "<SGIS 보안키>" }
}
```

`admin-whitelist.json`은 관리자 계정 명단입니다. 여기 적은 이메일만 관리자가 됩니다.

```json
[
  { "email": "<관리자 이메일>", "role": "admin", "display_name": "관리자", "active": true }
]
```

두 JSON 파일은 등록한 뒤 지웁니다.

### 4-5. 서비스 계정 권한

Cloud Run은 기본으로 Compute Engine 기본 서비스 계정(`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`)으로 돕니다. 이 계정에 다음 역할을 줍니다.

```bash
SA=<PROJECT_NUMBER>-compute@developer.gserviceaccount.com
for ROLE in roles/datastore.user roles/storage.objectAdmin roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:$SA --role=$ROLE
done
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member=serviceAccount:$SA --role=roles/iam.serviceAccountTokenCreator
```

마지막 권한은 학생의 학급 코드와 PIN 로그인에 필요합니다. 서버가 학생용 로그인 토큰에 서명할 때 씁니다.

### 4-6. 환경 변수 파일 만들기

두 서비스에 줄 환경 변수를 YAML로 만듭니다. 이 파일도 저장소에 올리지 않습니다.

`env.main.yaml` (주 백엔드)

```yaml
APP_ENV: production
GOOGLE_CLOUD_PROJECT: <PROJECT_ID>
DEV_AUTH_ENABLED: "false"
AUTO_PROVISION_FIREBASE_USERS: "false"
FIREBASE_DEFAULT_ROLE: student
FIREBASE_WEB_API_KEY: <apiKey>
FIREBASE_AUTH_DOMAIN: <authDomain>
FIREBASE_PROJECT_ID: <projectId>
FIREBASE_APP_ID: <appId>
FIREBASE_MESSAGING_SENDER_ID: <messagingSenderId>
FIREBASE_WHITELIST_SECRET: admin-whitelist
ENABLE_FIRESTORE: "true"
FIRESTORE_DATABASE: (default)
FIRESTORE_COLLECTION_PREFIX: main
ENABLE_CLOUD_STORAGE: "true"
GCS_CHART_BUCKET: <PROJECT_ID>-charts
GCS_DATASET_BUCKET: <PROJECT_ID>-datasets
ENABLE_SECRET_MANAGER: "true"
GEMINI_API_KEY_SECRET: gemini-api-key
KOSIS_API_KEY_SECRET: kosis-api-key
STAT_API_KEYS_SECRET: stat-api-keys
ENABLE_GEMINI: "true"
GEMINI_MODEL: gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS: "60"
MIN_STUDENT_AGE: "14"
GOOGLE_WORKSPACE_DOMAIN: ""
MAP_TILE_USER_AGENT: "stat-agent/0.1 (contact: <연락용 이메일>)"
```

`env.lessons.yaml` (차시 백엔드)는 위 내용을 그대로 복사하고 세 줄을 바꿉니다.

```yaml
FIRESTORE_COLLECTION_PREFIX: lesson
MAIN_BACKEND_URL: <4-7에서 얻은 주 백엔드 주소>
CORS_ORIGINS: https://<PROJECT_ID>.web.app
```

- `DEV_AUTH_ENABLED`는 서버에서 반드시 `false`입니다. `true`면 누구나 개발용 계정으로 들어올 수 있습니다.
- 차시 백엔드의 접두사는 `lesson`이어야 합니다. `firestore.rules`가 `lesson_` 컬렉션을 기준으로 실시간 화면을 허용합니다.
- 학교 Google Workspace 계정만 보이게 하려면 `GOOGLE_WORKSPACE_DOMAIN`에 학교 도메인을 적습니다. 로그인 창의 계정 목록만 좁히며, 권한은 관리자가 등록한 명단으로 정해집니다.
- 생성형 AI를 쓰지 않으려면 `ENABLE_GEMINI: "false"`로 두고 `GEMINI_API_KEY_SECRET`을 지웁니다.

### 4-7. 두 서비스 배포

저장소 맨 위 폴더에서 실행합니다.

```bash
# 주 백엔드
gcloud run deploy stat-agent-backend --source backend --region asia-northeast3 \
  --port 8000 --allow-unauthenticated --env-vars-file env.main.yaml

# 주 백엔드 주소를 확인해 env.lessons.yaml의 MAIN_BACKEND_URL에 적는다
gcloud run services describe stat-agent-backend --region asia-northeast3 --format "value(status.url)"

# 차시 백엔드 (주 백엔드 코드를 함께 담아야 해서 저장소 전체를 빌드 대상으로 쓴다)
gcloud artifacts repositories create stat-agent --repository-format=docker --location=asia-northeast3
IMAGE=asia-northeast3-docker.pkg.dev/<PROJECT_ID>/stat-agent/stat-agent-lessons-backend:latest
gcloud builds submit . --config lessons/backend/cloudbuild.yaml --substitutions _IMAGE=$IMAGE
gcloud run deploy stat-agent-lessons-backend --image $IMAGE --region asia-northeast3 \
  --port 8080 --allow-unauthenticated --env-vars-file env.lessons.yaml
```

### 4-8. 화면 올리기 (Firebase Hosting)

```bash
firebase login
firebase use --add <PROJECT_ID>
firebase deploy --only hosting,firestore:rules
```

배포가 끝나면 다음 주소가 열립니다.

- 주 앱: `https://<PROJECT_ID>.web.app/`
- 차시 앱: `https://<PROJECT_ID>.web.app/lessons/`
- 관리자: `https://<PROJECT_ID>.web.app/admin.html`

## 5. 첫 사용 준비

1. **관리자 로그인:** `admin-whitelist`에 적은 Google 계정으로 관리자 화면에 들어갑니다. "배포 준비 점검"에서 로그인, Firestore, Storage, 키 상태가 모두 정상인지 봅니다.
2. **교사 등록:** 관리자 화면의 사용자 관리에서 교사의 Google 이메일을 역할 "교사"로 등록합니다.
3. **우리 학교 정보:** 급식 카드(차시 앱 2차시)가 우리 학교 급식을 불러오게 하려면 `lessons/backend/lessons_app/data/schools.json`에 학교를 적고 차시 백엔드를 다시 배포합니다. 코드는 NEIS 학교 기본정보에서 찾습니다.

```json
[
  {
    "school_id": "<임의의 짧은 이름>",
    "atpt_ofcdc_sc_code": "<시도교육청 코드, 예: B10>",
    "sd_schul_code": "<행정표준코드 7자리>",
    "school_name": "<학교 이름>",
    "level": "middle 또는 high",
    "is_default": true
  }
]
```

4. **학급 만들기:** 교사는 차시 앱의 "학급 명단과 PIN 발급"에서 학급을 만들고 트랙(m1, m3, high, gifted)을 고른 뒤 학생 이름을 붙여 넣습니다. 학생마다 4자리 PIN이 나오고 쪽지로 인쇄할 수 있습니다. 실험수업 2차시를 하려면 학급의 시나리오를 "실험수업 2차시"로 바꿉니다.
5. **학생 접속:** 학생은 차시 앱 주소에서 학급 코드, 이름, PIN으로 들어옵니다. Google 계정은 필요 없습니다.
6. **수업 전 점검:** 학급 없이 트랙만 골라 미리보기로 리허설합니다. 수업 10분 전에 교사 진행 화면의 설정 창에서 켜진 공개를 모두 끕니다.

## 6. 운영 유의 사항

- **개인정보:** 앱은 학생 생년월일, 보호자 정보, 비밀번호를 저장하지 않습니다. 생성형 AI에는 자료 전체가 아니라 항목 구조, 요약, 분석 결과, 학생 입력 일부만 보냅니다. 학교의 개인정보 처리 절차(동의서, 보관 기간, 파기)는 운영하는 학교가 따로 정합니다. 만 14세 미만 학생이 참여하면 법정대리인 동의가 필요합니다.
- **교육과정 범위:** 분석 도구는 p값, 회귀계수, 신뢰구간, 가설검정, 순위상관을 내지 않도록 막혀 있습니다.
- **비용:** 소규모 수업은 대개 Cloud Run, Firestore, Storage의 무료 사용량 안에 듭니다. 결제 계정에 예산 알림을 걸어 두세요. 생성형 AI 호출은 사용량에 따라 요금이 날 수 있습니다.
- **키 교체:** 키를 바꿀 때는 Secret Manager에 새 버전을 추가하고 두 서비스를 다시 배포합니다.
- **문제 확인:** `https://<PROJECT_ID>.web.app/api`를 열어 `"status": "ok"`가 나오는지 보고(주 백엔드), Cloud Run 로그를 봅니다. 차시 앱 로그인이 안 되면 `MAIN_BACKEND_URL`과 4-5의 토큰 서명 권한을 먼저 확인합니다.

## 7. 라이선스와 출처

| 대상 | 라이선스 |
| --- | --- |
| 코드 | MIT (`LICENSE`) |
| 수업 자료(차시 카드, 발문, 진단 문항, 진단 그림, 수업용 예시 자료) | CC BY 4.0 (`LICENSE-CONTENT.md`) |
| 공공 통계 자료 | 각 제공 기관의 이용 조건 |
| `frontend/vendor/gridstack`, `lessons/frontend/vendor/qrcode` | 각 라이브러리의 MIT 라이선스(저작권 표기 유지) |

수업 자료를 고쳐 쓰거나 다시 배포할 때는 "A.E.S. 통계교육 교사연구회(2026), CC BY 4.0"처럼 출처를 밝혀 주세요.

- 수업용 공개 자료의 출처: 국가데이터처 「초중고사교육비조사」(2025), 「지역소득」(2022), 기상청 「기상관측통계」(2000~2024), 경기데이터드림 학교도서관 현황(2025), 세종시 학교 주변 교통안전 공공 자료(재구성). 나머지 수업 자료(두 반 성적, 방과후 수학, 급식 설문, 학급 문고)는 수업을 위해 만든 예시 자료입니다.
