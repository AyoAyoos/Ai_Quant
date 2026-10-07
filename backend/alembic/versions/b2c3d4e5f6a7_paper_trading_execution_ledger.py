"""paper trading execution ledger

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-07 00:00:00.000000

Adds the virtual-account state on paper_deployments plus the three
paper-trading ledger tables (positions, orders, trades). Additive only:
existing deployment rows keep their starting-capital snapshot and read
back as untouched accounts (cash_balance NULL == cash).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
# Runs after c7d8e9f0a1b2 so databases carrying the retired phantom paper
# schema (d4e5f6a7b8c9) have those tables renamed aside before these
# CREATE TABLEs run. Fresh databases see c7... as a no-op.
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    try:
        return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def _has_table(name: str) -> bool:
    try:
        return sa.inspect(op.get_bind()).has_table(name)
    except Exception:
        return False


def upgrade() -> None:
    # add_column has no IF NOT EXISTS: the retired phantom schema already
    # contributed realized_pnl / last_bar_date / last_error to
    # paper_deployments, so only genuinely missing columns are added.
    existing = _existing_columns("paper_deployments")
    if "cash_balance" not in existing:
        op.add_column('paper_deployments', sa.Column('cash_balance', sa.Float(), nullable=True))
    if "realized_pnl" not in existing:
        op.add_column('paper_deployments', sa.Column('realized_pnl', sa.Float(), nullable=True))
    if "last_bar_date" not in existing:
        op.add_column('paper_deployments', sa.Column('last_bar_date', sa.String(length=10), nullable=True))
    if "last_error" not in existing:
        op.add_column('paper_deployments', sa.Column('last_error', sa.Text(), nullable=True))

    if not _has_table("paper_positions"):
        op.create_table('paper_positions',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('deployment_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('symbol', sa.String(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('avg_price', sa.Float(), nullable=False),
    sa.Column('entry_date', sa.String(length=10), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['deployment_id'], ['paper_deployments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    if not _has_table("paper_orders"):
        op.create_table('paper_orders',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('deployment_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('symbol', sa.String(), nullable=False),
    sa.Column('side', sa.String(length=4), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('bar_date', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('commission', sa.Float(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['deployment_id'], ['paper_deployments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    if not _has_table("paper_trades"):
        op.create_table('paper_trades',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('deployment_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('symbol', sa.String(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('exit_price', sa.Float(), nullable=False),
    sa.Column('entry_date', sa.String(length=10), nullable=False),
    sa.Column('exit_date', sa.String(length=10), nullable=False),
    sa.Column('pnl', sa.Float(), nullable=False),
    sa.Column('pnl_net', sa.Float(), nullable=False),
    sa.Column('entry_order_id', sa.String(), nullable=True),
    sa.Column('exit_order_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['deployment_id'], ['paper_deployments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('paper_trades')
    op.drop_table('paper_orders')
    op.drop_table('paper_positions')
    op.drop_column('paper_deployments', 'last_error')
    op.drop_column('paper_deployments', 'last_bar_date')
    op.drop_column('paper_deployments', 'realized_pnl')
    op.drop_column('paper_deployments', 'cash_balance')
