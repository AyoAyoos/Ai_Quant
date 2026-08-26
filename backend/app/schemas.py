from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str


class ChatMessageIn(BaseModel):
    content: str
    conversation_id: str | None = None


class ChatMessageOut(BaseModel):
    reply: str
    conversation_id: str


