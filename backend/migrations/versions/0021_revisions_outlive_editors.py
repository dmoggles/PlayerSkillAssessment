"""Let assessment revisions outlive the coach who saved them, so coaches can delete their accounts.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("assessment_revisions", "editor_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("assessment_revisions", "editor_id", existing_type=sa.Integer(), nullable=False)
