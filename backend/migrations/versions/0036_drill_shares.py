"""Read-only links to a drill, for coaches who aren't on the platform.

Revision ID: 0036
Revises: 0035
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drill_shares",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("drill_shares")
