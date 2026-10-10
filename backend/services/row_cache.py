"""
row_cache.py — 지역별 data 행 메모리 캐시

Firestore 읽기를 줄이기 위해 지역별 레코드 목록을 서버 메모리에 보관한다.

- 지역별 지연 로딩: 처음 get_region() 호출 시에만 Firestore를 읽고
  이후 CRUD 시에는 캐시를 직접 갱신해 재조회 없이 최신 상태 유지한다.
- threading.Lock으로 동시 접근 보호.
- 각 행의 형식: {"id": doc_id, "date": ..., "region": ..., "value": ..., "memo": ...}
"""

import logging
import threading

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────
REGIONS = ["전국", "서울-강북", "서울-강남", "대전", "세종"]
DATA_COLLECTION = "data"

# ── 캐시 저장소 ────────────────────────────────────────────
_rows: dict[str, list[dict]] = {}   # {region: [{id, date, region, value, memo}]}
_lock = threading.Lock()


def get_region(region: str) -> list[dict]:
    """
    지역 캐시 반환 (날짜 오름차순).
    캐시에 없으면 Firestore에서 로드 후 반환한다.
    """
    if region in _rows:
        return _rows[region]
    with _lock:
        if region in _rows:         # double-check inside lock
            return _rows[region]
        return _load_from_firestore(region)


def _load_from_firestore(region: str) -> list[dict]:
    """Firestore에서 지역 데이터 로드. _lock 안에서 호출해야 한다."""
    from firebase import db
    logger.info("[CACHE] %s 로드 중...", region)
    docs = db.collection(DATA_COLLECTION).where("region", "==", region).stream()
    rows: list[dict] = []
    for doc in docs:
        d = doc.to_dict()
        rows.append({
            "id":     doc.id,
            "date":   d["date"],
            "region": d["region"],
            "value":  float(d["value"]),
            "memo":   d.get("memo", ""),
        })
    rows.sort(key=lambda r: r["date"])
    _rows[region] = rows
    logger.info("[CACHE] %s %d건 로드 완료", region, len(rows))
    return rows


def add_row(row: dict) -> None:
    """
    캐시에 행 추가.
    해당 지역이 아직 로드되지 않았으면 건너뜀
    (다음 get_region() 호출 시 Firestore에서 새 행을 포함해 로드됨).
    """
    region = row["region"]
    with _lock:
        if region not in _rows:
            return
        _rows[region].append(row)
        _rows[region].sort(key=lambda r: r["date"])


def update_row(old_id: str, old_region: str, new_row: dict) -> None:
    """
    캐시에서 기존 행을 제거하고 갱신된 행을 삽입한다.
    지역이 바뀐 경우 이전 지역에서 제거하고 새 지역에 추가한다.
    """
    new_region = new_row["region"]
    with _lock:
        if old_region in _rows:
            _rows[old_region] = [r for r in _rows[old_region] if r["id"] != old_id]
        if new_region in _rows:
            _rows[new_region].append(new_row)
            _rows[new_region].sort(key=lambda r: r["date"])


def remove_row(doc_id: str, region: str) -> None:
    """캐시에서 행 제거."""
    with _lock:
        if region in _rows:
            _rows[region] = [r for r in _rows[region] if r["id"] != doc_id]


def set_region(region: str, rows: list[dict]) -> None:
    """
    캐시에 지역 데이터를 직접 설정한다.
    build_summary 스크립트에서 Firestore 전체 로드 후 캐시를 워밍업할 때 사용.
    """
    with _lock:
        sorted_rows = sorted(rows, key=lambda r: r["date"])
        _rows[region] = sorted_rows
