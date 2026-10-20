"""Two suggested teams for a session's full squad game.

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("training_sessions", sa.Column("match_teams", JSONB, nullable=True))


def downgrade():
    op.drop_column("training_sessions", "match_teams")
