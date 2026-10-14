"""
test_series.py — GET /api/data/series (추이 그래프 API) 테스트 (Firestore·OpenAI 접근 없음)

원본 CSV를 메모리 캐시(row_cache)에 미리 채운 뒤, 실제 FastAPI 앱(main.app)에
TestClient로 요청을 보내 확인한다. firebase 모듈은 가짜로 바꿔 끼우므로
키나 인터넷 연결 없이 실행된다.

실행 방법 (backend/ 폴더에서, venv 활성화):
  python scripts/test_series.py
"""

import csv
import os
import sys
import types
from unittest.mock import MagicMock

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

# ── 외부 연결 차단: 가짜 firebase 모듈 + 더미 환경변수 ─────────────
_fake_fb = types.ModuleType("firebase")
_fake_fb.db = MagicMock()   # 호출 기록용 가짜 Firestore (캐시가 채워져 있으면 쓰이지 않아야 한다)
sys.modules["firebase"] = _fake_fb
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")
os.environ.setdefault("FIREBASE_SERVICE_ACCOUNT_JSON", "{}")   # config 검사 통과용 (실제 사용 안 함)

from fastapi.testclient import TestClient  # noqa: E402

import services.row_cache as rc  # noqa: E402
from main import app  # noqa: E402

CSV_PATH = os.path.join(BACKEND, "data", "apt_price_index_weekly.csv")


def _fill_cache_from_csv() -> None:
    """원본 CSV 3,600행을 지역별로 캐시에 채운다."""
    rows: dict[str, list[dict]] = {r: [] for r in rc.REGIONS}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows[r["region"]].append({
                "id":     f'{r["date"]}_{r["region"]}',
                "date":   r["date"],
                "region": r["region"],
                "value":  float(r["value"]),
                "memo":   r.get("memo", ""),
            })
    for region, lst in rows.items():
        rc.set_region(region, lst)


def _pass(name):
    print(f"  PASS  {name}")


def _fail(name, msg):
    print(f"  FAIL  {name}: {msg}")
    sys.exit(1)


client = TestClient(app)


# ── 테스트 1: 5개 지역 모두 720건, 날짜 오름차순 ─────────────────
def test_all_regions_full():
    for region in rc.REGIONS:
        res = client.get("/api/data/series", params={"region": region})
        if res.status_code != 200:
            _fail("all_regions_full", f"{region} HTTP {res.status_code} {res.text}")
        body = res.json()
        dates = [p["date"] for p in body["points"]]
        if body["count"] != 720 or len(dates) != 720:
            _fail("all_regions_full", f"{region} 건수 {body['count']}")
        if dates != sorted(dates):
            _fail("all_regions_full", f"{region} 날짜 정렬 오류")
        if dates[0] != "2012-11-26" or dates[-1] != "2026-09-28":
            _fail("all_regions_full", f"{region} 기간 {dates[0]}~{dates[-1]}")
    _pass("all_regions_full (5개 지역 × 720건, 오름차순, 2012-11-26~2026-09-28)")


# ── 테스트 2: 기준시점 2026-07-06 = 100.00 ───────────────────────
def test_base_point_100():
    for region in rc.REGIONS:
        body = client.get(
            "/api/data/series",
            params={"region": region, "start_date": "2026-07-06", "end_date": "2026-07-06"},
        ).json()
        if body["count"] != 1 or body["points"][0]["value"] != 100.0:
            _fail("base_point_100", f"{region} {body}")
    _pass("base_point_100 (기준시점 값 100.00)")


# ── 테스트 3: 기간 필터 (양 끝 포함) ─────────────────────────────
def test_date_filter():
    body = client.get(
        "/api/data/series",
        params={"region": "세종", "start_date": "2025-09-29", "end_date": "2026-09-28"},
    ).json()
    dates = [p["date"] for p in body["points"]]
    if not dates or dates[0] < "2025-09-29" or dates[-1] > "2026-09-28":
        _fail("date_filter", f"범위 밖 날짜 포함: {dates[:1]}~{dates[-1:]}")
    if dates[-1] != "2026-09-28":
        _fail("date_filter", "종료일 당일이 빠짐")
    _pass(f"date_filter (최근 1년 {body['count']}건)")


# ── 테스트 4: 잘못된 지역 → 422 한국어 안내 ─────────────────────
def test_invalid_region():
    res = client.get("/api/data/series", params={"region": "부산"})
    if res.status_code != 422 or "전국·서울-강북" not in res.json().get("detail", ""):
        _fail("invalid_region", f"HTTP {res.status_code} {res.text}")
    res = client.get("/api/data/series")
    if res.status_code != 422 or "필수" not in res.json().get("detail", ""):
        _fail("invalid_region", f"지역 누락 HTTP {res.status_code} {res.text}")
    _pass("invalid_region (422 + 한국어 안내)")


# ── 테스트 5: CRUD가 캐시에 반영되면 그래프에도 즉시 반영 ───────────
def test_reflects_cache_update():
    new_row = {"id": "2026-10-05_대전", "date": "2026-10-05", "region": "대전", "value": 100.50, "memo": ""}
    rc.add_row(new_row)
    last = client.get("/api/data/series", params={"region": "대전"}).json()["points"][-1]
    rc.remove_row("2026-10-05_대전", "대전")   # 원상 복구
    if last != {"date": "2026-10-05", "value": 100.5}:
        _fail("reflects_cache_update", f"마지막 점 {last}")
    after = client.get("/api/data/series", params={"region": "대전"}).json()
    if after["count"] != 720:
        _fail("reflects_cache_update", f"복구 후 {after['count']}건")
    _pass("reflects_cache_update (추가·삭제 즉시 반영)")


# ── 테스트 7: 캐시 적중 시 Firestore 읽기 0건 ────────────────────
def test_no_firestore_reads():
    calls = _fake_fb.db.collection.call_count
    if calls != 0:
        _fail("no_firestore_reads", f"Firestore collection() 호출 {calls}회")
    _pass("no_firestore_reads (캐시 적중 시 Firestore 읽기 0건)")


# ── 테스트 6: 기존 경로(/summary 아닌 목록 조회)와 충돌 없음 ──────────
def test_list_route_intact():
    res = client.get("/api/data", params={"region": "전국", "page_size": 5})
    if res.status_code != 200 or res.json()["total"] != 720:
        _fail("list_route_intact", f"HTTP {res.status_code} {res.text[:120]}")
    _pass("list_route_intact (GET /api/data 정상)")


if __name__ == "__main__":
    print("test_series — 추이 그래프 API")
    _fill_cache_from_csv()
    _fake_fb.db.reset_mock()   # 모듈 import 때의 호출 기록은 제외
    test_all_regions_full()
    test_base_point_100()
    test_date_filter()
    test_invalid_region()
    test_reflects_cache_update()
    test_list_route_intact()
    test_no_firestore_reads()
    print("모든 테스트 통과 (7/7)")
