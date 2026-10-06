"""
seed_data.py — CSV → Firestore data 컬렉션 업로드

사용법:
  # 드라이런: Firestore 연결 확인 + CSV 건수 출력만, 쓰기 없음
  python -m scripts.seed_data --dry-run

  # 실제 업로드
  python -m scripts.seed_data

실행 위치: backend/ 디렉토리 (python -m scripts.seed_data)

문서 ID: {date}_{region}  예) 2026-09-28_세종
배치 쓰기: 500건 단위 (Firestore 배치 한도)
업로드 후: 지역별 건수를 Firestore에서 다시 세어 검증 출력
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

# backend/ 를 sys.path에 추가 (scripts/ 하위에서 config, firebase import)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from firebase import db  # noqa: E402 (경로 설정 후 import)

# ── 상수 ──────────────────────────────────────────────────
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "apt_price_index_weekly.csv")
COLLECTION = "data"
BATCH_SIZE = 500
VALID_REGIONS = {"전국", "서울-강북", "서울-강남", "대전", "세종"}


def load_csv(path: str) -> list[dict]:
    """CSV를 읽어 레코드 리스트로 반환한다. UTF-8 BOM 처리 포함."""
    records = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = row["region"].strip()
            if region not in VALID_REGIONS:
                print(f"  [경고] 알 수 없는 지역 건너뜀: {region!r}")
                continue
            records.append({
                "date": row["date"].strip(),
                "region": region,
                "value": float(row["value"]),
                "memo": row["memo"].strip(),
            })
    return records


def print_summary(records: list[dict]) -> None:
    """CSV 건수 요약을 출력한다."""
    from collections import Counter
    counter = Counter(r["region"] for r in records)
    print(f"\nCSV 총 건수: {len(records)}")
    for region in sorted(counter):
        print(f"  {region}: {counter[region]}건")


def upload(records: list[dict]) -> None:
    """500건 단위 배치 쓰기로 Firestore에 업로드한다."""
    total = len(records)
    uploaded = 0
    now = datetime.now(timezone.utc)

    # 배치를 BATCH_SIZE 단위로 나눠 처리
    for start in range(0, total, BATCH_SIZE):
        chunk = records[start : start + BATCH_SIZE]
        batch = db.batch()

        for r in chunk:
            doc_id = f"{r['date']}_{r['region']}"
            doc_ref = db.collection(COLLECTION).document(doc_id)
            batch.set(doc_ref, {
                "date": r["date"],
                "region": r["region"],
                "value": r["value"],
                "memo": r["memo"],
                "created_at": now,
            })

        batch.commit()
        uploaded += len(chunk)
        print(f"  업로드 진행: {uploaded}/{total}")

    print(f"\n업로드 완료: 총 {uploaded}건")


def verify() -> None:
    """Firestore data 컬렉션에서 지역별 건수를 세어 검증 출력한다."""
    print("\nFirestore 검증 중...")
    from collections import Counter
    counter: Counter = Counter()

    docs = db.collection(COLLECTION).stream()
    for doc in docs:
        data = doc.to_dict()
        counter[data.get("region", "??")] += 1

    total = sum(counter.values())
    print(f"Firestore 총 건수: {total}")
    for region in sorted(counter):
        status = "OK" if counter[region] == 720 else "!!"
        print(f"  [{status}] {region}: {counter[region]}건 (기대값 720)")

    if total == 3600:
        print("\n검증 통과: 3,600건 정상 확인")
    else:
        print(f"\n[경고] 총 건수 불일치 — 기대값 3600, 실제 {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV → Firestore 업로드")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Firestore 연결 확인 + CSV 건수만 출력, 실제 쓰기 안 함",
    )
    args = parser.parse_args()

    print(f"CSV 경로: {os.path.abspath(CSV_PATH)}")
    records = load_csv(CSV_PATH)
    print_summary(records)

    if args.dry_run:
        # Firestore 연결만 확인 (쓰기 없음)
        print("\n[dry-run] Firestore 연결 확인 중...")
        db.collection(COLLECTION).limit(1).get()
        print("[dry-run] Firestore 연결 OK — 쓰기는 하지 않음")
        return

    print("\n업로드를 시작합니다...")
    upload(records)
    verify()


if __name__ == "__main__":
    main()
