from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message, MessageRole, Strategy
from app.schemas import ChatMessageIn, ChatMessageOut
from app.services.llm_service import chat_completion
from app.services.finalize_service import finalize_strategy
from app.services.strategy_extractor import extract_strategy, looks_like_final_strategy


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageOut)
async def send_message(payload: ChatMessageIn, db: Session = Depends(get_db)):
    # 1. Get or create conversation
    if payload.conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == payload.conversation_id
        ).first()
    else:
        # NOTE: for MVP, wire up real auth/user_id here. Placeholder user_id for now.
        conversation = Conversation(user_id=_get_or_create_dev_user(db), title=payload.content[:50])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # 2. Store user message
    user_msg = Message(conversation_id=conversation.id, role=MessageRole.user, content=payload.content)
    db.add(user_msg)
    db.commit()

    # 3. Build history for LLM
    history = [
        {"role": m.role.value, "content": m.content}
        for m in db.query(Message).filter(Message.conversation_id == conversation.id).order_by(Message.created_at)
    ]

    # 4. Call LLM
    reply = await chat_completion(history)

    # 5. Store assistant reply
    assistant_msg = Message(conversation_id=conversation.id, role=MessageRole.assistant, content=reply)
    db.add(assistant_msg)
    db.commit()

    # 6. If this reply looks like a finished strategy, run the constrained
    #    finalize call to get clean structured JSON instead of parsing prose.
    if looks_like_final_strategy(reply):
        finalized = await finalize_strategy(history + [{"role": "assistant", "content": reply}])

        if finalized:
            strategy = Strategy(
                conversation_id=conversation.id,
                name=finalized["name"],
                description=finalized["description"],
                generated_code=finalized["code"],
            )
            db.add(strategy)
            db.commit()
        else:
            # finalize_strategy failed (bad JSON, unsupported model, network issue) —
            # fall back to the regex extractor as a last resort rather than losing the strategy.
            extracted = extract_strategy(reply)
            if extracted:
                strategy = Strategy(
                    conversation_id=conversation.id,
                    name=extracted.name,
                    description=extracted.description,
                    generated_code=extracted.code,
                )
                db.add(strategy)
                db.commit()

    # 7. Return the response model (Properly aligned with the outer scope)
    # 7. Return the expected Pydantic schema format
    return {
        "reply": reply,
        "conversation_id": conversation.id
    }


def _get_or_create_dev_user(db: Session) -> str:
    """Temporary single dev user until auth is built. Replace in a later phase."""
    from app.models import User
    user = db.query(User).filter(User.email == "dev@local").first()
    if not user:
        user = User(email="dev@local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.id