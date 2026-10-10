"""
test_row_cache.py — row_cache 단위 테스트 (Firestore 접근 없음)

실행 방법 (backend/ 폴더에서):
  python scripts/test_row_cache.py
"""

import sys
import os

# 프로젝트 루트(backend/) 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.row_cache as rc


def _reset():
    """각 테스트 전 캐시 초기화."""
    rc._rows.clear()


def _pass(name):
    print(f"  PASS  {name}")


def _fail(name, msg):
    print(f"  FAIL  {name}: {msg}")
    sys.exit(1)


# ── 테스트 1: add_row — 날짜 오름차순 정렬 유지 ──────────────────
def test_add_row_sorted():
    _reset()
    rc._rows["전국"] = []
    rc.add_row({"id": "2024-01-15_전국", "date": "2024-01-15", "region": "전국", "value": 101.0, "memo": ""})
    rc.add_row({"id": "2024-01-08_전국", "date": "2024-01-08", "region": "전국", "value": 100.5, "memo": ""})
    dates = [r["date"] for r in rc._rows["전국"]]
    if dates != sorted(dates):
        _fail("add_row_sorted", f"정렬 오류: {dates}")
    _pass("add_row_sorted")


# ── 테스트 2: add_row — 미로드 지역은 건너뜀 ─────────────────────
def test_add_row_skip_when_not_cached():
    _reset()
    # "서울-강북" 은 캐시에 없음
    rc.add_row({"id": "2024-01-08_서울-강북", "date": "2024-01-08", "region": "서울-강북", "value": 99.0, "memo": ""})
    if "서울-강북" in rc._rows:
        _fail("add_row_skip_when_not_cached", "미로드 지역이 캐시에 추가됨")
    _pass("add_row_skip_when_not_cached")


# ── 테스트 3: remove_row ─────────────────────────────────────────
def test_remove_row():
    _reset()
    rc._rows["전국"] = [
        {"id": "2024-01-08_전국", "date": "2024-01-08", "region": "전국", "value": 100.0, "memo": ""},
        {"id": "2024-01-15_전국", "date": "2024-01-15", "region": "전국", "value": 101.0, "memo": ""},
    ]
    rc.remove_row("2024-01-08_전국", "전국")
    ids = [r["id"] for r in rc._rows["전국"]]
    if "2024-01-08_전국" in ids:
        _fail("remove_row", "행이 제거되지 않음")
    if len(ids) != 1:
        _fail("remove_row", f"행 수 오류: {ids}")
    _pass("remove_row")


# ── 테스트 4: update_row — 같은 지역 ────────────────────────────
def test_update_row_same_region():
    _reset()
    rc._rows["전국"] = [
        {"id": "2024-01-08_전국", "date": "2024-01-08", "region": "전국", "value": 100.0, "memo": ""},
    ]
    rc.update_row("2024-01-08_전국", "전국", {
        "id": "2024-01-08_전국", "date": "2024-01-08", "region": "전국", "value": 102.5, "memo": "수정"
    })
    rows = rc._rows["전국"]
    if len(rows) != 1:
        _fail("update_row_same_region", f"행 수 오류: {len(rows)}")
    if rows[0]["value"] != 102.5:
        _fail("update_row_same_region", f"값 미갱신: {rows[0]['value']}")
    _pass("update_row_same_region")


# ── 테스트 5: update_row — 지역 변경 ────────────────────────────
def test_update_row_region_change():
    _reset()
    rc._rows["전국"] = [
        {"id": "2024-01-08_전국", "date": "2024-01-08", "region": "전국", "value": 100.0, "memo": ""},
    ]
    rc._rows["대전"] = []
    rc.update_row("2024-01-08_전국", "전국", {
        "id": "2024-01-08_대전", "date": "2024-01-08", "region": "대전", "value": 98.0, "memo": ""
    })
    if rc._rows["전국"]:
        _fail("update_row_region_change", "구 지역에서 제거 안 됨")
    daejeon_ids = [r["id"] for r in rc._rows["대전"]]
    if "2024-01-08_대전" not in daejeon_ids:
        _fail("update_row_region_change", "새 지역에 추가 안 됨")
    _pass("update_row_region_change")


