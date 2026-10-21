from datetime import date as date_type, datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, Numeric, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # App admins curate the shared drill library.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    self_assessment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fills pronoun placeholders in skill descriptions: girls, boys or mixed (they/their).
    player_gender: Mapped[str] = mapped_column(String(10), default="mixed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("team_id", "name_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Period(Base):
    __tablename__ = "periods"
    # One active period per team; the API switches the old one off before switching a new one on.
    __table_args__ = (UniqueConstraint("team_id", "label"), Index("uq_periods_one_active", "team_id", unique=True, postgresql_where=text("is_active")))
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set by the coach when the period opens a new season, the point where players usually move up an age group.
    starts_season: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # The skill matrix version everyone in this period is rated on.
    matrix_version_id: Mapped[int] = mapped_column(ForeignKey("matrix_versions.id"), index=True)


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("player_id", "period_id", "assessor"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    assessor: Mapped[str] = mapped_column(String(10))
    position: Mapped[str] = mapped_column(String(20))
    primary_position: Mapped[str | None] = mapped_column(String(20))
    secondary_position: Mapped[str | None] = mapped_column(String(20))
    secondary_position_frequency: Mapped[str | None] = mapped_column(String(20))
    matrix_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    note: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    ratings: Mapped[list["Rating"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    player: Mapped[Player] = relationship(lazy="joined")

    @property
    def player_name(self):
        return self.player.name


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("assessment_id", "skill_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    skill_id: Mapped[str] = mapped_column(String(80))
    score: Mapped[int | None] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(String(500))
    # Copied from the previous period when it started from its ratings; cleared once the coach re-rates or confirms it.
    carried: Mapped[bool] = mapped_column(Boolean, default=False)


class AssessmentRevision(Base):
    __tablename__ = "assessment_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DevelopmentCycle(Base):
    """One round of focus areas and a plan for a player within a period (numbered from 1). A period can hold
    several, since periods often run half a season and plans about four weeks; the latest is the current one."""
    __tablename__ = "development_cycles"
    __table_args__ = (UniqueConstraint("player_id", "period_id", "number", name="uq_development_cycles_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    number: Mapped[int] = mapped_column(SmallInteger)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CycleCheckin(Base):
    """How one focus skill went over a development cycle, recorded as the next cycle starts: better, same or
    worse, with an optional note. Kept apart from the period assessment."""
    __tablename__ = "cycle_checkins"
    __table_args__ = (UniqueConstraint("cycle_id", "skill_id", name="uq_cycle_checkins_skill"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("development_cycles.id"), index=True)
    skill_id: Mapped[str] = mapped_column(String(80))
    trend: Mapped[str] = mapped_column(String(6))
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriorityConfirmation(Base):
    __tablename__ = "priority_confirmations"
    __table_args__ = (UniqueConstraint("cycle_id", "rank", name="uq_priority_confirmations_cycle_rank"),
                      UniqueConstraint("cycle_id", "skill_id", name="uq_priority_confirmations_cycle_skill"))
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("development_cycles.id"), index=True)
    skill_id: Mapped[str] = mapped_column(String(80))
    rank: Mapped[int] = mapped_column(SmallInteger)
    algorithm_suggested: Mapped[bool] = mapped_column(Boolean, default=True)
    coach_note: Mapped[str | None] = mapped_column(String(500))


class SelfLink(Base):
    __tablename__ = "self_links"
    __table_args__ = (UniqueConstraint("player_id", "period_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Membership and destructive team changes. No foreign keys, so events outlive deleted teams and players."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    actor_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(40))
    target_email: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlayerReport(Base):
    __tablename__ = "player_reports"
    __table_args__ = (UniqueConstraint("player_id", "period_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    message: Mapped[str | None] = mapped_column(String(1000))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    share_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    share_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    share_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    share_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerGroup(Base):
    """The age group a player competes in during a period (the "U" number). Ratings are judged against this
    cohort, and drills are matched to it. Carried into each new period; moved up a year when a season starts."""
    __tablename__ = "player_groups"
    __table_args__ = (UniqueConstraint("player_id", "period_id", name="uq_player_groups_player_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    age_group: Mapped[int] = mapped_column(SmallInteger)


class PlayerPlan(Base):
    """A player's saved development plan for a development cycle, in the planner's output format. Regenerating replaces it.
    It appears in the player report, and the report's share link opens its drills."""
    __tablename__ = "player_plans"
    __table_args__ = (UniqueConstraint("cycle_id", name="uq_player_plans_cycle"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("development_cycles.id"), index=True)
    plan: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillCategory(Base):
    """A broad grouping of skill tags (Passing, Finishing, ...) for a quick picture of a player, such as the
    profile web. Each tag belongs to at most one category. applies_to says whose web shows it."""
    __tablename__ = "skill_categories"
    __table_args__ = (CheckConstraint("applies_to IN ('outfield', 'goalkeeper', 'both')", name="ck_skill_categories_applies_to"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    applies_to: Mapped[str] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class SkillTag(Base):
    """Global taxonomy that skills, drills and training plans share. level_1/3/5 describe Developing, Achieving
    and Excelling on the common scale, relative to the player's age group."""
    __tablename__ = "skill_tags"
    __table_args__ = (CheckConstraint("area IN ('technical', 'tactical', 'mental', 'goalkeeping', 'physical')", name="ck_skill_tags_area"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    area: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(80))
    level_1: Mapped[str] = mapped_column(String(200))
    level_3: Mapped[str] = mapped_column(String(200))
    level_5: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str | None] = mapped_column(ForeignKey("skill_categories.id"))


class SkillMatrix(Base):
    """A starter template (team_id is null) or a team's own matrix."""
    __tablename__ = "skill_matrices"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MatrixVersion(Base):
    """An immutable published version of a matrix: labels, descriptors, weights and dependencies."""
    __tablename__ = "matrix_versions"
    __table_args__ = (UniqueConstraint("matrix_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_id: Mapped[int] = mapped_column(ForeignKey("skill_matrices.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MatrixSkillTag(Base):
    """Which tags a skill in a given matrix version feeds, and how strongly."""
    __tablename__ = "matrix_skill_tags"
    __table_args__ = (UniqueConstraint("matrix_version_id", "skill_id", "tag_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_version_id: Mapped[int] = mapped_column(ForeignKey("matrix_versions.id"), index=True)
    skill_id: Mapped[str] = mapped_column(String(80))
    tag_id: Mapped[str] = mapped_column(ForeignKey("skill_tags.id"), index=True)
    weight: Mapped[float] = mapped_column(Float)


class MatrixDraft(Base):
    """A team's work-in-progress matrix, autosaved. Skills carry their tags inside the document until publish."""
    __tablename__ = "matrix_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    base_version_id: Mapped[int] = mapped_column(ForeignKey("matrix_versions.id"))
    document: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Drill(Base):
    """One drill: in the shared library (curated by app admins, loaded from data files), or a team's own, written by
    its coaches (team_id set, source_version "team"; the loader never touches these)."""
    __tablename__ = "drills"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(300), default="")
    format: Mapped[str] = mapped_column(String(12))
    players_min: Mapped[int] = mapped_column(SmallInteger)
    players_ideal: Mapped[int] = mapped_column(SmallInteger)
    players_max: Mapped[int] = mapped_column(SmallInteger)
    age_min: Mapped[int] = mapped_column(SmallInteger)
    age_max: Mapped[int] = mapped_column(SmallInteger)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    duration_typical: Mapped[int] = mapped_column(SmallInteger)
    session_phase: Mapped[str] = mapped_column(String(20))
    intensity: Mapped[str] = mapped_column(String(6))
    space_width_m: Mapped[float | None] = mapped_column(Numeric(5, 1))
    space_length_m: Mapped[float | None] = mapped_column(Numeric(5, 1))
    equipment: Mapped[list] = mapped_column(JSONB, default=list)
    setup: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[list] = mapped_column(JSONB, default=list)
    coaching_points: Mapped[list] = mapped_column(JSONB, default=list)
    home_friendly: Mapped[bool] = mapped_column(Boolean, default=False)
    # How to run a home drill indoors (soft ball, household items), shown as its own section.
    indoors: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[str | None] = mapped_column(String(40))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    # A team drill that is the team's version of a library drill: for that team it replaces the library drill in the
    # library and the planners. Its content is its own; nothing is borrowed from the library drill.
    shadows_drill_id: Mapped[int | None] = mapped_column(ForeignKey("drills.id", ondelete="SET NULL"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillSubmission(Base):
    """A team drill offered to the shared library. Accepting it reserves a library slug; it is published when a data
    file with that slug is loaded, after an admin has written it up with diagrams like any library drill."""
    __tablename__ = "drill_submissions"
    __table_args__ = (CheckConstraint("status IN ('pending', 'accepted', 'declined', 'published')", name="ck_drill_submissions_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")
    reason: Mapped[str] = mapped_column(String(1000), default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    library_slug: Mapped[str | None] = mapped_column(String(80), unique=True)
    library_drill_id: Mapped[int | None] = mapped_column(ForeignKey("drills.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillTag(Base):
    __tablename__ = "drill_tags"
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("skill_tags.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)
    # False when the variation ladder does not describe this skill (a 1v1 drill that escalates for the attacker only).
    on_ladder: Mapped[bool] = mapped_column(Boolean, default=True)


class DrillMedia(Base):
    """A video link, other link, or animated diagram (JSON drawn by the app)."""
    __tablename__ = "drill_media"
    __table_args__ = (UniqueConstraint("drill_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(8))
    caption: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str | None] = mapped_column(String(500))
    video_start_seconds: Mapped[int | None] = mapped_column(Integer)
    diagram: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class DrillVariation(Base):
    """One rung of a drill's ladder: an easier regression, the base version, or a harder escalator."""
    __tablename__ = "drill_variations"
    __table_args__ = (UniqueConstraint("drill_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(120))
    change: Mapped[str] = mapped_column(Text, default="")
    level_min: Mapped[int] = mapped_column(SmallInteger)
    level_max: Mapped[int] = mapped_column(SmallInteger)
    diagram_media_id: Mapped[int | None] = mapped_column(ForeignKey("drill_media.id", ondelete="SET NULL"))
    # A video shown only for this variation; videos no variation claims are shown for the whole drill.
    video_media_id: Mapped[int | None] = mapped_column(ForeignKey("drill_media.id", ondelete="SET NULL"))
    # Overrides of the drill's content for this variation (None = same as the drill).
    setup: Mapped[str | None] = mapped_column(Text)
    # none_as_null: store Python None as SQL NULL ("no override"), not a JSON null value.
    equipment: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    instructions: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    coaching_points: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    players_min: Mapped[int | None] = mapped_column(SmallInteger)
    players_ideal: Mapped[int | None] = mapped_column(SmallInteger)
    players_max: Mapped[int | None] = mapped_column(SmallInteger)
    space_width_m: Mapped[float | None] = mapped_column(Numeric(5, 1))
    space_length_m: Mapped[float | None] = mapped_column(Numeric(5, 1))


class DrillLink(Base):
    __tablename__ = "drill_links"
    from_drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True)
    to_drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True)
    relation: Mapped[str] = mapped_column(String(12), primary_key=True)


class TrainingSession(Base):
    """A planned team training session on a date: a focus, a length, and blocks of drills (see sessions.py). With
    versions "groups", the expected players are split into level groups, each running the drills at its own version."""
    __tablename__ = "training_sessions"
    __table_args__ = (CheckConstraint("versions IN ('single', 'groups')", name="ck_training_sessions_versions"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
    date: Mapped[date_type] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(5))  # "18:30"
    length_minutes: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(120))
    focus_tags: Mapped[list] = mapped_column(JSONB, default=list)
    versions: Mapped[str] = mapped_column(String(6), default="single")
    groups: Mapped[list] = mapped_column(JSONB, default=list)  # [{"name", "player_ids"}], groups mode only
    notes: Mapped[str] = mapped_column(String(2000), default="")
    # Planned from a team template: the breakdown is copied, so editing or deleting the template leaves the session as it was.
    # Null minutes: the default breakdown for the session's length.
    template_id: Mapped[int | None] = mapped_column(ForeignKey("session_templates.id", ondelete="SET NULL"))
    phase_minutes: Mapped[dict | None] = mapped_column(JSONB)  # {phase: minutes}
    # The two teams for its full squad game: {"by": "planner" | "coach", "player_ids": [[...], [...]]}. The planner's
    # teams are balanced again whenever the expected players change; a coach's keep their players.
    match_teams: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionTemplate(Base):
    """A team's own breakdown of a session: a length and the minutes for each part it includes."""
    __tablename__ = "session_templates"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_session_templates_team_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    length_minutes: Mapped[int] = mapped_column(SmallInteger)
    minutes: Mapped[dict] = mapped_column(JSONB, default=dict)  # {phase: minutes}, only the parts included
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionBlock(Base):
    """One part of a session, in order: a drill at a version (one per group in groups mode), or the coach's own
    activity when drill_id is null."""
    __tablename__ = "session_blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    phase: Mapped[str] = mapped_column(String(20))
    minutes: Mapped[int] = mapped_column(SmallInteger)
    drill_id: Mapped[int | None] = mapped_column(ForeignKey("drills.id"))
    title: Mapped[str] = mapped_column(String(160), default="")
    variation_id: Mapped[int | None] = mapped_column(ForeignKey("drill_variations.id", ondelete="SET NULL"))
    group_variations: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"0": variation_id, ...}
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    chosen_by: Mapped[str] = mapped_column(String(8), default="planner")
    notes: Mapped[str] = mapped_column(String(1000), default="")


class SessionAttendance(Base):
    """Who is expected at a session (entered beforehand, for planning) and who came (afterwards)."""
    __tablename__ = "session_attendance"
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    expected: Mapped[bool] = mapped_column(Boolean, default=True)
    attended: Mapped[bool | None] = mapped_column(Boolean)


class AccessRequest(Base):
    """A club asking for access from the public site. Site admins invite or decline it; the cleanup job removes
    requests once they're dealt with (see maintenance.py), since the people asking have no account with us."""
    __tablename__ = "access_requests"
    __table_args__ = (CheckConstraint("status IN ('pending', 'invited', 'declined')", name="ck_access_requests_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), index=True)
    club: Mapped[str] = mapped_column(String(120))
    teams: Mapped[int | None] = mapped_column(SmallInteger)
    message: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillVideoSuggestion(Base):
    """A video a coach suggests for a drill. Site admins review it; approved ones are shown with the drill's own
    videos. Kept apart from drill_media, which the drill loader rewrites from the data files on every deploy."""
    __tablename__ = "drill_video_suggestions"
    __table_args__ = (UniqueConstraint("drill_id", "host", "video_id"),
                      CheckConstraint("status IN ('pending', 'approved', 'rejected', 'hidden')", name="ck_drill_video_suggestions_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), index=True)
    # The variation the video shows; null means the drill as a whole.
    variation_id: Mapped[int | None] = mapped_column(ForeignKey("drill_variations.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(500))
    host: Mapped[str] = mapped_column(String(10))
    video_id: Mapped[str] = mapped_column(String(40))
    start_seconds: Mapped[int | None] = mapped_column(Integer)
    # From the host's oEmbed when suggested.
    title: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(120), default="")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(500), default="")
    suggested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    caption: Mapped[str | None] = mapped_column(String(200))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String(20))
    reject_note: Mapped[str | None] = mapped_column(String(300))
    reports: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillLinkReport(Base):
    """A coach reporting a drill's video or link as broken or inappropriate. Reports are kept by URL, not by media
    row, because the loader rewrites drill_media on every deploy; hiding a link hides that URL on that drill."""
    __tablename__ = "drill_link_reports"
    __table_args__ = (CheckConstraint("reason IN ('dead', 'inappropriate', 'other')", name="ck_drill_link_reports_reason"),
                      CheckConstraint("status IN ('open', 'hidden', 'dismissed')", name="ck_drill_link_reports_status"),
                      Index("ix_drill_link_reports_drill_url", "drill_id", "url"))
    id: Mapped[int] = mapped_column(primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(500))
    # Set when the link is an approved coach's suggestion rather than one of the drill's own.
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("drill_video_suggestions.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(15))
    note: Mapped[str] = mapped_column(String(500), default="")
    reported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillVote(Base):
    """A coach's like (+1) or dislike (-1) of a drill; the reason is optional and for dislikes only."""
    __tablename__ = "drill_votes"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    drill_id: Mapped[int] = mapped_column(ForeignKey("drills.id", ondelete="CASCADE"), primary_key=True)
    vote: Mapped[int] = mapped_column(SmallInteger)
    reason: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
