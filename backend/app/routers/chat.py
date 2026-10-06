from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from app.database import get_db
from app.ids import canonical_uuid_or_404
from app.models import Conversation, Message, MessageRole, Strategy
from app.schemas import ChatMessageIn, ChatMessageOut
from app.services.llm_service import chat_completion
from app.services.finalize_service import finalize_strategy, finalize_strategy_spec
from app.services.strategy_extractor import (
    clean_reply_for_display,
    extract_strategy,
    looks_like_final_strategy,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageOut)
async def send_message(payload: ChatMessageIn, db: Session = Depends(get_db)):
    # 1. Get or create conversation
    if payload.conversation_id is not None:
        # Validate before querying: a malformed id cast to `::UUID` by Postgres
        # would raise a DataError here instead of the 404 below.
        conversation_id = canonical_uuid_or_404(
            payload.conversation_id, "Conversation not found"
        )
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        # NOTE: NO real auth yet — single dev user. Replace when auth lands.
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
        for m in db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ]

    # 4. Call LLM
    reply = await chat_completion(history)

    # 5. Store assistant reply
    assistant_msg = Message(conversation_id=conversation.id, role=MessageRole.assistant, content=reply)
    db.add(assistant_msg)
    db.commit()

    strategy_id: str | None = None
    strategy_name: str | None = None
    strategy_description: str | None = None
    display_reply = reply

    # 6. If this reply looks like a finished strategy, run the constrained
    #    finalize call to extract clean structured JSON.
    if looks_like_final_strategy(reply):
        finalized_spec = await finalize_strategy_spec(history + [{"role": "assistant", "content": reply}])

        if finalized_spec:
            # Generate backward-compatible Backtrader code for legacy compatibility
            from app.services.finalize_service import finalize_strategy
            # We need to call the old finalize_strategy to get the legacy format
            # but we already have the StrategySpec. Let's generate the legacy format.
            # We'll create a mock conversation history for finalize_strategy
            # Actually, let's just use the legacy finalize_strategy which calls finalize_strategy_spec internally
            # But we already have the StrategySpec. Let's generate the legacy format ourselves.
            from app.services.finalize_service import finalize_strategy
            # We'll call finalize_strategy with a mock conversation to get the legacy format
            # But we already have the StrategySpec. Let's generate the legacy format directly.
            # For simplicity, we'll call finalize_strategy with a mock conversation
            # Actually, we can just generate the legacy format from the StrategySpec
            from app.services.finalize_service import finalize_strategy
            # We'll create a minimal conversation history that would produce this StrategySpec
            # But that's complex. Instead, let's generate the legacy code directly.
            # For now, we'll store the StrategySpec and generate the legacy code for backward compatibility.
            
            # Generate legacy Backtrader code from StrategySpec
            indicators_code = []
            for ind in finalized_spec.get("indicators", []):
                indicators_code.append(f"        self.{ind['name']} = bt.indicators.{ind['type'].upper()}(self.data.close, period={ind['period']})")
            
            entry_desc = f"{finalized_spec['entry']['left']} {finalized_spec['entry']['operator']} "
            if finalized_spec['entry'].get('right_indicator'):
                entry_desc += finalized_spec['entry']['right_indicator']
            else:
                entry_desc += str(finalized_spec['entry']['right_value'])
            
            exit_desc = f"{finalized_spec['exit']['left']} {finalized_spec['exit']['operator']} "
            if finalized_spec['exit'].get('right_indicator'):
                exit_desc += finalized_spec['exit']['right_indicator']
            else:
                exit_desc += str(finalized_spec['exit']['right_value'])
            
            params_list = [f'{ind["name"]}_period' for ind in finalized_spec.get("indicators", [])]
            params_tuple = "(" + ", ".join(params_list) + ",)" if params_list else "()"
            
            code_lines = [
                "import backtrader as bt",
                "",
                "class GeneratedStrategy(bt.Strategy):",
                f"    params = {params_tuple}",
                "    def __init__(self):",
            ] + [f"        {line}" for line in indicators_code] + [
                "    def next(self):",
                f"        if not self.position and {entry_desc}:",
                "            self.buy()",
                f"        elif self.position and {exit_desc}:",
                "            self.sell()",
            ]
            legacy_code = "\n".join(code_lines)
            
            strategy = Strategy(
                conversation_id=conversation.id,
                name=finalized_spec.get("name", "Untitled Strategy"),
                description=f"Entry: {entry_desc}. Exit: {exit_desc}.",
                generated_code=legacy_code,
                strategy_spec=finalized_spec,
            )
            db.add(strategy)
            db.commit()
            db.refresh(strategy)
            strategy_id = strategy.id
            strategy_name = strategy.name
            strategy_description = strategy.description
        else:
            # Finalize failed (bad JSON / LLM error) — fall back to the regex
            # extractor so the strategy is still persisted rather than lost.
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
                db.refresh(strategy)
                strategy_id = strategy.id
                strategy_name = strategy.name
                strategy_description = strategy.description

        if strategy_id and strategy_name:
            # The stored message keeps the raw reply (finalize + LLM memory
            # need it); the client sees a cleaned version instead.
            display_reply = clean_reply_for_display(reply, strategy_name)

    # 7. Return the response model (thread the strategy back to the client)
    return {
        "reply": display_reply,
        "conversation_id": conversation.id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "strategy_description": strategy_description,
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
