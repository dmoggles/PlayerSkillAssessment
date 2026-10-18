"""A team's own drill can be its version of a library drill, which it then replaces for that team.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drills", sa.Column("shadows_drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="SET NULL"), nullable=True))
    # One version in use per team and library drill.
    op.create_index("uq_drills_team_shadow", "drills", ["team_id", "shadows_drill_id"], unique=True,
                    postgresql_where=sa.text("status = 'published' AND shadows_drill_id IS NOT NULL"))
    # Submissions already published: the team's drill becomes its version of the library drill (one per library drill).
    op.execute("""
        UPDATE drills AS own SET shadows_drill_id = pick.library_drill_id
        FROM (SELECT DISTINCT ON (s.team_id, s.library_drill_id) s.drill_id, s.library_drill_id
              FROM drill_submissions s JOIN drills d ON d.id = s.drill_id
              WHERE s.status = 'published' AND s.library_drill_id IS NOT NULL AND d.status = 'published'
              ORDER BY s.team_id, s.library_drill_id, s.id DESC) AS pick
        WHERE own.id = pick.drill_id
    """)


def downgrade():
    op.drop_index("uq_drills_team_shadow", "drills")
    op.drop_column("drills", "shadows_drill_id")
