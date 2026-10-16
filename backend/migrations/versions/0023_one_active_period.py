"""At most one active period per team, enforced by the database.

The API already keeps one active period per team; this stops a direct write (such as the demo seeder) from leaving
two. Where a team already has more than one, the most recently created stays active.

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE periods SET is_active = false
        WHERE is_active AND id NOT IN (
            SELECT DISTINCT ON (team_id) id FROM periods WHERE is_active ORDER BY team_id, created_at DESC, id DESC
        )
    """)
    op.create_index("uq_periods_one_active", "periods", ["team_id"], unique=True, postgresql_where=sa.text("is_active"))


def downgrade():
    op.drop_index("uq_periods_one_active", table_name="periods")
