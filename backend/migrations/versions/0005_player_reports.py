"""Per-player, per-period report: the coach's message to the player.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("message", sa.String(1000)),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("player_id", "period_id"),
    )
    op.create_index("ix_player_reports_player_id", "player_reports", ["player_id"])
    op.create_index("ix_player_reports_period_id", "player_reports", ["period_id"])


def downgrade():
    op.drop_table("player_reports")
