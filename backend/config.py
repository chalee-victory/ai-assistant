"""
config.py — 환경변수 로드 및 앱 설정값 관리

.env 파일(또는 배포 환경의 환경변수)에서 값을 읽어 앱 전체에 공급한다.
키를 코드에 직접 쓰지 않는다.
"""

import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 이 파일 기준으로 .env 탐색 (backend/.env)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


# ── OpenAI ───────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Firebase ─────────────────────────────────────────────
# Render 등 배포 환경: JSON 문자열을 환경변수로 주입
# 로컬 개발 편의: 파일 경로를 FIREBASE_KEY_PATH 로 지정 가능
FIREBASE_SERVICE_ACCOUNT_JSON: str | None = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
FIREBASE_KEY_PATH: str | None = os.getenv("FIREBASE_KEY_PATH")

# 둘 다 없으면 즉시 실패 → 설정 누락을 앱 시작 시점에 발견
if not FIREBASE_SERVICE_ACCOUNT_JSON and not FIREBASE_KEY_PATH:
    raise EnvironmentError(
        "Firebase 인증 정보가 없습니다. "
        "FIREBASE_SERVICE_ACCOUNT_JSON 또는 FIREBASE_KEY_PATH 를 설정하세요."
    )

# ── CORS ─────────────────────────────────────────────────
_raw_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS: list[str] = [
    o.strip().rstrip("/")
    for o in _raw_origins.split(",")
    if o.strip()
]
logger.info("[CORS] 허용 출처 %d개: %s", len(ALLOWED_ORIGINS), ", ".join(ALLOWED_ORIGINS))
