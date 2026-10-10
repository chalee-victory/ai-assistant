"""
conversation_service.py — conversations 컬렉션 CRUD

Firestore 문서 구조:
  conversations/{id}
    title       : str
    messages    : list[{role, content, created_at}]
    created_at  : str (ISO 8601)
    updated_at  : str (ISO 8601)

add_message()는 5단계 채팅 서비스에서 호출한다.
"""

from datetime import datetime, timezone

from fastapi import HTTPException

from firebase import db
from schemas import ConversationCreate, ConversationDetail, ConversationSummary, Message

COLLECTION = "conversations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_summary(doc_id: str, data: dict) -> ConversationSummary:
    return ConversationSummary(
        id=doc_id,
        title=data.get("title", "새 대화"),
        message_count=len(data.get("messages", [])),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def _to_detail(doc_id: str, data: dict) -> ConversationDetail:
    messages = [
        Message(
            role=m["role"],
            content=m["content"],
            created_at=m.get("created_at", ""),
        )
        for m in data.get("messages", [])
    ]
    return ConversationDetail(
        id=doc_id,
        title=data.get("title", "새 대화"),
        messages=messages,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


# ── 생성 ──────────────────────────────────────────────────
def create_conversation(payload: ConversationCreate) -> ConversationDetail:
    now = _now_iso()
    doc_data = {
        "title": payload.title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    # Firestore가 자동 생성한 ID 사용
    _, doc_ref = db.collection(COLLECTION).add(doc_data)
    return _to_detail(doc_ref.id, doc_data)


# ── 목록 조회 (updated_at 최신순, 최대 30건) ─────────────────
def list_conversations() -> list[ConversationSummary]:
    # Firestore 쿼리 단에서 정렬·상한 처리 → 읽기 건수 30건으로 고정
    docs = (
        db.collection(COLLECTION)
        .order_by("updated_at", direction="DESCENDING")
        .limit(30)
        .stream()
    )
    return [_to_summary(doc.id, doc.to_dict()) for doc in docs]


# ── 단건 조회 ─────────────────────────────────────────────
def get_conversation(conv_id: str) -> ConversationDetail:
    doc = db.collection(COLLECTION).document(conv_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"대화를 찾을 수 없습니다: {conv_id}")
    return _to_detail(doc.id, doc.to_dict())


# ── 삭제 ──────────────────────────────────────────────────
def delete_conversation(conv_id: str) -> None:
    doc_ref = db.collection(COLLECTION).document(conv_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail=f"대화를 찾을 수 없습니다: {conv_id}")
    doc_ref.delete()


# ── 메시지 추가 (5단계 채팅 서비스에서 호출) ──────────────────
def add_message(conv_id: str, role: str, content: str) -> None:
    """messages 배열에 메시지를 덧붙이고 updated_at을 갱신한다.

    존재하지 않는 conv_id이면 404를 발생시킨다.
    """
    doc_ref = db.collection(COLLECTION).document(conv_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"대화를 찾을 수 없습니다: {conv_id}")

    now = _now_iso()
    current_messages: list = doc.to_dict().get("messages", [])
    current_messages.append({"role": role, "content": content, "created_at": now})

    doc_ref.update({
        "messages": current_messages,
        "updated_at": now,
    })
