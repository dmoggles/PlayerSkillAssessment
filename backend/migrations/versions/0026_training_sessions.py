"""Team training sessions: blocks of drills on a date, and who is expected and who came.

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False, index=True),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("start_time", sa.String(5), nullable=True),
        sa.Column("length_minutes", sa.SmallInteger, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("focus_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("versions", sa.String(6), nullable=False, server_default="single"),
        sa.Column("groups", JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.String(2000), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("versions IN ('single', 'groups')", name="ck_training_sessions_versions"),
    )
    op.create_table(
        "session_blocks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("minutes", sa.SmallInteger, nullable=False),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id"), nullable=True),
        sa.Column("title", sa.String(160), nullable=False, server_default=""),
        sa.Column("variation_id", sa.Integer, sa.ForeignKey("drill_variations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_variations", JSONB, nullable=False, server_default="{}"),
        sa.Column("reasons", JSONB, nullable=False, server_default="[]"),
        sa.Column("chosen_by", sa.String(8), nullable=False, server_default="planner"),
        sa.Column("notes", sa.String(1000), nullable=False, server_default=""),
    )
    op.create_table(
        "session_attendance",
        sa.Column("session_id", sa.Integer, sa.ForeignKey("training_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), primary_key=True, index=True),
        sa.Column("expected", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("attended", sa.Boolean, nullable=True),
    )


def downgrade():
    op.drop_table("session_attendance")
    op.drop_table("session_blocks")
    op.drop_table("training_sessions")
