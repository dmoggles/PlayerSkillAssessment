"""Whether a drill's variation ladder describes progress in each of its tags.

A 1v1 drill tagged for attacking and defending gets harder for the attacker as it escalates, not the
defender; suggestions only match a player's level to a rung through tags on the ladder.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drill_tags", sa.Column("on_ladder", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("drill_tags", "on_ladder")
