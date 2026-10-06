"""How to run a home drill indoors, shown as its own section on the drill page.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drills", sa.Column("indoors", sa.Text))


def downgrade():
    op.drop_column("drills", "indoors")
