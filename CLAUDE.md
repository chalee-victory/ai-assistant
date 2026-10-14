# CLAUDE.md — 아파트 시세 AI 비서 (코디세이 미션: 나만의 AI 비서 구축)

이 파일은 Claude Code가 작업할 때마다 읽는 프로젝트 지침이다. 아래 규칙을 항상 지킨다.

## 1. 프로젝트 개요
- 한국부동산원 **주간 아파트 매매가격지수** 데이터를 이해하고, 사용자의 질문에 데이터 근거로 답하는 AI 비서 웹서비스.
- 핵심 원리: **컨텍스트 주입** — 백엔드가 데이터 요약을 계산해 GPT 시스템 프롬프트에 넣은 뒤 질문에 답하게 한다.
- 분업 원칙: **계산은 파이썬, 해석(문장화)은 GPT.** GPT에게 수치 계산을 맡기지 않는다.
- GitHub: `chalee-victory/ai-assistant`

## 2. 데이터
- 원본: `backend/data/apt_price_index_weekly.csv` (UTF-8 BOM, 3,600행)
- 컬럼: `date`(YYYY-MM-DD, 주 기준일), `region`, `value`(지수, 소수 2자리), `memo`(예: "주간 +0.06%")
- 지역 5개: `전국`, `서울-강북`, `서울-강남`, `대전`, `세종`
- 기간: 2012-11-26 ~ 2026-09-28, 지역별 720주 (5개 지역 날짜 동일)
- 연휴(추석·설)로 발표가 없던 주 3곳: 2017-10-09, 2025-02-03, 2025-10-13 각각의 바로 앞 주가 비어 있음(14일 간격) — 데이터 오류 아님
- 출처: 한국부동산원 R-ONE 전국주택가격동향조사 주간아파트동향 (README에 출처 표기)

### 지수 해석 규칙 (시스템 프롬프트에도 반드시 포함)
- 기준시점 **2026-07-06 = 100** (5개 지역 모두 이 주에 100.00).
- 지수는 지역별 **가격 변화율** 비교에만 쓴다. 지역 간 **가격 수준(어디가 더 비싼지)** 비교 금지.
- 금액(원)으로 환산하지 않는다.
- 변화는 **퍼센트(%)**로 말한다. 포인트 차이를 %로 말하지 않는다.
  - 예: 고점 대비 = (현재 ÷ 고점 − 1) × 100

## 3. 기술 스택 (변경 금지)
- 백엔드: FastAPI, Python 3.10+, venv. 패키지: fastapi, uvicorn, firebase-admin, openai, python-dotenv, pydantic → **Render 배포**
- 프론트: **바닐라 HTML/CSS/JS만** (React·Vue 등 프레임워크 금지) → **Vercel 배포**
  - 예외: 그래프는 **Chart.js 4.4.4** (CDN `cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js`, 실패 시 unpkg). 이 버전엔 `chart.umd.min.js`가 없으니 경로 변경 금지
- DB: Firebase Firestore
- AI: OpenAI GPT API (기본 모델은 환경변수 `OPENAI_MODEL`, 저비용 모델 사용)

## 4. 폴더 구조
```
ai-assistant/
├── CLAUDE.md
├── README.md
├── .gitignore
├── backend/
│   ├── main.py              # 앱 생성, CORS, 라우터 등록
│   ├── config.py            # 환경변수 로드
│   ├── firebase.py          # Firestore 클라이언트 초기화
│   ├── schemas.py           # Pydantic 모델
│   ├── routers/             # HTTP 입구 (data.py, conversations.py, chat.py)
│   ├── services/            # 업무 로직 (data_service.py, summary_service.py,
│   │                        #            conversation_service.py, chat_service.py,
│   │                        #            row_cache.py — 지역별 data 행 메모리 캐시)
│   ├── scripts/             # 운영: seed_data(CSV→Firestore) · build_summary · show_prompt · backfill_updated_at
│   │                        # 테스트: test_row_cache · test_series(키 불필요) · test_chat_rules(OpenAI 키 필요)
│   ├── data/apt_price_index_weekly.csv
│   ├── requirements.txt
│   ├── .python-version      # 3.12.9 (Render와 동일)
│   └── .env.example
├── frontend/
│   ├── index.html, style.css, app.js   # 채팅 · 대화 기록 · 요약 · 추이 그래프 · 데이터 관리
│   ├── config.example.js    # 로컬용 → config.js로 복사
│   ├── config.js            # 빌드 시 생성 (커밋 금지)
│   └── build.sh             # Vercel 빌드: API_BASE_URL → config.js
└── docs/
    ├── TECH-GUIDE.md        # 초보자용 기술 안내서
    └── screenshots/         # 01-chat · 02-crud · 03-history · 04-trend (README용)
```
- 라우터는 요청/검증/응답만, 서비스는 DB·계산·GPT 호출만 담당한다.