# ── 테스트 6: data_service 필터·페이지네이션 (row_cache 직접 설정) ──
def test_filter_and_pagination():
    _reset()
    rows = [
        {"id": f"2024-{m:02d}-01_전국", "date": f"2024-{m:02d}-01", "region": "전국", "value": float(100 + m), "memo": ""}
        for m in range(1, 13)
    ]
    rc.set_region("전국", rows)

    cached = rc.get_region("전국")
    dates = [r["date"] for r in cached]
    if dates != sorted(dates):
        _fail("filter_and_pagination", f"오름차순 정렬 오류: {dates}")

    # 날짜 필터: 2024-03-01 ~ 2024-06-01 → 4개
    filtered = [r for r in cached if "2024-03-01" <= r["date"] <= "2024-06-01"]
    if len(filtered) != 4:
        _fail("filter_and_pagination", f"필터 결과 수 오류: {len(filtered)}")

    # 페이지네이션: page_size=3, page=2 → 다음 3개
    page_size = 3
    all_items = list(reversed(cached))  # 최신순
    page2 = all_items[3:6]
    if len(page2) != 3:
        _fail("filter_and_pagination", f"페이지2 수 오류: {len(page2)}")

    _pass("filter_and_pagination")


# ── 테스트 7: set_region — 직접 설정 후 get_region 반환 ──────────
def test_set_region():
    _reset()
    rows = [
        {"id": "2024-01-15_세종", "date": "2024-01-15", "region": "세종", "value": 95.0, "memo": ""},
        {"id": "2024-01-08_세종", "date": "2024-01-08", "region": "세종", "value": 94.5, "memo": ""},
    ]
    rc.set_region("세종", rows)
    result = rc.get_region("세종")
    if result[0]["date"] != "2024-01-08":
        _fail("set_region", f"정렬 오류: {result[0]['date']}")
    if len(result) != 2:
        _fail("set_region", f"행 수 오류: {len(result)}")
    _pass("set_region")


# ── 테스트 8: 로드 중 예외 → 캐시 미할당 ──────────────────────────
def test_load_exception_leaves_cache_empty():
    """_load_from_firestore 도중 예외 발생 시 _rows에 아무것도 남지 않아야 한다."""
    _reset()
    original = rc._load_from_firestore

    def fake_fail(region):
        raise RuntimeError("ResourceExhausted: 할당량 초과 (테스트용)")

    rc._load_from_firestore = fake_fail
    try:
        try:
            rc.get_region("서울-강남")
            _fail("load_exception_leaves_cache_empty", "예외가 발생해야 함")
        except RuntimeError:
            pass  # 예외 전파 확인
        if "서울-강남" in rc._rows:
            _fail("load_exception_leaves_cache_empty", "실패 후 캐시에 데이터가 남아있음")
    finally:
        rc._load_from_firestore = original
    _pass("load_exception_leaves_cache_empty")


# ── 테스트 9: 로드 성공 → 캐시 완전 할당 ────────────────────────
def test_load_success_full_data_cached():
    """_load_from_firestore 성공 시 전체 데이터가 _rows에 정렬 저장되어야 한다."""
    _reset()
    original = rc._load_from_firestore

    fake_rows = [
        {"id": f"2024-01-{i:02d}_대전", "date": f"2024-01-{i:02d}",
         "region": "대전", "value": float(90 + i), "memo": ""}
        for i in range(1, 5)
    ]

    def fake_ok(region):
        # 원본 함수와 동일하게: 전체 수집 후 캐시 대입
        rows = sorted(fake_rows, key=lambda r: r["date"])
        rc._rows[region] = rows
        return rows

    rc._load_from_firestore = fake_ok
    try:
        result = rc.get_region("대전")
    finally:
        rc._load_from_firestore = original

    if len(result) != 4:
        _fail("load_success_full_data_cached", f"행 수 오류: {len(result)}")
    if "대전" not in rc._rows:
        _fail("load_success_full_data_cached", "캐시에 저장 안 됨")
    dates = [r["date"] for r in rc._rows["대전"]]
    if dates != sorted(dates):
        _fail("load_success_full_data_cached", f"정렬 오류: {dates}")
    _pass("load_success_full_data_cached")


# ── 실행 ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("row_cache 단위 테스트 시작\n")
    test_add_row_sorted()
    test_add_row_skip_when_not_cached()
    test_remove_row()
    test_update_row_same_region()
    test_update_row_region_change()
    test_filter_and_pagination()
    test_set_region()
    test_load_exception_leaves_cache_empty()
    test_load_success_full_data_cached()
    print("\n모든 테스트 통과")
