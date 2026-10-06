"""Shared development plans: a frozen copy of a generated plan behind an expiring, no-login link.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False, index=True),
        sa.Column("plan", JSONB, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("player_id", "period_id", name="uq_shared_plans_player_period"),
    )


def downgrade():
    op.drop_table("shared_plans")
