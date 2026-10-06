"""
summary_service.py — 지역별 요약 계산 및 meta/summary 캐시 관리

compute_and_save_summary(): data 컬렉션 전체를 읽어 요약을 계산하고
                            meta/summary 문서에 저장한다.
get_summary():              저장된 meta/summary 문서를 그대로 반환한다.

요약 항목 (CLAUDE.md 6번 참조):
  - period, count
  - latest, max, min, average
  - from_peak_pct, change_4w_pct, change_52w_pct, change_total_pct
  - trend: direction(상승/하락/보합) + consecutive_weeks
  - 전체: regions, data_period, total_count, index_base_date
"""

from datetime import datetime, timezone

from firebase import db

REGIONS = ["전국", "서울-강북", "서울-강남", "대전", "세종"]
META_DOC = db.collection("meta").document("summary")

# 지수 기준시점 (CLAUDE.md: 2026-07-06 = 100)
INDEX_BASE_DATE = "2026-07-06"


def _pct(current: float, base: float) -> float:
    """(current / base - 1) × 100, 소수 둘째 자리 반올림."""
    return round((current / base - 1) * 100, 2)


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

    # 4주 전: 4 레코드 이전 (인덱스 -5)
    change_4w_pct = _pct(latest_val, values[-5]) if n >= 5 else _pct(latest_val, first_val)
    # 52주 전: 52 레코드 이전 (인덱스 -53)
    change_52w_pct = _pct(latest_val, values[-53]) if n >= 53 else _pct(latest_val, first_val)

    # 추세: 주간 증감 부호 분석
    direction = "보합"
    consecutive_weeks = 0
    if n >= 2:
        changes = [values[i] - values[i - 1] for i in range(1, n)]
        recent = changes[-1]
        if recent > 0:
            direction = "상승"
        elif recent < 0:
            direction = "하락"
        # 연속 상승·하락 주 수 계산
        if direction != "보합":
            for c in reversed(changes):
                if (direction == "상승" and c > 0) or (direction == "하락" and c < 0):
                    consecutive_weeks += 1
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
            "direction": direction,
            "consecutive_weeks": consecutive_weeks,
        },
    }


def compute_and_save_summary() -> None:
    """data 컬렉션 전체를 읽어 요약을 계산하고 meta/summary에 저장한다."""
    # data 컬렉션 전체 읽기
    docs = db.collection("data").stream()

    # 지역별로 레코드 분류
    by_region: dict[str, list[dict]] = {r: [] for r in REGIONS}
    all_dates: list[str] = []

    for doc in docs:
        d = doc.to_dict()
        region = d.get("region", "")
        if region in by_region:
            by_region[region].append({
                "date": d["date"],
                "value": float(d["value"]),
            })
            all_dates.append(d["date"])

    # 각 지역 날짜 오름차순 정렬 후 통계 계산
    region_stats: dict[str, dict] = {}
    for region, records in by_region.items():
        if not records:
            continue
        records.sort(key=lambda r: r["date"])
        region_stats[region] = _compute_region_stats(records)

    total_count = sum(s["count"] for s in region_stats.values())
    all_dates_sorted = sorted(set(all_dates))

    summary = {
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
    }

    META_DOC.set(summary)
    print(f"[summary] meta/summary 저장 완료 (총 {total_count}건)")


def get_summary() -> dict:
    """저장된 meta/summary 문서를 반환한다. 없으면 빈 dict."""
    doc = META_DOC.get()
    if not doc.exists:
        return {}
    return doc.to_dict()
