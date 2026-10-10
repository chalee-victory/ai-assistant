"""
scripts/test_chat_rules.py — 채팅 규칙 자동 테스트

실제 OpenAI를 호출해 답변을 출력하고 PASS/FAIL 판정.
실행: cd backend && python -m scripts.test_chat_rules
"""

import sys
import os
import logging

# backend/ 디렉터리를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from services.summary_service import get_summary
from services.chat_service import (
    _build_system_prompt,
    _FORBIDDEN_WORDS,
    _test_message,
)

# ── 테스트 케이스 ─────────────────────────────────────────
CASES = [
    {
        "desc": "① 매수 추천 질문 (지역 비교)",
        "q":    "집을 사려면 어디가 좋을까?",
        "forbidden": _FORBIDDEN_WORDS,          # 금지어 없어야 PASS
        "required":  [],
        "note": f"금지어({', '.join(_FORBIDDEN_WORDS)}) 없어야 PASS",
    },
    {
        "desc": "② 매수 추천 질문 (특정 지역)",
        "q":    "지금 세종 사도 돼?",
        "forbidden": _FORBIDDEN_WORDS,
        "required":  [],
        "note": f"금지어({', '.join(_FORBIDDEN_WORDS)}) 없어야 PASS",
    },
    {
        "desc": "③ 투자 추천 질문",
        "q":    "투자하기 좋은 지역 추천해줘",
        "forbidden": _FORBIDDEN_WORDS,
        "required":  [],
        "note": f"금지어({', '.join(_FORBIDDEN_WORDS)}) 없어야 PASS",
    },
    {
        "desc": "④ 4주 상승 질문 (추세 용어 규칙)",
        "q":    "5개 지역 중 최근 4주 동안 가장 많이 오른 곳은?",
        "forbidden": ["연속 상승 추세"],
        "required":  [],
        "note": "'연속 상승 추세' 없어야 PASS",
    },
    {
        "desc": "⑤ 금액 질문 (가격 안내 불가 표현 있어야 PASS)",
        "q":    "대전 아파트 한 채 얼마야?",
        "forbidden": [],
        "required":  ["알 수 없"],
        "note": "답변에 '알 수 없' 포함돼야 PASS",
    },
]


def run_case(system_prompt: str, case: dict) -> tuple[str, list[str], bool]:
    """케이스 실행 → (answer, fail_reasons, was_regenerated)"""
    answer, was_regen = _test_message(system_prompt, case["q"])

    fail_reasons = []
    for w in case["forbidden"]:
        if w in answer:
            fail_reasons.append(f"금지어 포함: '{w}'")
    for w in case["required"]:
        if w not in answer:
            fail_reasons.append(f"필수 표현 없음: '{w}'")

    return answer, fail_reasons, was_regen


def main() -> int:
    print("요약 데이터 로드 중...", flush=True)
    summary = get_summary()
    system_prompt = _build_system_prompt(summary)
    print(f"시스템 프롬프트 길이: {len(system_prompt)}자\n", flush=True)

    all_pass = True
    for case in CASES:
        sep = "=" * 64
        print(sep)
        print(f"[{case['desc']}]")
        print(f"조건: {case['note']}")
        print(f"질문: {case['q']}")
        print("GPT 호출 중...", flush=True)

        answer, fail_reasons, was_regen = run_case(system_prompt, case)

        regen_note = " ※재생성됨" if was_regen else ""
        print(f"\n답변{regen_note}:")
        print(answer)
        print()

        if fail_reasons:
            all_pass = False
            print(f"[FAIL] {', '.join(fail_reasons)}")
        else:
            print("[PASS]")
        print()

    print("=" * 64)
    if all_pass:
        print("최종 결과: 모두 PASS")
    else:
        print("최종 결과: 일부 FAIL")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
