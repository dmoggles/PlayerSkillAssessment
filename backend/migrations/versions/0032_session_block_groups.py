"""Level groups a coach makes for one exercise in a session.

Revision ID: 0032
Revises: 0031
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("session_blocks", sa.Column("groups", JSONB, nullable=True))


def downgrade():
    op.drop_column("session_blocks", "groups")
