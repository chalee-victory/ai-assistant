"""
data_service.py — data 컬렉션 CRUD

목록 조회와 요약 재계산은 메모리 캐시(row_cache)를 우선 사용해 Firestore 읽기를 줄인다.
- GET 목록: row_cache에서 필터·정렬·페이지 처리 (Firestore 0읽기, 최초 지역 접근 시 ~720읽기)
- POST/PUT/DELETE: Firestore 쓰기 후 row_cache 동기 갱신 → compute_and_save_region()은 캐시 사용

중복 확인(POST)은 doc_id 단건 get() 유지 (1건 읽기).
"""

from datetime import datetime, timezone

from fastapi import HTTPException

from firebase import db
from schemas import (
    DataCreate,
    DataListResponse,
    DataResponse,
    DataUpdate,
    SeriesPoint,
    SeriesResponse,
)
from services import row_cache
from services.summary_service import compute_and_save_region

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

    # 중복 확인: 단건 읽기 1회
    if doc_ref.get().exists:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{payload.date} {payload.region} 데이터가 이미 있습니다. "
                "값을 바꾸려면 목록에서 [수정]을 눌러주세요."
            ),
        )

    doc_data = {
        "date":       payload.date,
        "region":     payload.region,
        "value":      payload.value,
        "memo":       payload.memo,
        "created_at": datetime.now(timezone.utc),
    }
    doc_ref.set(doc_data)

    # 캐시 갱신 (이미 로드된 지역이면 즉시 반영, 아니면 다음 get_region() 시 로드)
    row_cache.add_row({
        "id":     doc_id,
        "date":   payload.date,
        "region": payload.region,
        "value":  payload.value,
        "memo":   payload.memo,
    })

    compute_and_save_region(payload.region)
    return _to_response(doc_id, doc_data)


# ── 목록 조회 (필터 + 페이지네이션) ──────────────────────────
def get_data_list(
    region: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> DataListResponse:
    # 대상 지역 목록 결정
    regions = [region] if region else row_cache.REGIONS

    items: list[DataResponse] = []
    for r in regions:
        for row in row_cache.get_region(r):   # 최초 접근 시만 Firestore 읽기
            date = row["date"]
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            items.append(DataResponse(
                id=row["id"],
                date=date,
                region=row["region"],
                value=row["value"],
                memo=row.get("memo", ""),
            ))

    items.sort(key=lambda r: r.date, reverse=True)  # 최신순(내림차순)

    total = len(items)
    start = (page - 1) * page_size
    return DataListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items[start : start + page_size],
    )


# ── 추이 그래프용 시계열 ────────────────────────────────────
def get_series(
    region: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SeriesResponse:
    """지역 하나의 (날짜, 지수) 목록을 날짜 오름차순으로 반환한다.

    row_cache를 그대로 사용하므로 데이터 관리 탭과 캐시를 공유한다.
    (해당 지역 최초 접근 시에만 Firestore 읽기, 이후 0읽기 · CRUD 즉시 반영)
    """
    points = [
        SeriesPoint(date=row["date"], value=row["value"])
        for row in row_cache.get_region(region)   # 이미 날짜 오름차순
        if (not start_date or row["date"] >= start_date)
        and (not end_date or row["date"] <= end_date)
    ]
    return SeriesResponse(region=region, count=len(points), points=points)


# ── 수정 ──────────────────────────────────────────────────
def update_data(doc_id: str, payload: DataUpdate) -> DataResponse:
    doc_ref = db.collection(COLLECTION).document(doc_id)
    existing = doc_ref.get()   # 1 읽기 (현재 값 필요)

    if not existing.exists:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")

    current = existing.to_dict()
    old_region = current["region"]
    updated_fields = payload.model_dump(exclude_none=True)

    # 변경 후 date/region으로 새 문서 ID 계산
    new_date   = updated_fields.get("date",   current["date"])
    new_region = updated_fields.get("region", old_region)
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

    # 캐시 갱신
    row_cache.update_row(doc_id, old_region, {
        "id":     new_doc_id,
        "date":   new_date,
        "region": new_region,
        "value":  float(updated_fields.get("value", current["value"])),
        "memo":   updated_fields.get("memo", current.get("memo", "")),
    })

    # region이 바뀌었으면 이전 지역과 새 지역 모두 갱신
    affected = {new_region}
    if new_region != old_region:
        affected.add(old_region)
    for r in sorted(affected):
        compute_and_save_region(r)

    return _to_response(new_doc_id, new_data)


# ── 삭제 ──────────────────────────────────────────────────
def delete_data(doc_id: str) -> None:
    doc_ref = db.collection(COLLECTION).document(doc_id)
    snapshot = doc_ref.get()   # 1 읽기 (존재 확인 + region 취득)

    if not snapshot.exists:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")

    region = snapshot.to_dict()["region"]
    doc_ref.delete()

    # 캐시 갱신
    row_cache.remove_row(doc_id, region)

    compute_and_save_region(region)
