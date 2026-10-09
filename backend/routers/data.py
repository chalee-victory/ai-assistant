"""
routers/data.py — /api/data 엔드포인트

주의: GET /api/data/summary 는 GET /api/data/{id} 보다
      반드시 먼저 등록해야 'summary'가 id로 매칭되는 것을 막는다.
"""

from fastapi import APIRouter, Query

from schemas import DataCreate, DataListResponse, DataResponse, DataUpdate
from services import data_service, summary_service

router = APIRouter(prefix="/api/data", tags=["data"])


# ── 요약 조회 (/{id} 보다 앞에 등록) ──────────────────────────
@router.get("/summary", summary="지역별 요약 통계 조회")
def get_summary() -> dict:
    """meta/summary 캐시에서 지역별 요약 통계를 반환한다."""
    return summary_service.get_summary()


# ── 목록 조회 ─────────────────────────────────────────────
@router.get("", response_model=DataListResponse, summary="데이터 목록 조회")
def get_data_list(
    region: str | None = Query(None, description="지역 필터 (전국/서울-강북/서울-강남/대전/세종)"),
    start_date: str | None = Query(None, description="시작일 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="종료일 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(50, ge=1, le=500, description="페이지 크기"),
) -> DataListResponse:
    return data_service.get_data_list(region, start_date, end_date, page, page_size)


# ── 생성 ──────────────────────────────────────────────────
@router.post("", response_model=DataResponse, status_code=201, summary="데이터 생성")
def create_data(payload: DataCreate) -> DataResponse:
    return data_service.create_data(payload)


# ── 수정 ──────────────────────────────────────────────────
@router.put("/{doc_id}", response_model=DataResponse, summary="데이터 수정")
def update_data(doc_id: str, payload: DataUpdate) -> DataResponse:
    return data_service.update_data(doc_id.strip(), payload)


# ── 삭제 ──────────────────────────────────────────────────
@router.delete("/{doc_id}", status_code=204, summary="데이터 삭제")
def delete_data(doc_id: str) -> None:
    data_service.delete_data(doc_id.strip())
