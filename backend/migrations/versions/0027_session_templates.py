"""Session templates: a team's own breakdowns of a session into parts, and the breakdown each session was planned with.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("length_minutes", sa.SmallInteger, nullable=False),
        sa.Column("minutes", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "name", name="uq_session_templates_team_name"),
    )
    op.add_column("training_sessions", sa.Column("template_id", sa.Integer, sa.ForeignKey("session_templates.id", ondelete="SET NULL"), nullable=True))
    op.add_column("training_sessions", sa.Column("phase_minutes", JSONB, nullable=True))


def downgrade():
    op.drop_column("training_sessions", "phase_minutes")
    op.drop_column("training_sessions", "template_id")
    op.drop_table("session_templates")
