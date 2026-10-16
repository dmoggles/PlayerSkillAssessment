"""Skill categories: a broad grouping of skill tags (Passing, Finishing, ...) for the player profile web.

Revision ID: 0022
Revises: 0021
"""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

DATA = Path(__file__).parents[1] / "data"


def upgrade():
    categories = op.create_table(
        "skill_categories",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("applies_to", sa.String(10), nullable=False),
        sa.Column("sort_order", sa.SmallInteger, nullable=False),
        sa.CheckConstraint("applies_to IN ('outfield', 'goalkeeper', 'both')", name="ck_skill_categories_applies_to"),
    )
    op.add_column("skill_tags", sa.Column("category", sa.String(40), sa.ForeignKey("skill_categories.id"), nullable=True))
    data = json.loads((DATA / "skill_categories_v1.json").read_text())
    op.bulk_insert(categories, data["categories"])
    skill_tags = sa.table("skill_tags", sa.column("id", sa.String), sa.column("category", sa.String))
    for tag_id, category in data["tags"].items():
        op.execute(skill_tags.update().where(skill_tags.c.id == tag_id).values(category=category))


def downgrade():
    op.drop_column("skill_tags", "category")
    op.drop_table("skill_categories")
