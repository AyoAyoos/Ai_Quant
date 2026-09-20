from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    conversation_id: str | None = None
    content: str


class ChatMessageOut(BaseModel):
    conversation_id: str
    reply: str
    strategy_id: str | None = None
    strategy_name: str | None = None