"""Random practice situations as homework: how many, and on which format's pitch.

Revision ID: 0034
Revises: 0033
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("practice_assignments", sa.Column("random_count", sa.SmallInteger))
    op.add_column("practice_assignments", sa.Column("format", sa.String(10)))


def downgrade():
    op.drop_column("practice_assignments", "format")
    op.drop_column("practice_assignments", "random_count")
