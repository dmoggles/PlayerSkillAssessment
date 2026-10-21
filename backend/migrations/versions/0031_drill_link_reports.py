"""Coaches reporting a drill's video or link as broken or inappropriate.

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drill_link_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("suggestion_id", sa.Integer, sa.ForeignKey("drill_video_suggestions.id", ondelete="CASCADE")),
        sa.Column("reason", sa.String(15), nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("reported_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("handled_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("reason IN ('dead', 'inappropriate', 'other')", name="ck_drill_link_reports_reason"),
        sa.CheckConstraint("status IN ('open', 'hidden', 'dismissed')", name="ck_drill_link_reports_status"),
    )
    op.create_index("ix_drill_link_reports_drill_url", "drill_link_reports", ["drill_id", "url"])
    op.create_index("ix_drill_link_reports_reported_by", "drill_link_reports", ["reported_by"])
    op.create_index("ix_drill_link_reports_status", "drill_link_reports", ["status"])


def downgrade():
    op.drop_table("drill_link_reports")
