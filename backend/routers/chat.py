"""
routers/chat.py — /api/chat 엔드포인트

POST /api/chat  질문을 받아 GPT 답변 + conversation_id 반환
"""

from fastapi import APIRouter

from schemas import ChatRequest, ChatResponse
from services import chat_service

_503 = {503: {"description": "Firestore 요청 한도 초과"}}

router = APIRouter(prefix="/api/chat", tags=["chat"], responses=_503)


@router.post("", response_model=ChatResponse, summary="AI 채팅")
def chat(request: ChatRequest) -> ChatResponse:
    """
    - conversation_id 없으면 새 대화를 자동 생성합니다.
    - 이전 대화를 이어가려면 이전 응답의 conversation_id를 그대로 전달하세요.
    """
    return chat_service.chat(request)
