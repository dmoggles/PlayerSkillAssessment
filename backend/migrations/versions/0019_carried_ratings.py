"""Carried ratings: a period can start from the previous period's coach ratings. Each copied score is marked as
carried until the coach changes or confirms it, so copied values never pass for fresh judgments.

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ratings", sa.Column("carried", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("ratings", "carried")
