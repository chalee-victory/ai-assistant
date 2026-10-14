"""
main.py — FastAPI 앱 생성, CORS 설정, 라우터 등록
"""

import logging

# uvicorn 로그와 함께 [CORS], [CACHE] INFO 로그가 출력되도록 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import ResourceExhausted

from config import ALLOWED_ORIGINS
from routers import chat, conversations, data

app = FastAPI(
    title="아파트 시세 AI 비서",
    description="한국부동산원 주간 아파트 매매가격지수 기반 AI 질의응답 서비스",
    version="0.1.0",
)

# CORS: 환경변수 ALLOWED_ORIGINS에 등록된 출처만 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic 검증 오류 → 422 + 한국어 단일 문자열
_FIELD_KO = {"date": "날짜", "region": "지역", "value": "지수값", "memo": "메모", "message": "질문"}

@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    msgs: list[str] = []
    for err in exc.errors():
        locs = [l for l in err.get("loc", []) if l not in ("body", "query")]
        field = _FIELD_KO.get(str(locs[-1]), str(locs[-1])) if locs else ""
        t = err.get("type", "")
        raw = err.get("msg", "")
        if t == "missing":
            msg = f"{field} 항목은 필수입니다"
        elif "YYYY-MM-DD" in raw:
            msg = raw
        elif t in ("greater_than", "greater_than_equal") or "greater than" in raw:
            msg = f"{field}은(는) 0보다 큰 숫자여야 합니다"
        elif t == "literal_error" or "Input should be" in raw:
            msg = f"{field}은(는) 전국·서울-강북·서울-강남·대전·세종 중 하나여야 합니다"
        elif t in ("float_parsing", "int_parsing"):
            msg = f"{field}은(는) 숫자여야 합니다"
        else:
            msg = f"{field}: {raw}" if field else raw
        msgs.append(msg)
    return JSONResponse(status_code=422, content={"detail": " / ".join(msgs)})


@app.exception_handler(ResourceExhausted)
async def _quota_handler(request: Request, exc: ResourceExhausted) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "서버 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."},
    )


# 헬스체크: Render 헬스체크 및 /docs 진입 전 확인용
@app.get("/", summary="헬스체크", tags=["root"])
def root():
    return {"service": "아파트 시세 AI 비서 API", "docs": "/docs", "status": "ok"}


# 라우터 등록
app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)
