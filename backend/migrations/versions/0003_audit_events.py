"""Audit log for membership and destructive team changes.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, nullable=False),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_email", sa.String(255)),
        sa.Column("details", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_team_id", "audit_events", ["team_id"])


def downgrade():
    op.drop_index("ix_audit_events_team_id", table_name="audit_events")
    op.drop_table("audit_events")
