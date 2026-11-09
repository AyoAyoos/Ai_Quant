"""add updated_at to conversations

Revision ID: 4f6a7b8c9d10
Revises: 0fcc1c1e1e03
Create Date: 2026-11-10 01:45:00.000000

The Conversation model has tracked ``updated_at`` since the project model was
introduced, but the preceding migration never added the column.  Existing
databases therefore failed on the first conversation query with
``column "updated_at" of relation "conversations" does not exist``.

The column is intentionally nullable to match the model.  A temporary server
default backfills existing rows; the default is then removed so the schema
matches the SQLAlchemy definition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4f6a7b8c9d10"
down_revision: Union[str, None] = "0fcc1c1e1e03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _conversation_columns() -> dict:
    """Return the current conversations columns keyed by name.

    Some local databases already have ``updated_at`` because it was added by
    an older ``create_all``/manual schema update before this migration existed.
    CI starts from an empty database, so the add-column path is still tested
    there.  Reconcile both cases without rewriting migration history.
    """
    inspector = sa.inspect(op.get_bind())
    return {column["name"]: column for column in inspector.get_columns("conversations")}


def upgrade() -> None:
    columns = _conversation_columns()
    existing = columns.get("updated_at")

    if existing is None:
        op.add_column(
            "conversations",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        # The temporary default gives every existing row a valid value.  Where
        # possible, use the conversation's creation time as its first update
        # time rather than the migration timestamp.
        op.execute(
            "UPDATE conversations "
            "SET updated_at = created_at "
            "WHERE created_at IS NOT NULL"
        )
    else:
        if not existing["nullable"]:
            # The model defines a nullable column.  Existing drifted databases
            # may have been created with NOT NULL; relax it without touching
            # any data.
            op.alter_column("conversations", "updated_at", nullable=True)

        # Only fill genuinely missing values.  A drifted database may already
        # contain meaningful updated_at history that must be preserved.
        op.execute(
            "UPDATE conversations "
            "SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
            "WHERE updated_at IS NULL"
        )

    # The model does not define a server default; keep the schema aligned.
    op.alter_column("conversations", "updated_at", server_default=None)


def downgrade() -> None:
    if "updated_at" in _conversation_columns():
        op.drop_column("conversations", "updated_at")
