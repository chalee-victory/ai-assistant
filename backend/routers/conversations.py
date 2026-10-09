"""
routers/conversations.py — /api/conversations 엔드포인트

POST   /api/conversations          대화 생성
GET    /api/conversations          대화 목록 (updated_at 최신순, messages 제외)
GET    /api/conversations/{id}     대화 상세 (messages 전체 포함)
DELETE /api/conversations/{id}     대화 삭제 → 204
"""

from fastapi import APIRouter

from schemas import ConversationCreate, ConversationDetail, ConversationSummary
from services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationDetail, status_code=201, summary="대화 생성")
def create_conversation(payload: ConversationCreate) -> ConversationDetail:
    return conversation_service.create_conversation(payload)


@router.get("", response_model=list[ConversationSummary], summary="대화 목록 조회")
def list_conversations() -> list[ConversationSummary]:
    return conversation_service.list_conversations()


@router.get("/{conv_id}", response_model=ConversationDetail, summary="대화 상세 조회")
def get_conversation(conv_id: str) -> ConversationDetail:
    return conversation_service.get_conversation(conv_id.strip())


@router.delete("/{conv_id}", status_code=204, summary="대화 삭제")
def delete_conversation(conv_id: str) -> None:
    conversation_service.delete_conversation(conv_id.strip())
