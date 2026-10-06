"""
data_service.py — data 컬렉션 CRUD

생성·수정·삭제 후에는 summary_service.compute_and_save_summary()를
호출해 meta/summary 캐시를 항상 최신 상태로 유지한다.

문서 ID 규칙: {date}_{region}  예) 2026-09-28_세종
"""

from datetime import datetime, timezone

from fastapi import HTTPException

from firebase import db
from schemas import DataCreate, DataListResponse, DataResponse, DataUpdate
from services.summary_service import compute_and_save_summary

COLLECTION = "data"


def _to_response(doc_id: str, data: dict) -> DataResponse:
    """Firestore 문서 dict → DataResponse 변환."""
    return DataResponse(
        id=doc_id,
        date=data["date"],
        region=data["region"],
        value=float(data["value"]),
        memo=data.get("memo", ""),
    )


# ── 생성 ──────────────────────────────────────────────────
def create_data(payload: DataCreate) -> DataResponse:
    doc_id = f"{payload.date}_{payload.region}"
    doc_ref = db.collection(COLLECTION).document(doc_id)

    if doc_ref.get().exists:
        raise HTTPException(status_code=409, detail=f"이미 존재하는 데이터입니다: {doc_id}")

    doc_data = {
        "date": payload.date,
        "region": payload.region,
        "value": payload.value,
        "memo": payload.memo,
        "created_at": datetime.now(timezone.utc),
    }
    doc_ref.set(doc_data)
    compute_and_save_summary()

    return _to_response(doc_id, doc_data)


# ── 목록 조회 (필터 + 페이지네이션) ──────────────────────────
def get_data_list(
    region: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> DataListResponse:
    query = db.collection(COLLECTION)

    # region 필터는 Firestore 서버에서 처리 (단일 필드 = 인덱스 불필요)
    if region:
        query = query.where("region", "==", region)

    docs = query.stream()

    # 날짜 필터·정렬은 Python에서 처리 (복합 인덱스 생성 불필요)
    items: list[DataResponse] = []
    for doc in docs:
        d = doc.to_dict()
        date = d.get("date", "")
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        items.append(_to_response(doc.id, d))

    items.sort(key=lambda r: r.date)

    total = len(items)
    start = (page - 1) * page_size
    return DataListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items[start : start + page_size],
    )


# ── 수정 ──────────────────────────────────────────────────
def update_data(doc_id: str, payload: DataUpdate) -> DataResponse:
    doc_ref = db.collection(COLLECTION).document(doc_id)
    existing = doc_ref.get()

    if not existing.exists:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")

    current = existing.to_dict()
    updated_fields = payload.model_dump(exclude_none=True)

    # 변경 후 date/region으로 새 문서 ID 계산
    new_date = updated_fields.get("date", current["date"])
    new_region = updated_fields.get("region", current["region"])
    new_doc_id = f"{new_date}_{new_region}"

    new_data = {**current, **updated_fields, "updated_at": datetime.now(timezone.utc)}
    new_data.pop("created_at", None)  # 아래에서 원본 값 재사용

    if new_doc_id != doc_id:
        # date 또는 region이 바뀌면 문서 ID도 바뀜: 삭제 후 재생성
        doc_ref.delete()
        new_ref = db.collection(COLLECTION).document(new_doc_id)
        new_ref.set({**new_data, "created_at": current.get("created_at")})
    else:
        doc_ref.update({**updated_fields, "updated_at": datetime.now(timezone.utc)})

    compute_and_save_summary()
    return _to_response(new_doc_id, new_data)


# ── 삭제 ──────────────────────────────────────────────────
def delete_data(doc_id: str) -> None:
    doc_ref = db.collection(COLLECTION).document(doc_id)

    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")

    doc_ref.delete()
    compute_and_save_summary()
