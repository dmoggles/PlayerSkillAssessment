"""Videos coaches suggest for drills, reviewed by site admins before anyone sees them.

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drill_video_suggestions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("variation_id", sa.Integer, sa.ForeignKey("drill_variations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("host", sa.String(10), nullable=False),
        sa.Column("video_id", sa.String(40), nullable=False),
        sa.Column("start_seconds", sa.Integer, nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("channel", sa.String(120), nullable=False, server_default=""),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("suggested_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending", index=True),
        sa.Column("caption", sa.String(200), nullable=True),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(20), nullable=True),
        sa.Column("reject_note", sa.String(300), nullable=True),
        sa.Column("reports", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("drill_id", "host", "video_id"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'hidden')", name="ck_drill_video_suggestions_status"),
    )


def downgrade():
    op.drop_table("drill_video_suggestions")
