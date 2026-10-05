"""One autosaved draft of each team's skill matrix.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "matrix_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False, unique=True),
        sa.Column("base_version_id", sa.Integer, sa.ForeignKey("matrix_versions.id"), nullable=False),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("matrix_drafts")
