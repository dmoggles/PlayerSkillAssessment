"""Drill library: drills, tags, variations, media, links and coach votes; app admin flag on users.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table(
        "drills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False, server_default=""),
        sa.Column("format", sa.String(12), nullable=False),
        sa.Column("players_min", sa.SmallInteger, nullable=False),
        sa.Column("players_ideal", sa.SmallInteger, nullable=False),
        sa.Column("players_max", sa.SmallInteger, nullable=False),
        sa.Column("age_min", sa.SmallInteger, nullable=False),
        sa.Column("age_max", sa.SmallInteger, nullable=False),
        sa.Column("duration_min", sa.SmallInteger, nullable=False),
        sa.Column("duration_typical", sa.SmallInteger, nullable=False),
        sa.Column("session_phase", sa.String(20), nullable=False),
        sa.Column("intensity", sa.String(6), nullable=False),
        sa.Column("space_width_m", sa.Numeric(5, 1)),
        sa.Column("space_length_m", sa.Numeric(5, 1)),
        sa.Column("equipment", JSONB, nullable=False, server_default="[]"),
        sa.Column("setup", sa.Text, nullable=False, server_default=""),
        sa.Column("instructions", JSONB, nullable=False, server_default="[]"),
        sa.Column("coaching_points", JSONB, nullable=False, server_default="[]"),
        sa.Column("home_friendly", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_version", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published', 'retired')", name="ck_drills_status"),
        sa.CheckConstraint("format IN ('individual', 'small_group', 'unit', 'team')", name="ck_drills_format"),
        sa.CheckConstraint("players_min >= 1 AND players_min <= players_ideal AND players_ideal <= players_max", name="ck_drills_players"),
        sa.CheckConstraint("age_min >= 4 AND age_min <= age_max AND age_max <= 23", name="ck_drills_ages"),
        sa.CheckConstraint("duration_min >= 1 AND duration_min <= duration_typical", name="ck_drills_duration"),
        sa.CheckConstraint("session_phase IN ('warm_up', 'technical', 'opposed', 'small_sided_game', 'cool_down')", name="ck_drills_phase"),
        sa.CheckConstraint("intensity IN ('low', 'medium', 'high')", name="ck_drills_intensity"),
    )
    op.create_index("ix_drills_status", "drills", ["status"])
    op.create_table(
        "drill_tags",
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(40), sa.ForeignKey("skill_tags.id"), primary_key=True, index=True),
        sa.Column("weight", sa.Float, nullable=False),
        sa.CheckConstraint("weight IN (1.0, 0.5)", name="ck_drill_tags_weight"),
    )
    op.create_table(
        "drill_media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("caption", sa.String(200), nullable=False, server_default=""),
        sa.Column("url", sa.String(500)),
        sa.Column("video_start_seconds", sa.Integer),
        sa.Column("diagram", JSONB),
        sa.UniqueConstraint("drill_id", "position"),
        sa.CheckConstraint("kind IN ('video', 'diagram', 'link')", name="ck_drill_media_kind"),
        sa.CheckConstraint("(kind = 'diagram') = (diagram IS NOT NULL) AND (kind = 'diagram' OR url IS NOT NULL)", name="ck_drill_media_content"),
    )
    op.create_table(
        "drill_variations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("change", sa.Text, nullable=False, server_default=""),
        sa.Column("level_min", sa.SmallInteger, nullable=False),
        sa.Column("level_max", sa.SmallInteger, nullable=False),
        sa.Column("diagram_media_id", sa.Integer, sa.ForeignKey("drill_media.id", ondelete="SET NULL")),
        sa.Column("video_media_id", sa.Integer, sa.ForeignKey("drill_media.id", ondelete="SET NULL")),
        # Optional overrides of the drill's own content for this variation; empty = same as the drill.
        sa.Column("setup", sa.Text),
        sa.Column("equipment", JSONB),
        sa.Column("instructions", JSONB),
        sa.Column("coaching_points", JSONB),
        sa.Column("players_min", sa.SmallInteger),
        sa.Column("players_ideal", sa.SmallInteger),
        sa.Column("players_max", sa.SmallInteger),
        sa.Column("space_width_m", sa.Numeric(5, 1)),
        sa.Column("space_length_m", sa.Numeric(5, 1)),
        sa.UniqueConstraint("drill_id", "position"),
        sa.CheckConstraint("(players_min IS NULL AND players_ideal IS NULL AND players_max IS NULL) OR "
                           "(players_min >= 1 AND players_min <= players_ideal AND players_ideal <= players_max)", name="ck_drill_variations_players"),
        sa.CheckConstraint("(space_width_m IS NULL) = (space_length_m IS NULL)", name="ck_drill_variations_space"),
        sa.CheckConstraint("kind IN ('regression', 'base', 'escalator')", name="ck_drill_variations_kind"),
        sa.CheckConstraint("level_min >= 1 AND level_min <= level_max AND level_max <= 5", name="ck_drill_variations_levels"),
    )
    op.create_index("uq_drill_variations_one_base", "drill_variations", ["drill_id"], unique=True, postgresql_where=sa.text("kind = 'base'"))
    op.create_table(
        "drill_links",
        sa.Column("from_drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("to_drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("relation", sa.String(12), primary_key=True),
        sa.CheckConstraint("relation IN ('harder', 'easier', 'pairs_with')", name="ck_drill_links_relation"),
        sa.CheckConstraint("from_drill_id <> to_drill_id", name="ck_drill_links_not_self"),
    )
    op.create_table(
        "drill_votes",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("drill_id", sa.Integer, sa.ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True, index=True),
        sa.Column("vote", sa.SmallInteger, nullable=False),
        sa.Column("reason", sa.String(20)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("vote IN (-1, 1)", name="ck_drill_votes_vote"),
        sa.CheckConstraint("reason IS NULL OR (vote = -1 AND reason IN ('too_advanced', 'too_easy', 'unclear', 'equipment_or_space', 'did_not_work', 'other'))", name="ck_drill_votes_reason"),
    )


def downgrade():
    for table in ("drill_votes", "drill_links", "drill_variations", "drill_media", "drill_tags", "drills"):
        op.drop_table(table)
    op.drop_column("users", "is_admin")
