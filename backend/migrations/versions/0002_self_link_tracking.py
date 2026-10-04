"""Track when self-assessment links are issued and first opened.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("self_links", sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("self_links", sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("self_links", "opened_at")
    op.drop_column("self_links", "issued_at")
