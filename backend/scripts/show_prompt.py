"""
show_prompt.py — 현재 조립되는 시스템 프롬프트 전문을 콘솔에 출력한다.

OpenAI 호출 없이 meta/summary만 읽어 프롬프트를 확인한다.
채팅 답변 품질 튜닝 시 활용.

실행 위치: backend/
  python -m scripts.show_prompt
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.chat_service import _build_system_prompt  # noqa: E402
from services.summary_service import get_summary         # noqa: E402

if __name__ == "__main__":
    summary = get_summary()
    if not summary:
        print("[오류] meta/summary 문서가 없습니다. build_summary를 먼저 실행하세요.")
        sys.exit(1)

    prompt = _build_system_prompt(summary)

    print("=" * 60)
    print(prompt)
    print("=" * 60)
    print(f"\n총 길이: {len(prompt)}자")
