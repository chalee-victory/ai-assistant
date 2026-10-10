"""
schemas.py — Pydantic 입출력 모델

검증 규칙:
  - region: 5개 지역 중 하나만 허용
  - value: 양수 (gt=0)
  - date: YYYY-MM-DD 형식
"""

import re
from datetime import date as _date
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ── 타입 별칭 ─────────────────────────────────────────────
RegionType = Literal["전국", "서울-강북", "서울-강남", "대전", "세종"]
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _check_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _DATE_RE.match(v):
        raise ValueError("날짜 형식은 YYYY-MM-DD여야 합니다")
    dt = _date.fromisoformat(v)
    if dt.weekday() != 0:
        day_ko = _WEEKDAY_KO[dt.weekday()]
        raise ValueError(
            f"주간지수 날짜는 월요일이어야 합니다. (선택한 날짜: {v} {day_ko}요일)"
        )
    return v


# ── 데이터 생성 ────────────────────────────────────────────
class DataCreate(BaseModel):
    date: str
    region: RegionType
    value: Annotated[float, Field(gt=0, description="지수 값 (양수)")]
    memo: str = ""

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        return _check_date(v)  # type: ignore[return-value]


# ── 데이터 수정 (모든 필드 선택적) ───────────────────────────
class DataUpdate(BaseModel):
    date: Optional[str] = None
    region: Optional[RegionType] = None
    value: Optional[Annotated[float, Field(gt=0)]] = None
    memo: Optional[str] = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v)


# ── 데이터 응답 ────────────────────────────────────────────
class DataResponse(BaseModel):
    id: str
    date: str
    region: str
    value: float
    memo: str


# ── 목록 응답 (페이지네이션) ──────────────────────────────────
class DataListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DataResponse]


# ════════════════════════════════════════════════════════════
# 대화(Conversation) 모델
# ════════════════════════════════════════════════════════════

RoleType = Literal["user", "assistant"]


# ── 메시지 단위 ────────────────────────────────────────────
class Message(BaseModel):
    role: RoleType
    content: str
    created_at: str  # ISO 8601 문자열로 직렬화


# ── 대화 생성 요청 ─────────────────────────────────────────
class ConversationCreate(BaseModel):
    title: str = "새 대화"


# ── 목록 응답 (messages 본문 제외) ──────────────────────────
class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


# ── 상세 응답 (messages 전체 포함) ──────────────────────────
class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[Message]
    created_at: str
    updated_at: str


# ════════════════════════════════════════════════════════════
# 채팅 모델
# ════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: Annotated[str, Field(min_length=1, max_length=1000, description="질문 (1~1000자)")]
    conversation_id: Optional[str] = None  # 없으면 새 대화 자동 생성


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
