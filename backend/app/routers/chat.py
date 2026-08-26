from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message, MessageRole, Strategy, User
from app.schemas import ChatMessageIn, ChatMessageOut
from app.services.llm_service import chat_completion
from app.services.finalize_service import finalize_strategy
from app.services.strategy_extractor import (
    extract_strategy,
    looks_like_final_strategy,
)


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageOut)
async def send_message(
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get existing conversation or create a new one
    # ---------------------------------------------------------
    if payload.conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == payload.conversation_id)
            .first()
        )

        if not conversation:
            # If the supplied conversation ID doesn't exist,
            # return a clear error instead of crashing later.
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    else:
        # Temporary development user until real authentication
        # is connected to the chat endpoint.
        user_id = _get_or_create_dev_user(db)

        conversation = Conversation(
            user_id=user_id,
            title=payload.content[:50],
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # ---------------------------------------------------------
    # 2. Store the user's message
    # ---------------------------------------------------------
    user_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=payload.content,
    )

    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # ---------------------------------------------------------
    # 3. Build conversation history for the LLM
    # ---------------------------------------------------------
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
        .all()
    )

    history = [
        {
            "role": message.role.value,
            "content": message.content,
        }
        for message in messages
    ]

    # ---------------------------------------------------------
    # 4. Call the LLM
    # ---------------------------------------------------------
    reply = await chat_completion(history)

    # ---------------------------------------------------------
    # 5. Store the assistant's reply
    # ---------------------------------------------------------
    assistant_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content=reply,
    )

    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    # ---------------------------------------------------------
    # 6. Detect and save a finalized trading strategy
    # ---------------------------------------------------------
    if looks_like_final_strategy(reply):

        # Add the assistant response to the history used
        # by the finalization service.
        finalization_history = history + [
            {
                "role": "assistant",
                "content": reply,
            }
        ]

        finalized = await finalize_strategy(finalization_history)

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
            # Fallback if structured finalization fails.
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

    # ---------------------------------------------------------
    # 7. Return response to the frontend
    # ---------------------------------------------------------
    return ChatMessageOut(
        reply=reply,
        conversation_id=str(conversation.id),
    )


def _get_or_create_dev_user(db: Session) -> str:
    """
    Temporary development user.

    This will later be replaced by the authenticated user's ID.
    """

    user = (
        db.query(User)
        .filter(User.email == "dev@local")
        .first()
    )

    if not user:
        user = User(email="dev@local")

        db.add(user)
        db.commit()
        db.refresh(user)

    return str(user.id)