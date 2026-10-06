"""
schemas.py — Pydantic 입출력 모델

검증 규칙:
  - region: 5개 지역 중 하나만 허용
  - value: 양수 (gt=0)
  - date: YYYY-MM-DD 형식
"""

import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ── 타입 별칭 ─────────────────────────────────────────────
RegionType = Literal["전국", "서울-강북", "서울-강남", "대전", "세종"]
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(v: Optional[str]) -> Optional[str]:
    if v is not None and not _DATE_RE.match(v):
        raise ValueError("날짜 형식은 YYYY-MM-DD여야 합니다")
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
