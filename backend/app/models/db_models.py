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


class DeploymentStatus(str, enum.Enum):
    active = "active"
    stopped = "stopped"


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
    # Human reason for the last reject/stop transition; null otherwise.
    status_note = Column(Text)
    # Structured strategy specification (for strategy builder workflow)
    strategy_spec = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="strategies")
    backtest_results = relationship("BacktestResult", back_populates="strategy", cascade="all, delete-orphan")
    deployments = relationship("PaperDeployment", back_populates="strategy", cascade="all, delete-orphan")


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


class PaperDeployment(Base):
    """A paper-trading deployment record.

    This is the *gate*, not a live trading engine: a row exists only after
    the strategy passed approval (backtested, quality thresholds, guardrails)
    and was explicitly deployed. Stopping flips the strategy back to
    approved and closes the record — the history is preserved for audit.
    Only one active deployment per strategy is allowed.

    The virtual paper account lives on this row: ``cash`` is the starting
    capital snapshotted at deploy time, ``cash_balance`` is the current
    virtual cash (decreases on simulated BUY fills, increases on SELL fills),
    ``realized_pnl`` accumulates net P&L of closed simulated trades, and
    ``last_bar_date`` is the watermark of the last market bar the paper
    engine processed (``YYYY-MM-DD``). ``last_error`` keeps the latest
    execution error visible instead of failing silently.
    """

    __tablename__ = "paper_deployments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    strategy_id = Column(UUID(as_uuid=False), ForeignKey("strategies.id"), nullable=False)
    status = Column(Enum(DeploymentStatus), default=DeploymentStatus.active, nullable=False)
    # Config snapshot at deploy time (mirrors BacktestRequest knobs).
    cash = Column(Float, nullable=False)
    commission_pct = Column(Float, nullable=False)
    sizer_percents = Column(Float, nullable=False)
    deployed_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime)
    stop_reason = Column(Text)
    # Virtual paper account state (NULL cash_balance on pre-existing rows
    # reads as "untouched, equals starting cash").
    cash_balance = Column(Float)
    realized_pnl = Column(Float, default=0.0)
    last_bar_date = Column(String(10))
    last_error = Column(Text)

    strategy = relationship("Strategy", back_populates="deployments")
    positions = relationship(
        "PaperPosition", back_populates="deployment", cascade="all, delete-orphan"
    )
    orders = relationship(
        "PaperOrder", back_populates="deployment", cascade="all, delete-orphan"
    )
    trades = relationship(
        "PaperTrade", back_populates="deployment", cascade="all, delete-orphan"
    )


class PaperPosition(Base):
    """A currently open simulated long position.

    Long-only, one open position per deployment/symbol: the engine refuses
    to open a second position while one exists and never opens shorts.
    """

    __tablename__ = "paper_positions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False
    )
    symbol = Column(String, nullable=False, default="NIFTY50")
    quantity = Column(Integer, nullable=False)
    avg_price = Column(Float, nullable=False)
    entry_date = Column(String(10), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    deployment = relationship("PaperDeployment", back_populates="positions")


class PaperOrder(Base):
    """Every simulated order the paper engine placed, filled or rejected.

    Rejected orders are stored (status ``"rejected"`` with a reason in
    ``note``) so the UI can show them — they must never render as trades
    or chart markers.
    """

    __tablename__ = "paper_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False
    )
    symbol = Column(String, nullable=False, default="NIFTY50")
    side = Column(String(4), nullable=False)  # "BUY" | "SELL"
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)  # simulated fill price (bar close)
    bar_date = Column(String(10), nullable=False)  # market bar the fill belongs to
    status = Column(String(10), nullable=False, default="filled")  # filled | rejected
    commission = Column(Float, nullable=False, default=0.0)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    deployment = relationship("PaperDeployment", back_populates="orders")


class PaperTrade(Base):
    """A completed simulated round-trip (BUY fill paired with its SELL fill)."""

    __tablename__ = "paper_trades"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False
    )
    symbol = Column(String, nullable=False, default="NIFTY50")
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    entry_date = Column(String(10), nullable=False)
    exit_date = Column(String(10), nullable=False)
    pnl = Column(Float, nullable=False)  # gross, before commissions
    pnl_net = Column(Float, nullable=False)  # net of both fills' commissions
    entry_order_id = Column(String)
    exit_order_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    deployment = relationship("PaperDeployment", back_populates="trades")
