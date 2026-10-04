"""Coach notes on individual ratings and on the whole assessment.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ratings", sa.Column("note", sa.String(500), nullable=True))
    op.add_column("assessments", sa.Column("note", sa.String(1000), nullable=True))


def downgrade():
    op.drop_column("assessments", "note")
    op.drop_column("ratings", "note")
