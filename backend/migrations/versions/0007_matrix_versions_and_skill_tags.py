"""Versioned skill matrices in the database, global skill tags, and per-version skill-to-tag mapping.

The starter matrix (formerly bobtails_skill_matrix.json) becomes version 1 of the starter template,
and every existing team and period is linked to it.

Revision ID: 0007
Revises: 0006
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DATA = Path(__file__).parents[1] / "data"


def upgrade():
    tags = op.create_table(
        "skill_tags",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("area", sa.String(20), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        # What levels 1, 3 and 5 look like on the shared scale (Developing, Achieving, Excelling for the age group).
        sa.Column("level_1", sa.String(200), nullable=False),
        sa.Column("level_3", sa.String(200), nullable=False),
        sa.Column("level_5", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.CheckConstraint("area IN ('technical', 'tactical', 'mental', 'goalkeeping', 'physical')", name="ck_skill_tags_area"),
    )
    matrices = op.create_table(
        "skill_matrices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=True, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    versions = op.create_table(
        "matrix_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("matrix_id", sa.Integer, sa.ForeignKey("skill_matrices.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("matrix_id", "version"),
    )
    mapping = op.create_table(
        "matrix_skill_tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("matrix_version_id", sa.Integer, sa.ForeignKey("matrix_versions.id"), nullable=False, index=True),
        sa.Column("skill_id", sa.String(80), nullable=False),
        sa.Column("tag_id", sa.String(40), sa.ForeignKey("skill_tags.id"), nullable=False, index=True),
        sa.Column("weight", sa.Float, nullable=False),
        sa.UniqueConstraint("matrix_version_id", "skill_id", "tag_id"),
    )

    now = datetime.now(timezone.utc)
    op.bulk_insert(tags, [{**t, "active": True} for t in json.loads((DATA / "skill_tags_v1.json").read_text())])
    op.bulk_insert(matrices, [{"id": 1, "team_id": None, "name": "Starter: U12 7-a-side", "created_at": now}])
    op.bulk_insert(versions, [{"id": 1, "matrix_id": 1, "version": 1, "created_by": None, "published_at": now,
                               "document": json.loads((DATA / "starter_matrix_v1.json").read_text())}])
    op.bulk_insert(mapping, [{"matrix_version_id": 1, "skill_id": skill_id, "tag_id": tag_id, "weight": weight}
                             for skill_id, weights in json.loads((DATA / "starter_skill_tags_v1.json").read_text()).items()
                             for tag_id, weight in weights.items()])
    # Explicit ids above; move the sequences past them.
    for table in ("skill_matrices", "matrix_versions"):
        op.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")

    op.add_column("periods", sa.Column("matrix_version_id", sa.Integer, sa.ForeignKey("matrix_versions.id"), nullable=True))
    op.execute("UPDATE periods SET matrix_version_id = 1")
    op.alter_column("periods", "matrix_version_id", nullable=False)
    op.create_index("ix_periods_matrix_version_id", "periods", ["matrix_version_id"])


def downgrade():
    op.drop_index("ix_periods_matrix_version_id", table_name="periods")
    op.drop_column("periods", "matrix_version_id")
    for table in ("matrix_skill_tags", "matrix_versions", "skill_matrices", "skill_tags"):
        op.drop_table(table)
