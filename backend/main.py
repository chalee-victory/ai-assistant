"""
main.py — FastAPI 앱 생성, CORS 설정, 라우터 등록
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from routers import conversations, data

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

# 라우터 등록
app.include_router(data.router)
app.include_router(conversations.router)
