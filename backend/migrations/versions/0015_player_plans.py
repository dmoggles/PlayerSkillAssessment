"""Saved development plans, shown in the player report; shared plan links are folded into the report link.

Each shared plan becomes its player's saved plan for that period; its separate link stops working.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False, index=True),
        sa.Column("plan", JSONB, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("player_id", "period_id", name="uq_player_plans_player_period"),
    )
    op.execute("INSERT INTO player_plans (player_id, period_id, plan, created_by, created_at) "
               "SELECT player_id, period_id, plan, created_by, created_at FROM shared_plans")
    op.drop_table("shared_plans")


def downgrade():
    # Saved plans are not turned back into shared links; their tokens no longer exist.
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
    op.drop_table("player_plans")
