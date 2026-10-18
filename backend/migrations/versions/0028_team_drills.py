"""Teams' own drills, written by their coaches, and their submissions to the shared library.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drills", sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_drills_team_id", "drills", ["team_id"])
    op.add_column("drills", sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("drills", sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True))
    op.create_table(
        "drill_submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("submitted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("library_slug", sa.String(80), nullable=True, unique=True),
        sa.Column("library_drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'published')", name="ck_drill_submissions_status"),
    )


def downgrade():
    op.drop_table("drill_submissions")
    op.drop_column("drills", "updated_by")
    op.drop_column("drills", "created_by")
    op.drop_index("ix_drills_team_id", "drills")
    op.drop_column("drills", "team_id")