## 5. Firestore 설계
- `data` 컬렉션: 문서 1개 = 1주 × 1지역
  - 문서 ID: `{date}_{region}` (예: `2026-09-28_세종`) → seed 재실행해도 중복 없음
  - 필드: date, region, value, memo, created_at
- `conversations` 컬렉션: 필드 title, messages[{role, content, created_at}], created_at, updated_at
- `meta/summary` 문서: **요약 캐시**
  - 채팅 때는 이 문서 1건만 읽는다 (data 3,600건을 매번 읽지 않음 — 무료 한도 하루 읽기 5만 건 보호)
  - data를 생성·수정·삭제할 때, 그리고 seed 후에 요약을 다시 계산해 갱신한다
- **메모리 캐시** (Firestore 읽기 95% 이상 절감 — 2026-10-10 무료 한도 초과 사고 후 도입)
  - `row_cache`: 지역별 data 행을 처음 필요할 때만 로드(지연 로딩), 전부 받은 뒤에만 캐시에 대입(부분 로딩 방지)
  - CRUD는 Firestore 쓰기 성공 후 캐시도 갱신, 요약 재계산은 캐시로(0읽기)
  - 목록(GET /api/data)·그래프(GET /api/data/series)·요약 재계산이 같은 캐시를 공유
  - summary도 메모리 캐시(CRUD 시 무효화), 대화 목록은 `order_by(updated_at).limit(30)`
  - 새 기능도 data를 읽을 땐 반드시 `row_cache.get_region()`을 쓴다 (컬렉션 직접 stream 금지)
  - `ResourceExhausted` → 503 한국어 안내

## 6. 요약(summary) 내용 — 지역별
- period(시작~끝), count
- latest(값, 날짜), max(값, 날짜), min(값, 날짜), average
- from_peak_pct: 고점 대비 %
- change_4w_pct, change_52w_pct, change_total_pct
- trend: 최근 4주 증감률 부호로 "상승/하락/보합" + 연속 상승·하락 주 수
- 전체: 지역 목록, 데이터 기간, 총 건수, 지수 기준시점

## 7. API 엔드포인트 (미션 필수)
- 데이터: `POST /api/data`, `GET /api/data`(region·기간 필터, 페이지네이션), `PUT /api/data/{id}`, `DELETE /api/data/{id}`, `GET /api/data/summary`
- 대화: `POST /api/conversations`, `GET /api/conversations`, `GET /api/conversations/{id}`, `DELETE /api/conversations/{id}`
- 채팅: `POST /api/chat` — 요약 캐시 읽기 → 시스템 프롬프트 조립 → GPT 호출 → conversations에 자동 저장 → 답변 반환
- 추가: `GET /` (헬스체크), `GET /api/data/series?region=` (추이 그래프용, 날짜 오름차순 — 보너스)
- 주의: `/summary`, `/series` 같은 고정 경로는 `/{doc_id}` 경로보다 **먼저** 등록
- Swagger: `/docs` 동작 확인

## 8. 보안·운영 규칙
- 키는 **환경변수로만** 관리. 코드·커밋에 키 하드코딩 절대 금지.
  - `OPENAI_API_KEY`, `OPENAI_MODEL`, `FIREBASE_SERVICE_ACCOUNT_JSON`(JSON 문자열), `ALLOWED_ORIGINS`(쉼표 구분), 프론트 `API_BASE_URL`
