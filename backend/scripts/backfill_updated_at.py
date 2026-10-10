"""
backfill_updated_at.py — conversations 문서에 updated_at 필드 보정

코드 확인 결과: create_conversation()·add_message() 모두 항상 updated_at을 기록.
이 스크립트는 혹시 생성 이전에 존재했을 구 문서를 대비한 1회성 보정용이다.

실행 방법 (backend/ 폴더에서):
  python scripts/backfill_updated_at.py

주의: Firestore 실제 읽기/쓰기가 발생한다. 할당량 여유가 있을 때 실행할 것.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone
from firebase import db

COLLECTION = "conversations"


def main():
    docs = list(db.collection(COLLECTION).stream())
    print(f"conversations 문서 {len(docs)}건 조회 완료\n")

    patched = 0
    skipped = 0
    for doc in docs:
        data = doc.to_dict()
        if data.get("updated_at"):
            skipped += 1
            continue

        # updated_at 없음: created_at 값으로 채우거나 현재 시각 사용
        fallback = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        doc.reference.update({"updated_at": fallback})
        print(f"  보정: {doc.id} → updated_at = {fallback}")
        patched += 1

    print(f"\n완료: {patched}건 보정, {skipped}건 건너뜀")


if __name__ == "__main__":
    main()
