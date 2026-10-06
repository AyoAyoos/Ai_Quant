"""add strategy_spec column to strategies table

Revision ID: d4e5f6a7b8c9
Revises: c4d1e8f7a2b9
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c4d1e8f7a2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'strategies',
        sa.Column('strategy_spec', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('strategies', 'strategy_spec')