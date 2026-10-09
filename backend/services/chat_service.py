"""
chat_service.py — AI 채팅 핵심 로직

처리 순서:
  1. meta/summary 캐시 1건 읽기 (data 컬렉션은 읽지 않음)
  2. 요약 데이터로 시스템 프롬프트 조립 + 길이 콘솔 출력
  3. conversation_id 없으면 새 대화 생성, 있으면 기존 대화 조회
  4. 최근 10개 메시지를 GPT 입력으로 변환
  5. GPT 호출 (max_tokens=500, temperature=0.3)
  6. user → assistant 순서로 대화에 저장
  7. 새 대화면 첫 질문 앞 20자를 제목으로 자동 설정
  8. conversation_id + 답변 반환

분업 원칙: 수치 계산은 Python(summary_service), 해석·문장화는 GPT.
"""

import openai
from fastapi import HTTPException

from config import OPENAI_API_KEY, OPENAI_MODEL
from firebase import db
from schemas import ChatRequest, ChatResponse, ConversationCreate
from services.conversation_service import add_message, create_conversation, get_conversation
from services.summary_service import get_summary

_client = openai.OpenAI(api_key=OPENAI_API_KEY)

MAX_HISTORY = 10  # GPT에 전달하는 최근 대화 이력 개수


# ── 시스템 프롬프트 조립 ─────────────────────────────────────
def _build_system_prompt(summary: dict) -> str:
    """meta/summary 데이터를 GPT 시스템 프롬프트 문자열로 조립한다."""
    base_date = summary.get("index_base_date", "2026-07-06")
    period = summary.get("data_period", {})
    total = summary.get("total_count", 0)
    updated_at = summary.get("updated_at", "")

    lines = [
        "당신은 한국부동산원 주간 아파트 매매가격지수 분석 비서입니다.",
        "아래 데이터를 근거로 사용자 질문에 한국어로 간결하게 답하세요.",
        "수치 계산은 이미 완료된 값만 사용하고, 해석과 설명을 담당합니다.",
        "",
        "## 데이터 범위",
        f"- 대상 지역: 전국, 서울-강북, 서울-강남, 대전, 세종 (5개)",
        f"- 데이터 기간: {period.get('start', '')} ~ {period.get('end', '')} | 총 {total}건",
        f"- 요약 갱신 시각: {updated_at}",
        "",
        "## 지역별 요약",
    ]

    for region, stats in summary.get("by_region", {}).items():
        latest = stats.get("latest", {})
        peak   = stats.get("max", {})
        trough = stats.get("min", {})
        trend  = stats.get("trend", {})
        streak = stats.get("streak", {})
        lines += [
            f"### {region}",
            f"- 최신값: {latest.get('value')} ({latest.get('date')})",
            f"- 고점: {peak.get('value')} ({peak.get('date')}) | 저점: {trough.get('value')} ({trough.get('date')})",
            f"- 평균: {stats.get('average')} | 고점 대비: {stats.get('from_peak_pct'):+.2f}%",
            (
                f"- 4주 변화: {stats.get('change_4w_pct'):+.2f}% | "
                f"52주 변화: {stats.get('change_52w_pct'):+.2f}% | "
                f"전체 변화: {stats.get('change_total_pct'):+.2f}%"
            ),
            f"- 추세(4주 기준): {trend.get('direction')} | 최근 흐름(직전 주 기준): {streak.get('direction')} {streak.get('weeks')}주 연속",
            "",
        ]

    lines += [
        "## 해석 규칙 (반드시 준수)",
        f"- 지수 기준시점: {base_date} = 100 (5개 지역 공통)",
        "- 지수는 지역별 가격 변화율 비교에만 사용. 지역 간 가격 수준(어디가 더 비싼지) 비교 금지.",
        "- 금액(원)으로 환산 금지.",
        "- 변화는 반드시 퍼센트(%)로 표현. 공식: (현재 ÷ 기준 − 1) × 100. 포인트 차이를 %로 말하지 않음.",
        "- 위 요약에 없는 수치는 지어내지 말고 '해당 데이터가 없습니다'라고 답하세요.",
    ]

    return "\n".join(lines)


# ── OpenAI 오류 → 한국어 502 변환 ────────────────────────────
def _raise_gpt_error(e: Exception) -> None:
    if isinstance(e, openai.AuthenticationError):
        msg = "GPT API 키가 유효하지 않습니다. OPENAI_API_KEY 환경변수를 확인하세요."
    elif isinstance(e, openai.NotFoundError):
        msg = f"GPT 모델을 찾을 수 없습니다: {OPENAI_MODEL}. OPENAI_MODEL 환경변수를 확인하세요."
    elif isinstance(e, openai.RateLimitError):
        msg = "GPT API 사용 한도를 초과했습니다. 잠시 후 다시 시도하세요."
    elif isinstance(e, openai.APIConnectionError):
        msg = "GPT API 서버에 연결할 수 없습니다. 네트워크 상태를 확인하세요."
    elif isinstance(e, openai.BadRequestError):
        msg = f"GPT 요청이 잘못되었습니다: {e}"
    else:
        msg = f"GPT API 오류가 발생했습니다: {e}"
    raise HTTPException(status_code=502, detail=msg)


# ── 메인 함수 ─────────────────────────────────────────────
def chat(request: ChatRequest) -> ChatResponse:
    # 1. 요약 캐시 읽기 (Firestore 1건, data 컬렉션 미접근)
    summary = get_summary()
    if not summary:
        raise HTTPException(
            status_code=503,
            detail="요약 데이터가 없습니다. build_summary를 먼저 실행하세요.",
        )

    # 2. 시스템 프롬프트 조립 + 길이 콘솔 출력
    system_prompt = _build_system_prompt(summary)
    print(f"[chat] 시스템 프롬프트 길이: {len(system_prompt)}자")

    # 3. 대화 가져오기 또는 새로 생성
    if request.conversation_id:
        conv_id = request.conversation_id.strip()
        detail = get_conversation(conv_id)  # 없으면 404
        is_new = False
    else:
        detail = create_conversation(ConversationCreate(title="새 대화"))
        conv_id = detail.id
        is_new = True

    # 4. 최근 MAX_HISTORY 개 메시지 → GPT 입력 형식 변환
    history = detail.messages[-MAX_HISTORY:]
    gpt_messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m.role, "content": m.content} for m in history],
        {"role": "user", "content": request.message},
    ]

    # 5. GPT 호출
    try:
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=gpt_messages,
            max_tokens=500,
            temperature=0.3,
        )
        answer = response.choices[0].message.content.strip()
    except openai.OpenAIError as e:
        _raise_gpt_error(e)

    # 6. 대화에 메시지 저장 (user → assistant 순서)
    add_message(conv_id, "user", request.message)
    add_message(conv_id, "assistant", answer)

    # 7. 새 대화면 첫 질문 앞 20자를 제목으로 자동 설정
    if is_new:
        title = request.message[:20] + ("..." if len(request.message) > 20 else "")
        db.collection("conversations").document(conv_id).update({"title": title})

    return ChatResponse(conversation_id=conv_id, answer=answer)
