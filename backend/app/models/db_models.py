import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Enum, Float, ForeignKey, Index,
    Integer, JSON, String, Text, UniqueConstraint,
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
    strategy_spec = Column(JSON)  # Validated engine-neutral StrategySpec v1
    status = Column(Enum(StrategyStatus), default=StrategyStatus.draft)
    # Human reason for the last reject/stop transition; null otherwise.
    status_note = Column(Text)
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
    """A paper-trading deployment record — the root of one virtual account.

    This is the *gate* plus the account it owns. A row exists only after the
    strategy passed approval (backtested, quality thresholds, guardrails) and
    was explicitly deployed. Stopping flips the strategy back to approved and
    closes the record — the history is preserved for audit. Only one active
    deployment per strategy is allowed.

    ``cash`` is the *immutable config snapshot* of the capital the deploy
    request asked for and never changes afterwards; it is the account's
    ``initial_balance``. All mutable paper state lives in separate columns so
    the configured value stays auditable:

    * ``balance``      — cash available right now; moves with every simulated fill
    * ``realized_pnl`` — profit/loss banked by closed paper trades
    * ``last_bar_date`` — watermark of the last market bar accounted for (drives
      the future tick loop's duplicate protection)
    * ``last_error``   — why the last simulated run failed, null when healthy
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
    # Mutable virtual-account state. Seeded from `cash` when the account opens.
    balance = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    last_bar_date = Column(DateTime)
    last_error = Column(Text)

    strategy = relationship("Strategy", back_populates="deployments")
    positions = relationship(
        "PaperPosition",
        back_populates="deployment",
        cascade="all, delete-orphan",
    )
    trades = relationship(
        "PaperTrade",
        back_populates="deployment",
        cascade="all, delete-orphan",
    )
    orders = relationship(
        "PaperOrder",
        back_populates="deployment",
        cascade="all, delete-orphan",
    )


class PaperPosition(Base):
    """An OPEN paper position held by a deployment's virtual account.

    One row per ``(deployment_id, symbol)`` — enforced by a unique constraint,
    so a second open position for the same instrument cannot be created by
    accident. Sizing a position further means updating the quantity and the
    weighted-average entry price on this row, not inserting another.

    ``quantity`` is a positive whole number of units: the MVP is a single,
    long-only book (``PercentSizer`` sizes one position at a time and there is
    no leverage, no shorting and no multi-instrument hedging). ``last_price``
    is the most recent mark and is null until the position is first marked; the
    account snapshot marks an unmarked leg at its entry price.
    """

    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("deployment_id", "symbol", name="uq_paper_positions_deployment_symbol"),
        CheckConstraint("quantity > 0", name="ck_paper_positions_quantity_positive"),
        CheckConstraint("avg_entry_price >= 0", name="ck_paper_positions_entry_price_non_negative"),
        CheckConstraint("last_price IS NULL OR last_price >= 0", name="ck_paper_positions_last_price_non_negative"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False, index=True
    )
    symbol = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    last_price = Column(Float)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    deployment = relationship("PaperDeployment", back_populates="positions")


class PaperTrade(Base):
    """A CLOSED paper trade — one simulated entry and its matching exit.

    Unlike the transient backtest trade dicts (``ClosedTradeCollector`` in
    ``strategy_runner``) these rows are the durable ledger of what paper
    trading actually did. ``gross_pnl`` is price movement only; ``commission``
    is the fee actually charged on both legs; ``net_pnl`` is what the virtual
    cash was really credited with. ``direction`` reuses the backtest's existing
    vocabulary (``long``/``short``) so the same strategy code produces
    consistent language in both places.
    """

    __tablename__ = "paper_trades"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('long', 'short')", name="ck_paper_trades_direction"
        ),
        CheckConstraint("quantity > 0", name="ck_paper_trades_quantity_positive"),
        CheckConstraint("entry_price >= 0 AND exit_price >= 0", name="ck_paper_trades_prices_non_negative"),
        # Keeps the stored ledger self-consistent. A tolerance rather than `=`
        # so ordinary float64 rounding of the two legs can never trip it.
        CheckConstraint(
            "abs(net_pnl - (gross_pnl - commission)) < 0.000001",
            name="ck_paper_trades_net_matches_gross",
        ),
        # Ledgers are always read newest-first for one account.
        Index("ix_paper_trades_deployment_exit", "deployment_id", "exit_date"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False, index=True
    )
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    entry_date = Column(DateTime, nullable=False)
    exit_date = Column(DateTime, nullable=False)
    gross_pnl = Column(Float, nullable=False)
    commission = Column(Float, nullable=False, default=0.0)
    net_pnl = Column(Float, nullable=False)
    won = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    deployment = relationship("PaperDeployment", back_populates="trades")


class PaperOrder(Base):
    """Audit record of a simulated order submitted to the virtual account.

    Rows exist so the paper phase can *demonstrate* that BUY/SELL orders are
    actually generated and processed rather than silently mutating the
    balance: every submitted order is written with the reason it was created
    (e.g. ``strategy_signal``), and ``status`` records whether it filled or
    was refused (``insufficient_cash``, ``no_open_position``, …). Filled
    orders carry ``fill_price`` and ``filled_at``.

    Stored as constrained strings rather than a Postgres ENUM to keep the
    migration free of custom types, matching the plain ``direction``/``side``
    vocabulary the backtest runner already emits.
    """

    __tablename__ = "paper_orders"
    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')", name="ck_paper_orders_side"),
        CheckConstraint(
            "order_type IN ('market', 'limit', 'stop')", name="ck_paper_orders_order_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'filled', 'rejected', 'cancelled')",
            name="ck_paper_orders_status",
        ),
        CheckConstraint("quantity > 0", name="ck_paper_orders_quantity_positive"),
        Index("ix_paper_orders_deployment_created", "deployment_id", "created_at"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    deployment_id = Column(
        UUID(as_uuid=False), ForeignKey("paper_deployments.id"), nullable=False, index=True
    )
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    order_type = Column(String, nullable=False, default="market")
    status = Column(String, nullable=False, default="pending")
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    filled_at = Column(DateTime)
    fill_price = Column(Float)

    deployment = relationship("PaperDeployment", back_populates="orders")