- `.gitignore`: `.env`, `venv/`, `__pycache__/`, `*serviceAccount*.json`, `*firebase-adminsdk*.json`, `frontend/config.js`
- 입력 검증은 Pydantic(region은 5개 중 하나, value는 양수, date는 YYYY-MM-DD).
- 예외 처리: 없는 id → 404, 검증 실패 → 422, 외부 API 실패 → 502와 친절한 메시지.
- 비용 제한: GPT `max_tokens` 500 이하, 대화 이력은 최근 10개 메시지만 전달.
- Render 무료 티어 콜드스타트: 프론트에 "서버 깨우는 중(최대 1분)" 안내 표시.

## 9. 작업 방식
- 한 번에 한 단계만 구현하고, 각 단계 끝에 실행·확인 방법을 알려준다.
- 사용자가 요청하지 않은 기능을 미리 만들지 않는다.
- 코드 주석과 설명은 한국어로 작성한다.
- 개발 순서:
  1. 토대: .gitignore, requirements.txt, .env.example, config.py
  2. firebase.py → seed_data.py (업로드 후 콘솔에서 3,600건 확인)
  3. schemas.py → data_service.py / summary_service.py → routers/data.py → main.py (`/docs` 확인)
  4. conversation_service.py → routers/conversations.py
  5. chat_service.py → routers/chat.py
  6. 프론트: index.html → style.css → app.js
  7. 배포: Render → Vercel(build.sh) → README.md
- 보너스(필수 완료 후): Function Calling(지역·기간별 조회 도구), ~~그래프~~(완료), CSV 내보내기, 다크모드

### 협업 규칙 (로컬 Claude Code ↔ claude.ai 클라우드 Claude)
- 두 곳 모두 이 저장소에 push한다. **작업 시작 전 `git pull`, 끝나면 push까지** — 동시에 고치면 충돌
- `main`에 push하면 Render·Vercel이 **자동 재배포**된다. 평가 기간 등 조심할 땐 브랜치 + PR
- 데이터 테스트에 원본 날짜를 쓰지 않는다 (2026-09-28 대전 원본 삭제 사고). 테스트용은 원본에 없는 미래 **월요일**
- 키·`.env` 화면은 캡처·공유 금지

## 진행 현황 (2026-10-14 기준) — 미션 제출 완료

### 완료: 1~7단계 + 보너스 그래프
- **1~5단계**: 토대 → Firestore 3,600건 → 데이터 CRUD·요약 → 대화 → 채팅(gpt-4o-mini)
- **6단계**: 프론트(3단 레이아웃, Pretendard, 상승 빨강/하락 파랑), AI 답변 품질 보강, 데이터 안전장치
  - 순위는 `_compute_rankings()`가 코드로 계산해 주입, 이번 요청의 숫자만 사용, 매수 질문 금지어 시 1회 재생성
  - 입력 검증 프론트+백엔드(월요일 날짜 포함), 중복 409, 삭제 확인창, 204 응답 처리
- **7단계**: 요구사항 점검(❌ 0개) → Firestore 읽기 최적화 → Render·Vercel 배포 → 키 재발급 → README·TECH-GUIDE·스크린샷
- **보너스 그래프** (커밋 3846c12): `/api/data/series` + '추이 그래프' 탭(지역 복수 선택, 1년/3년/5년/전체, 기준 100, 크게 보기, CRUD 자동 갱신)

### 배포 주소
- 프론트 https://ai-assistant-frontend-xi.vercel.app (`-xi` 없는 주소는 남의 사이트)
- API https://ai-assistant-fenj.onrender.com · Swagger `/docs`
- Render: Root `backend`, Start `uvicorn main:app --host 0.0.0.0 --port $PORT`, 무료 티어 콜드스타트 최대 1분
- Vercel: Root `frontend`, Build `bash build.sh`, Output `.`
- Firestore 무료 한도(하루 읽기 5만) 초기화: 매일 16시(KST)

### 테스트 (backend/, venv 활성화)
- `python scripts/test_row_cache.py` — 9/9
- `python scripts/test_series.py` — 7/7 (키 불필요, 원본 CSV 사용)
- `python -m scripts.test_chat_rules` — 실제 OpenAI 호출(키 필요)

### 남은 일
- 보너스: CSV 내보내기, 다크모드, Function Calling
- 향후 과제(README 기재): 관리자 인증(현재 누구나 CRUD 가능), 커서 기반 페이지네이션
