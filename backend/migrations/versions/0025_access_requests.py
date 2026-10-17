"""Requests for access from the public site, for site admins to invite or decline.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("club", sa.String(120), nullable=False),
        sa.Column("teams", sa.SmallInteger, nullable=True),
        sa.Column("message", sa.String(1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending", index=True),
        sa.Column("handled_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'invited', 'declined')", name="ck_access_requests_status"),
    )


def downgrade():
    op.drop_table("access_requests")
