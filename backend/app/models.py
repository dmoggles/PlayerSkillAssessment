from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, SmallInteger, String, UniqueConstraint
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
    __table_args__ = (UniqueConstraint("team_id", "label"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
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


class AssessmentRevision(Base):
    __tablename__ = "assessment_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    editor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriorityConfirmation(Base):
    __tablename__ = "priority_confirmations"
    __table_args__ = (UniqueConstraint("player_id", "period_id", "rank"), UniqueConstraint("player_id", "period_id", "skill_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), index=True)
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
    details: Mapped[dict | None] = mapped_column(JSON)
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
