"""
summary_service.py — 지역별 요약 계산 및 meta/summary 캐시 관리

compute_and_save_summary(): data 전체를 읽어 모든 지역 요약을 재계산한다. (build_summary용)
compute_and_save_region():  row_cache 를 사용해 해당 지역 요약만 갱신한다. (CRUD용)
get_summary():              메모리 캐시를 우선 반환, 없으면 Firestore 1건 읽기.

추세 필드 구조:
  - trend  : { direction, change_4w_pct }  — 4주 변화율 기준 큰 흐름
             direction: change_4w_pct 부호 기준. |값| < 0.05% → 보합
  - streak : { direction, weeks }          — 직전 주 변화 기준 단기 흐름
             direction: 직전 주 증감 부호 기준. 0이면 보합
             weeks: 그 방향으로 연속된 주 수

변화율 기준:
  - change_4w_pct  : 최신 날짜 − 28일 이하인 가장 가까운 날짜의 값과 비교
  - change_52w_pct : 최신 날짜 − 364일 이하인 가장 가까운 날짜의 값과 비교
  (행 인덱스가 아닌 실제 날짜 기준 → 연휴 공백 주 영향 없음)
"""

from datetime import datetime, timedelta, timezone

from firebase import db
from services import row_cache

# ── 요약 메모리 캐시 (CRUD 시 무효화, TTL 없음) ──────────────────
_summary: dict = {}
_summary_valid: bool = False


def _invalidate_summary() -> None:
    global _summary_valid
    _summary_valid = False

REGIONS = ["전국", "서울-강북", "서울-강남", "대전", "세종"]
META_DOC = db.collection("meta").document("summary")

# 지수 기준시점 (CLAUDE.md: 2026-07-06 = 100)
INDEX_BASE_DATE = "2026-07-06"
# 추세 보합 임계값: |change_4w_pct| 가 이 값 미만이면 "보합"
TREND_FLAT_THRESHOLD = 0.05


def _pct(current: float, base: float) -> float:
    """(current / base - 1) × 100, 소수 둘째 자리 반올림."""
    return round((current / base - 1) * 100, 2)


def _find_value_before(dates: list[str], values: list[float], days: int) -> float | None:
    """최신 날짜에서 days일 전(이하)인 날짜 중 가장 최근 날짜의 값을 반환한다.

    dates는 오름차순 정렬 상태여야 한다. 현재(마지막) 값은 제외하고 탐색한다.
    """
    latest_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
    target_dt = latest_dt - timedelta(days=days)

    # 뒤에서부터 탐색해 target 이하인 첫 번째 날짜를 반환
    for i in range(len(dates) - 2, -1, -1):
        if datetime.strptime(dates[i], "%Y-%m-%d") <= target_dt:
            return values[i]
    return None  # 해당 기간보다 오래된 데이터 없음


def _compute_region_stats(records: list[dict]) -> dict:
    """날짜 오름차순으로 정렬된 레코드 리스트에서 지역별 통계를 계산한다."""
    values = [r["value"] for r in records]
    dates = [r["date"] for r in records]
    n = len(values)

    max_val = max(values)
    max_date = dates[values.index(max_val)]
    min_val = min(values)
    min_date = dates[values.index(min_val)]
    latest_val = values[-1]
    latest_date = dates[-1]
    first_val = values[0]

    # ── 변화율: 날짜 기준 (행 인덱스 아님) ──────────────────────
    val_4w = _find_value_before(dates, values, 28)
    change_4w_pct = _pct(latest_val, val_4w) if val_4w is not None else _pct(latest_val, first_val)

    val_52w = _find_value_before(dates, values, 364)
    change_52w_pct = _pct(latest_val, val_52w) if val_52w is not None else _pct(latest_val, first_val)

    # ── trend: 4주 변화율 기준 큰 흐름 ──────────────────────────
    if abs(change_4w_pct) < TREND_FLAT_THRESHOLD:
        trend_direction = "보합"
    elif change_4w_pct > 0:
        trend_direction = "상승"
    else:
        trend_direction = "하락"

    # ── streak: 직전 주 변화 기준 단기 흐름 ──────────────────────
    streak_direction = "보합"
    streak_weeks = 0
    if n >= 2:
        changes = [values[i] - values[i - 1] for i in range(1, n)]
        last_change = changes[-1]
        if last_change > 0:
            streak_direction = "상승"
        elif last_change < 0:
            streak_direction = "하락"
        # 연속 주 수: streak_direction 과 같은 방향이 연속된 주 수
        for c in reversed(changes):
            if streak_direction == "상승" and c > 0:
                streak_weeks += 1
            elif streak_direction == "하락" and c < 0:
                streak_weeks += 1
            elif streak_direction == "보합" and c == 0:
                streak_weeks += 1
            else:
                break

    return {
        "period": {"start": dates[0], "end": dates[-1]},
        "count": n,
        "latest": {"value": latest_val, "date": latest_date},
        "max": {"value": max_val, "date": max_date},
        "min": {"value": min_val, "date": min_date},
        "average": round(sum(values) / n, 2),
        "from_peak_pct": _pct(latest_val, max_val),
        "change_4w_pct": change_4w_pct,
        "change_52w_pct": change_52w_pct,
        "change_total_pct": _pct(latest_val, first_val),
        "trend": {
            "direction": trend_direction,
            "change_4w_pct": change_4w_pct,
        },
        "streak": {
            "direction": streak_direction,
            "weeks": streak_weeks,
        },
    }


