# 아파트 시세 AI 비서

한국부동산원 **주간 아파트 매매가격지수** 데이터를 기반으로 사용자 질문에 답하는 AI 웹서비스.
백엔드가 데이터 요약을 계산해 GPT 시스템 프롬프트에 주입하고, GPT가 이를 근거로 자연어 답변을 생성합니다.

- **백엔드 (Render)**: `https://ai-assistant-xxxx.onrender.com`
- **프론트엔드 (Vercel)**: `https://ai-assistant-xxxx.vercel.app`

---

## 기술 스택

| 분류 | 사용 기술 |
|------|-----------|
| 백엔드 | FastAPI · Python 3.12 · Uvicorn |
| 프론트엔드 | 바닐라 HTML / CSS / JavaScript |
| 데이터베이스 | Firebase Firestore |
| AI | OpenAI GPT API (gpt-4o-mini) |
| 백엔드 배포 | Render (무료 티어) |
| 프론트엔드 배포 | Vercel |

---

## 데이터

- **출처**: 한국부동산원 R-ONE 전국주택가격동향조사 주간아파트동향
- **기간**: 2012-11-26 ~ 2026-09-28 (주간, 5개 지역)
- **지역**: 전국 · 서울-강북 · 서울-강남 · 대전 · 세종
- **지수 기준시점**: 2026-07-06 = 100

---

## 로컬 개발

### 1. 저장소 클론

```bash
git clone https://github.com/chalee-victory/ai-assistant.git
cd ai-assistant
```

### 2. 백엔드 실행

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # .env에 실제 키 입력
uvicorn main:app --reload
```

Swagger UI: `http://localhost:8000/docs`

### 3. 프론트엔드 실행

```bash
cd frontend
cp config.example.js config.js   # 이미 기본값 localhost:8000
# 브라우저에서 index.html 열기 (Live Server 등)
```

---

## 환경변수

### 백엔드 (`.env` 또는 Render 환경변수)

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `OPENAI_MODEL` | 사용할 GPT 모델 | `gpt-4o-mini` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase 서비스 계정 키 (JSON 문자열) | `{"type":"service_account",...}` |
| `FIREBASE_KEY_PATH` | 키 파일 경로 (로컬 개발 선택) | `C:/keys/firebase-key.json` |
| `ALLOWED_ORIGINS` | CORS 허용 출처 (쉼표 구분) | `https://my-app.vercel.app` |

### 프론트엔드 (Vercel 환경변수)

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `API_BASE_URL` | 백엔드 URL | `https://ai-assistant-xxxx.onrender.com` |

---

## 배포

### Render (백엔드)

1. Render 대시보드 → **New Web Service** → 이 저장소 연결
2. 설정:
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. **Environment** 탭에서 위 환경변수 5개 입력
4. Deploy → 서비스 URL 복사 (Vercel `API_BASE_URL`에 사용)

> 무료 티어는 비활성 후 콜드 스타트(최대 1분)가 발생합니다.

### Vercel (프론트엔드)

1. Vercel 대시보드 → **Add New Project** → 이 저장소 연결
2. 설정:
   - **Root Directory**: `frontend`
   - **Build Command**: `bash build.sh`
   - **Output Directory**: `.`
3. **Environment Variables** → `API_BASE_URL` = Render 서비스 URL
4. Deploy

### Firestore 초기 데이터 적재

Firestore `data` 컬렉션이 비어 있을 때 한 번 실행합니다.

```bash
cd backend
python scripts/seed_data.py      # CSV → Firestore 3,600건 업로드
python scripts/build_summary.py  # meta/summary 계산·저장
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/data` | 데이터 추가 |
| `GET` | `/api/data` | 데이터 목록 조회 (지역·기간 필터, 페이지네이션) |
| `GET` | `/api/data/summary` | 요약 통계 조회 |
| `PUT` | `/api/data/{id}` | 데이터 수정 |
| `DELETE` | `/api/data/{id}` | 데이터 삭제 |
| `POST` | `/api/conversations` | 대화 생성 |
| `GET` | `/api/conversations` | 대화 목록 |
| `GET` | `/api/conversations/{id}` | 대화 상세 |
| `DELETE` | `/api/conversations/{id}` | 대화 삭제 |
| `POST` | `/api/chat` | AI 채팅 (GPT 호출) |

---

## 폴더 구조

```
ai-assistant/
├── backend/
│   ├── main.py              # FastAPI 앱, CORS, 라우터
│   ├── config.py            # 환경변수 로드
│   ├── firebase.py          # Firestore 클라이언트
│   ├── schemas.py           # Pydantic 스키마
│   ├── routers/             # data.py · conversations.py · chat.py
│   ├── services/            # data_service · summary_service · conversation_service · chat_service · row_cache
│   ├── scripts/             # seed_data · build_summary · show_prompt · backfill_updated_at · test_row_cache
│   ├── data/apt_price_index_weekly.csv
│   ├── requirements.txt
│   ├── .python-version      # 3.12.9
│   └── .env.example
└── frontend/
    ├── index.html
    ├── style.css
    ├── app.js
    ├── config.example.js
    └── build.sh             # Vercel 빌드: API_BASE_URL → config.js
```
