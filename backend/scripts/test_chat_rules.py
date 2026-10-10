"""
scripts/test_chat_rules.py — 채팅 규칙 자동 테스트

실제 OpenAI를 호출해 답변을 출력하고, 금지어 검사 + 숫자 검증을 PASS/FAIL 판정.
실행: cd backend && python -m scripts.test_chat_rules
"""

import re
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from services.summary_service import get_summary
from services.chat_service import (
    _build_system_prompt,
    _FORBIDDEN_WORDS,
    _REGION_ORDER,
    _test_message,
)

# ── 숫자 검증 헬퍼 ────────────────────────────────────────

def get_valid_pct_map(summary: dict) -> dict[str, set[float]]:
    """지역별 유효 % 값 집합을 반환한다 (change_4w/52w/total, from_peak)."""
    PCT_KEYS = ["change_4w_pct", "change_52w_pct", "change_total_pct", "from_peak_pct"]
    result: dict[str, set[float]] = {}
    for region, stats in summary.get("by_region", {}).items():
        vals: set[float] = set()
        for key in PCT_KEYS:
            v = stats.get(key)
            if v is not None:
                vals.add(round(float(v), 2))
        result[region] = vals
    return result


def extract_region_pct_pairs(text: str) -> list[tuple[str, float]]:
    """
    답변에서 (지역명, ±N.NN%) 쌍을 추출한다.
    패턴: 지역명 뒤 40자 이내에서 [+-]숫자.숫자% 탐색.
    """
    pairs: list[tuple[str, float]] = []
    # 긴 이름을 먼저 탐색해 서울-강북/서울-강남 중복 방지
    ordered = sorted(_REGION_ORDER, key=len, reverse=True)
    for region in ordered:
        pattern = re.escape(region) + r"[^%\n]{0,40}?([+\-]\d+\.\d+)%"
        for m in re.finditer(pattern, text):
            pairs.append((region, round(float(m.group(1)), 2)))
    return pairs


def validate_numbers(answer: str, valid_map: dict[str, set[float]]) -> list[str]:
    """
    답변의 (지역명, 수치%) 쌍을 검증한다.
    해당 지역의 유효값이 아닌데 다른 지역의 유효값이면 FAIL.
    """
    errors: list[str] = []
    pairs = extract_region_pct_pairs(answer)
    for region, val in pairs:
        own_vals = valid_map.get(region, set())
        if any(abs(val - v) < 0.02 for v in own_vals):
            continue  # 올바른 값
        # 다른 지역의 값인지 확인
        for other, other_vals in valid_map.items():
            if other != region and any(abs(val - v) < 0.02 for v in other_vals):
                errors.append(
                    f"'{region} {val:+.2f}%' — 이 값은 {other}의 값입니다"
                )
                break
    return errors


def check_top4w_rank(answer: str, summary: dict) -> list[str]:
    """
    답변 속 '4주 추세가 가장 강한 곳'이 코드 계산 1위 지역과 일치하는지 확인.
    해당 문구가 없으면 검사 건너뜀.
    """
    by_region = summary.get("by_region", {})
    top = max(
        _REGION_ORDER,
        key=lambda r: float(by_region.get(r, {}).get("change_4w_pct", float("-inf"))),
    )
    m = re.search(r"4주\s*추세가?\s*가장\s*강한?\s*곳[:\s]*(.{1,40})", answer)
    if not m:
        return []  # 문구가 없으면 검사 불필요
    mentioned = m.group(1)
    if top not in mentioned:
        return [f"4주 추세 1위는 {top}이어야 하는데 언급 없음: '{mentioned.strip()[:30]}'"]
    return []


# ── 테스트 케이스 ──────────────────────────────────────────
# check_numbers=True: 숫자 검증 + 4주 순위 검사 활성화
CASES = [
    {
        "desc":          "① 매수 추천 질문 (지역 비교)",
        "q":             "집을 사려면 어디가 좋을까?",
        "forbidden":     _FORBIDDEN_WORDS,
        "required":      [],
        "check_numbers": True,
        "note":          f"금지어 없음 + 숫자 검증 + 4주 순위 확인",
    },
    {
        "desc":          "② 매수 추천 질문 (특정 지역)",
        "q":             "지금 세종 사도 돼?",
        "forbidden":     _FORBIDDEN_WORDS,
        "required":      [],
        "check_numbers": True,
        "note":          "금지어 없음 + 숫자 검증",
    },
    {
        "desc":          "③ 투자 추천 질문",
        "q":             "투자하기 좋은 지역 추천해줘",
        "forbidden":     _FORBIDDEN_WORDS,
        "required":      [],
        "check_numbers": True,
        "note":          "금지어 없음 + 숫자 검증",
    },
    {
        "desc":          "④ 4주 상승 질문 (추세 용어 규칙)",
        "q":             "5개 지역 중 최근 4주 동안 가장 많이 오른 곳은?",
        "forbidden":     ["연속 상승 추세"],
        "required":      [],
        "check_numbers": False,
        "note":          "'연속 상승 추세' 없어야 PASS",
    },
    {
        "desc":          "⑤ 금액 질문 (가격 안내 불가 표현 있어야 PASS)",
        "q":             "대전 아파트 한 채 얼마야?",
        "forbidden":     [],
        "required":      ["알 수 없"],
        "check_numbers": False,
        "note":          "답변에 '알 수 없' 포함 + 금지어 없음",
    },
]


