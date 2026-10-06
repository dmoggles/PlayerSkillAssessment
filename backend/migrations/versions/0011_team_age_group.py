"""Team age group (the "U" number, e.g. 12 for U12), used to default the drill library's age filter.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teams", sa.Column("age_group", sa.SmallInteger))
    op.create_check_constraint("ck_teams_age_group", "teams", "age_group BETWEEN 5 AND 21")


def downgrade():
    op.drop_constraint("ck_teams_age_group", "teams", type_="check")
    op.drop_column("teams", "age_group")