# ── 전체 재계산 (build_summary 스크립트용) ──────────────────────
def compute_and_save_summary() -> None:
    """data 컬렉션 전체를 읽어 모든 지역 요약을 재계산하고 meta/summary에 저장한다."""
    docs = db.collection("data").stream()

    by_region: dict[str, list[dict]] = {r: [] for r in REGIONS}
    all_dates: list[str] = []

    for doc in docs:
        d = doc.to_dict()
        region = d.get("region", "")
        if region in by_region:
            by_region[region].append({"date": d["date"], "value": float(d["value"])})
            all_dates.append(d["date"])

    region_stats: dict[str, dict] = {}
    for region, records in by_region.items():
        if not records:
            continue
        records.sort(key=lambda r: r["date"])
        region_stats[region] = _compute_region_stats(records)

    total_count = sum(s["count"] for s in region_stats.values())
    all_dates_sorted = sorted(set(all_dates))

    META_DOC.set({
        "regions": REGIONS,
        "index_base_date": INDEX_BASE_DATE,
        "index_base_value": 100.0,
        "data_period": {
            "start": all_dates_sorted[0] if all_dates_sorted else "",
            "end": all_dates_sorted[-1] if all_dates_sorted else "",
        },
        "total_count": total_count,
        "by_region": region_stats,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _invalidate_summary()
    print(f"[summary] meta/summary 전체 저장 완료 (총 {total_count}건)")


# ── 단일 지역 갱신 (CRUD 후 호출) ──────────────────────────────
def compute_and_save_region(region: str) -> None:
    """row_cache 를 사용해 해당 지역 요약만 갱신한다 (Firestore 읽기 0건).

    meta/summary 문서가 없으면 전체 재계산으로 폴백한다.
    """
    # 1. row_cache 에서 해당 지역 행 취득 (Firestore 읽기 0건)
    cached = row_cache.get_region(region)
    records = [{"date": r["date"], "value": r["value"]} for r in cached]

    new_stats = _compute_region_stats(records) if records else {}

    # 2. 기존 meta/summary 읽기 (1건) — 다른 지역 수치를 보존하기 위해
    existing = META_DOC.get()
    if not existing.exists:
        print(f"[summary] meta/summary 없음 → 전체 재계산으로 폴백")
        compute_and_save_summary()
        return

    by_region: dict = existing.to_dict().get("by_region", {})
    by_region[region] = new_stats

    # total_count: 모든 지역 건수 합산
    total_count = sum(s.get("count", 0) for s in by_region.values())

    # data_period: 모든 지역 period 의 min start / max end
    periods = [s["period"] for s in by_region.values() if s.get("period")]
    data_period = {
        "start": min(p["start"] for p in periods) if periods else "",
        "end": max(p["end"] for p in periods) if periods else "",
    }

    # 변경된 필드만 업데이트 (다른 지역 항목 덮어쓰기 없음)
    META_DOC.update({
        f"by_region.{region}": new_stats,
        "total_count": total_count,
        "data_period": data_period,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _invalidate_summary()
    print(f"[summary] {region} 요약 갱신 완료 ({len(records)}건)")


def get_summary() -> dict:
    """메모리 캐시가 유효하면 즉시 반환, 아니면 Firestore 1건 읽기 후 캐시에 저장."""
    global _summary, _summary_valid
    if _summary_valid:
        return _summary
    doc = META_DOC.get()
    if not doc.exists:
        return {}
    _summary = doc.to_dict()
    _summary_valid = True
    return _summary
