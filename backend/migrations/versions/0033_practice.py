"""Practice scenarios: a player's link, the practice coaches set them, and every attempt.

Revision ID: 0033
Revises: 0032
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "practice_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "practice_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("stage", sa.SmallInteger),
        sa.Column("scenario_id", sa.String(80)),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_on", sa.Date),
        sa.CheckConstraint("(scenario_id IS NULL) <> (stage IS NULL)", name="ck_practice_assignments_one_target"),
    )
    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scenario_id", sa.String(80), nullable=False),
        sa.Column("frame_id", sa.String(40), nullable=False),
        sa.Column("attempt_no", sa.SmallInteger, nullable=False),
        sa.Column("x", sa.Float),
        sa.Column("y", sa.Float),
        sa.Column("choice", sa.String(40)),
        sa.Column("points", sa.SmallInteger, nullable=False),
        sa.Column("zone_hit", sa.SmallInteger),
        sa.Column("failed_checks", JSONB, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade():
    op.drop_table("practice_attempts")
    op.drop_table("practice_assignments")
    op.drop_table("practice_links")
