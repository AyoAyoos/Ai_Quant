"""retire phantom paper-trading schema d4e5f6a7b8c9

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-07 00:00:00.000000

A previous (interrupted) paper-trading attempt stamped some databases with
revision ``d4e5f6a7b8c9`` and created a DIFFERENT paper schema there
(``paper_deployments.balance``, ``paper_positions.avg_entry_price`` /
``last_price`` / ``opened_at``, ``paper_orders.order_type`` / ``reason`` /
``fill_price``, ``paper_trades.direction`` / ``gross_pnl`` / ``net_pnl`` /
``won``, TIMESTAMP dates). That revision does not exist in this repo, so
``alembic upgrade head`` — including the backend's startup migration —
fails with "Can't locate revision identified by 'd4e5f6a7b8c9'" and the
container restart-loops.

This migration renames those legacy objects aside (NON-DESTRUCTIVE: every
rename is reversible in downgrade()) so the real paper-ledger migration
``b2c3d4e5f6a7`` can create the current schema under the canonical table
names. Databases that never saw the phantom revision are untouched: every
step is guarded by an existence check, so fresh installs behave exactly as
if this migration were a no-op.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_TAG = "legacy_d4e5f6a7b8c9"

_LEGACY_TABLES = ("paper_positions", "paper_orders", "paper_trades")


def _has_table(insp, name: str) -> bool:
    try:
        return insp.has_table(name)
    except Exception:
        return False


def _columns(insp, table: str) -> set[str]:
    try:
        return {col["name"] for col in insp.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for table in _LEGACY_TABLES:
        # Only retire tables that actually carry the phantom shape (legacy
        # marker columns). A current-shape table of the same name must never
        # be renamed: that would mean b2 already ran, which the chain
        # ordering (c7... before b2...) already rules out.
        cols = _columns(insp, table)
        if table == "paper_positions" and "avg_entry_price" not in cols:
            continue
        if table == "paper_orders" and "order_type" not in cols:
            continue
        if table == "paper_trades" and "gross_pnl" not in cols:
            continue
        if not _has_table(insp, table):
            continue
        op.rename_table(table, f"{LEGACY_TAG}_{table}")

    if _has_table(insp, "paper_deployments"):
        cols = _columns(insp, "paper_deployments")
        if "balance" in cols and "cash_balance" not in cols:
            op.alter_column(
                "paper_deployments", "balance",
                new_column_name=f"balance_{LEGACY_TAG}",
            )
            # The phantom column was NOT NULL without a default, which would
            # reject every new paper_deployments INSERT (the current code
            # never writes this archived column). Keep the data, drop the
            # blocking constraint.
            op.alter_column(
                "paper_deployments", f"balance_{LEGACY_TAG}",
                nullable=True,
            )
        # The phantom schema declared last_bar_date as TIMESTAMP; the
        # current model watermarks with 'YYYY-MM-DD' strings. Convert the
        # (empty in practice) column in place — no rows are touched beyond
        # reformatting, nothing is dropped.
        if "last_bar_date" in cols and bind.dialect.name == "postgresql":
            col_type = next(
                (c["type"] for c in insp.get_columns("paper_deployments")
                 if c["name"] == "last_bar_date"),
                None,
            )
            if col_type is not None and not isinstance(col_type, sa.String):
                op.execute(
                    "ALTER TABLE paper_deployments ALTER COLUMN last_bar_date "
                    "TYPE VARCHAR(10) USING to_char(last_bar_date, 'YYYY-MM-DD')"
                )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _has_table(insp, "paper_deployments"):
        cols = _columns(insp, "paper_deployments")
        if f"balance_{LEGACY_TAG}" in cols and "balance" not in cols:
            op.alter_column(
                "paper_deployments", f"balance_{LEGACY_TAG}",
                nullable=False,
            )
            op.alter_column(
                "paper_deployments", f"balance_{LEGACY_TAG}",
                new_column_name="balance",
            )
        if "last_bar_date" in cols and bind.dialect.name == "postgresql":
            col_type = next(
                (c["type"] for c in insp.get_columns("paper_deployments")
                 if c["name"] == "last_bar_date"),
                None,
            )
            if col_type is not None and isinstance(col_type, sa.String):
                op.execute(
                    "ALTER TABLE paper_deployments ALTER COLUMN last_bar_date "
                    "TYPE TIMESTAMP USING last_bar_date::timestamp"
                )

    for table in _LEGACY_TABLES:
        archived = f"{LEGACY_TAG}_{table}"
        if _has_table(insp, archived) and not _has_table(insp, table):
            op.rename_table(archived, table)
