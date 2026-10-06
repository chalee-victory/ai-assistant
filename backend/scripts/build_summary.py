"""
build_summary.py — meta/summary 문서를 처음 생성하거나 강제 재계산한다.

seed_data.py 실행 직후, 또는 data 컬렉션을 외부에서 직접 수정했을 때 사용.

실행 위치: backend/
  python -m scripts.build_summary
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.summary_service import compute_and_save_summary, get_summary  # noqa: E402

if __name__ == "__main__":
    print("요약 계산 중 (data 컬렉션 전체 읽기)...")
    compute_and_save_summary()

    # 저장된 내용 간단히 확인
    summary = get_summary()
    print(f"\n[확인] 기준 기간: {summary.get('data_period')}")
    print(f"[확인] 총 건수: {summary.get('total_count')}")
    for region, stats in summary.get("by_region", {}).items():
        trend = stats.get("trend", {})
        print(
            f"  {region}: 최신 {stats['latest']['value']} ({stats['latest']['date']}) | "
            f"추세 {trend.get('direction')} {trend.get('consecutive_weeks')}주"
        )