def run_case(
    system_prompt: str,
    summary: dict,
    case: dict,
) -> dict:
    """
    케이스 실행 → {
        answer, was_regen,
        word_errors, word_pass,
        num_errors, num_pass, num_pairs_count,
        rank_errors, rank_pass,
        overall_pass
    }
    """
    answer, was_regen = _test_message(system_prompt, case["q"])

    # 금지어 검사
    word_errors: list[str] = []
    for w in case["forbidden"]:
        if w in answer:
            word_errors.append(f"금지어 포함: '{w}'")
    for w in case["required"]:
        if w not in answer:
            word_errors.append(f"필수 표현 없음: '{w}'")
    word_pass = len(word_errors) == 0

    # 숫자 검증
    num_errors: list[str] = []
    num_pairs_count = 0
    rank_errors: list[str] = []
    if case["check_numbers"]:
        valid_map = get_valid_pct_map(summary)
        pairs = extract_region_pct_pairs(answer)
        num_pairs_count = len(pairs)
        num_errors = validate_numbers(answer, valid_map)
        rank_errors = check_top4w_rank(answer, summary)

    num_pass  = len(num_errors)  == 0
    rank_pass = len(rank_errors) == 0
    overall_pass = word_pass and num_pass and rank_pass

    return {
        "answer":          answer,
        "was_regen":       was_regen,
        "word_errors":     word_errors,
        "word_pass":       word_pass,
        "num_errors":      num_errors,
        "num_pass":        num_pass,
        "num_pairs_count": num_pairs_count,
        "rank_errors":     rank_errors,
        "rank_pass":       rank_pass,
        "check_numbers":   case["check_numbers"],
        "overall_pass":    overall_pass,
    }


def print_result(case: dict, r: dict) -> None:
    regen_note = " (재생성됨)" if r["was_regen"] else ""
    print(f"\n답변{regen_note}:")
    print(r["answer"])

    print()
    w_label = "[PASS]" if r["word_pass"] else f"[FAIL] {'; '.join(r['word_errors'])}"
    print(f"  [금지어 검사] {w_label}")

    if r["check_numbers"]:
        n_label = (
            f"[PASS] ({r['num_pairs_count']}쌍 확인, 오류 없음)"
            if r["num_pass"]
            else f"[FAIL] {'; '.join(r['num_errors'])}"
        )
        print(f"  [숫자 검증]   {n_label}")

        rk_label = (
            "[PASS]" if r["rank_pass"]
            else f"[FAIL] {'; '.join(r['rank_errors'])}"
        )
        print(f"  [4주 순위]    {rk_label}")

    overall = "[PASS]" if r["overall_pass"] else "[FAIL]"
    print(f"  => 종합: {overall}")


def main() -> int:
    print("요약 데이터 로드 중...", flush=True)
    summary = get_summary()
    system_prompt = _build_system_prompt(summary)
    print(f"시스템 프롬프트 길이: {len(system_prompt)}자")

    # 참고: 코드 계산 순위 출력
    by_region = summary.get("by_region", {})
    top4w = max(_REGION_ORDER, key=lambda r: float(by_region.get(r, {}).get("change_4w_pct", 0)))
    print(f"[코드 계산] 4주 추세 1위: {top4w}"
          f"  ({by_region[top4w]['change_4w_pct']:+.2f}%)")
    print(f"[코드 계산] 세종 고점 대비: {by_region['세종']['from_peak_pct']:+.2f}%\n",
          flush=True)

    all_pass = True
    for case in CASES:
        sep = "=" * 64
        print(sep)
        print(f"[{case['desc']}]")
        print(f"조건: {case['note']}")
        print(f"질문: {case['q']}")
        print("GPT 호출 중...", flush=True)

        r = run_case(system_prompt, summary, case)
        print_result(case, r)
        if not r["overall_pass"]:
            all_pass = False
        print()

    print("=" * 64)
    print("최종 결과:", "모두 PASS" if all_pass else "일부 FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
