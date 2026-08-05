import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Float, Integer, JSON, Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class StrategyStatus(str, enum.Enum):
    draft = "draft"
    backtested = "backtested"
    approved = "approved"
    paper_trading = "paper_trading"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    title = Column(String, default="New conversation")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    strategies = relationship("Strategy", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    market = Column(String, default="NIFTY50")
    generated_code = Column(Text, nullable=False)  # AI-generated Python strategy code
    status = Column(Enum(StrategyStatus), default=StrategyStatus.draft)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="strategies")
    backtest_results = relationship("BacktestResult", back_populates="strategy", cascade="all, delete-orphan")


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id"), nullable=False)
    total_return_pct = Column(Float)
    win_rate_pct = Column(Float)
    max_drawdown_pct = Column(Float)
    num_trades = Column(Integer)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    raw_metrics = Column(JSON)  # full metrics dump for flexibility
    created_at = Column(DateTime, default=datetime.utcnow)

    strategy = relationship("Strategy", back_populates="backtest_results")
