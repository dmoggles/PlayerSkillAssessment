"""Focus check-ins: at the end of a development cycle, how each focus skill went (better, same or worse).

Stored on the cycle, apart from the period assessment, so period-to-period comparisons stay independent.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cycle_checkins",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cycle_id", sa.Integer, sa.ForeignKey("development_cycles.id"), nullable=False, index=True),
        sa.Column("skill_id", sa.String(80), nullable=False),
        sa.Column("trend", sa.String(6), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cycle_id", "skill_id", name="uq_cycle_checkins_skill"),
        sa.CheckConstraint("trend IN ('better', 'same', 'worse')", name="ck_cycle_checkins_trend"),
    )


def downgrade():
    op.drop_table("cycle_checkins")
