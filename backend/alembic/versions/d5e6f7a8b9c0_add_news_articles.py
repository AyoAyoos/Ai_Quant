"""add news articles

Revision ID: d5e6f7a8b9c0
Revises: 4f6a7b8c9d10
Create Date: 2026-11-13 00:00:00.000000

Stores the Market News Hub feed.  Only headline, a short source snippet, the
source link and classification metadata are persisted; full article text and
publisher images are never copied into this table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "4f6a7b8c9d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The test harness calls ``Base.metadata.create_all``, which can create this
    # table on a shared dev database before Alembic sees the revision.  Reconcile
    # both cases without rewriting migration history.
    if sa.inspect(op.get_bind()).has_table("news_articles"):
        return

    op.create_table(
        "news_articles",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_domain", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_key", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("region", sa.String(length=20), nullable=False, server_default="global"),
        sa.Column("category", sa.String(length=30), nullable=False, server_default="markets"),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("tickers_text", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("sentiment", sa.String(length=10), nullable=False, server_default="neutral"),
        sa.Column("sentiment_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sentiment_method", sa.String(length=20), nullable=False, server_default="lexicon"),
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default="aggregator"),
        sa.Column("content_type", sa.String(length=20), nullable=False, server_default="report"),
        sa.Column("credibility_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("impact_level", sa.String(length=10), nullable=False, server_default="low"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="unknown"),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_news_articles_external_id"), "news_articles", ["external_id"], unique=True)
    op.create_index(op.f("ix_news_articles_published_at"), "news_articles", ["published_at"], unique=False)
    op.create_index(op.f("ix_news_articles_fetched_at"), "news_articles", ["fetched_at"], unique=False)
    op.create_index(op.f("ix_news_articles_region"), "news_articles", ["region"], unique=False)
    op.create_index(op.f("ix_news_articles_category"), "news_articles", ["category"], unique=False)
    op.create_index(op.f("ix_news_articles_sentiment"), "news_articles", ["sentiment"], unique=False)
    op.create_index(op.f("ix_news_articles_source_type"), "news_articles", ["source_type"], unique=False)
    op.create_index(op.f("ix_news_articles_credibility_level"), "news_articles", ["credibility_level"], unique=False)
    op.create_index(op.f("ix_news_articles_impact_level"), "news_articles", ["impact_level"], unique=False)


def downgrade() -> None:
    for index in (
        "ix_news_articles_impact_level",
        "ix_news_articles_credibility_level",
        "ix_news_articles_source_type",
        "ix_news_articles_sentiment",
        "ix_news_articles_category",
        "ix_news_articles_region",
        "ix_news_articles_fetched_at",
        "ix_news_articles_published_at",
        "ix_news_articles_external_id",
    ):
        op.drop_index(op.f(index), table_name="news_articles")
    op.drop_table("news_articles")
