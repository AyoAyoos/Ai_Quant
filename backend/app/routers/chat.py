from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, Message, MessageRole, Strategy
from app.schemas import ChatMessageIn, ChatMessageOut
from app.services.llm_service import chat_completion
from app.services.finalize_service import finalize_strategy
from app.services.strategy_extractor import looks_like_final_strategy
from app.services.strategy_schema import StrategySpec
from app.services.strategy_generator import generate_backtrader_code


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post("", response_model=ChatMessageOut)
async def send_message(
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
):

    # =========================================================
    # 1. Get existing conversation or create a new one
    # =========================================================

    if payload.conversation_id:

        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == payload.conversation_id
            )
            .first()
        )

        if conversation is None:
            raise ValueError(
                "Conversation not found."
            )

    else:

        conversation = Conversation(
            user_id=_get_or_create_dev_user(db),
            title=payload.content[:50],
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # =========================================================
    # 2. Store user message
    # =========================================================

    user_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=payload.content,
    )

    db.add(user_msg)
    db.commit()

    # =========================================================
    # 3. Build conversation history
    # =========================================================

    history = [
        {
            "role": message.role.value,
            "content": message.content,
        }
        for message in (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conversation.id
            )
            .order_by(Message.created_at)
        )
    ]

    # =========================================================
    # 4. Call LLM
    # =========================================================

    reply = await chat_completion(history)

    # =========================================================
    # 5. Store assistant response
    # =========================================================

    assistant_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content=reply,
    )

    db.add(assistant_msg)
    db.commit()

    # =========================================================
    # 6. Default response values
    # =========================================================

    strategy_response = None

    # =========================================================
    # 7. Check whether strategy is finalized
    # =========================================================

    is_final = looks_like_final_strategy(reply)

    print()
    print("========== STRATEGY DEBUG ==========")
    print("looks_like_final_strategy:", is_final)

    # =========================================================
    # 8. Finalize strategy specification
    # =========================================================

    if is_final:

        print()
        print("Calling finalize_strategy...")

        finalized = await finalize_strategy(
            history
            + [
                {
                    "role": "assistant",
                    "content": reply,
                }
            ]
        )

        print()
        print("Finalized result:")
        print(finalized)

        # =====================================================
        # 9. Validate strategy specification
        # =====================================================

        if finalized:

            try:

                validated_strategy = (
                    StrategySpec.model_validate(
                        finalized
                    )
                )

                print()
                print(
                    "========== VALID STRATEGY SPECIFICATION =========="
                )

                print(validated_strategy)

                # =================================================
                # 10. Generate Backtrader code
                # =================================================

                generated_code = (
                    generate_backtrader_code(
                        validated_strategy
                    )
                )

                print()
                print(
                    "========== GENERATING BACKTRADER CODE =========="
                )

                print(generated_code)

                # =================================================
                # 11. Save strategy to database
                # =================================================

                strategy = Strategy(
                    conversation_id=conversation.id,
                    name=validated_strategy.name,
                    description=validated_strategy.description,
                    market=validated_strategy.market,
                    generated_code=generated_code,
                )

                db.add(strategy)
                db.commit()
                db.refresh(strategy)

                # =================================================
                # 12. Prepare strategy for frontend
                # =================================================

                strategy_response = {
                    "id": str(strategy.id),
                    "name": validated_strategy.name,
                    "description": (
                        validated_strategy.description
                    ),
                    "market": validated_strategy.market,
                    "timeframe": validated_strategy.timeframe,
                    "indicators": [
                        indicator.model_dump()
                        for indicator
                        in validated_strategy.indicators
                    ],
                    "entry_conditions": (
                        validated_strategy.entry_conditions
                    ),
                    "exit_conditions": (
                        validated_strategy.exit_conditions
                    ),
                    "risk_management": (
                        validated_strategy
                        .risk_management
                        .model_dump()
                    ),
                    "code": generated_code,
                }

                print()
                print(
                    "========== STRATEGY SAVED =========="
                )

                print(
                    "Strategy ID:",
                    strategy.id,
                )

                print(
                    "Strategy Name:",
                    strategy.name,
                )

                print(
                    "Market:",
                    strategy.market,
                )

            except Exception as validation_error:

                print()
                print(
                    "========== INVALID STRATEGY =========="
                )

                print(validation_error)

        else:

            print()
            print(
                "========== FINALIZATION FAILED =========="
            )

    print()
    print(
        "========== END STRATEGY DEBUG =========="
    )
    print()

    # =========================================================
    # 13. Return response to React
    # =========================================================

    return {
        "reply": reply,
        "conversation_id": str(
            conversation.id
        ),
        "strategy": strategy_response,
    }


def _get_or_create_dev_user(
    db: Session,
) -> str:

    """
    Temporary development user until
    authentication is implemented.
    """

    from app.models import User

    user = (
        db.query(User)
        .filter(
            User.email == "dev@local"
        )
        .first()
    )

    if not user:

        user = User(
            email="dev@local"
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    return user.id