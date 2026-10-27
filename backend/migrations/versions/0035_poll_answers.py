"""Coaching polls' answers. Polls only run on the development site; elsewhere this table stays empty.

Revision ID: 0035
Revises: 0034
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "poll_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("poll_id", sa.String(40), nullable=False, index=True),
        sa.Column("respondent", sa.String(64), nullable=False),
        sa.Column("name", sa.String(60)),
        sa.Column("scenario_id", sa.String(40), nullable=False),
        sa.Column("x", sa.Float, nullable=False),
        sa.Column("y", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("poll_id", "respondent", "scenario_id", name="uq_poll_answers_one_each"),
    )


def downgrade():
    op.drop_table("poll_answers")
