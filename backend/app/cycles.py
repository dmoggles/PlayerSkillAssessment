"""Development cycles: rounds of focus areas and a plan within a period. The latest cycle is the current one;
earlier ones are history. Priorities and saved plans belong to a cycle."""
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from .models import DevelopmentCycle, PlayerPlan, PriorityConfirmation, User


def current_cycle(db: DbSession, player_id: int, period_id: int) -> DevelopmentCycle | None:
    return db.query(DevelopmentCycle).filter_by(player_id=player_id, period_id=period_id).order_by(DevelopmentCycle.number.desc()).first()


def ensure_cycle(db: DbSession, player_id: int, period_id: int, user: User) -> DevelopmentCycle:
    """The current cycle, starting cycle 1 when the player has none in this period yet."""
    cycle = current_cycle(db, player_id, period_id)
    if not cycle:
        cycle = DevelopmentCycle(player_id=player_id, period_id=period_id, number=1, created_by=user.id)
        db.add(cycle)
        db.flush()
    return cycle


def current_priorities(db: DbSession, player_id: int, period_id: int) -> list[PriorityConfirmation]:
    cycle = current_cycle(db, player_id, period_id)
    if not cycle:
        return []
    return db.query(PriorityConfirmation).filter_by(cycle_id=cycle.id).order_by(PriorityConfirmation.rank).all()


def current_plan(db: DbSession, player_id: int, period_id: int) -> PlayerPlan | None:
    cycle = current_cycle(db, player_id, period_id)
    return db.query(PlayerPlan).filter_by(cycle_id=cycle.id).first() if cycle else None


def latest_cycle_ids(db: DbSession, **filters) -> set[int]:
    """The current cycle of every player and period matching the filters (e.g. period_id=…)."""
    latest = db.query(DevelopmentCycle.player_id, DevelopmentCycle.period_id, func.max(DevelopmentCycle.number).label("n")).filter_by(
        **filters).group_by(DevelopmentCycle.player_id, DevelopmentCycle.period_id).subquery()
    rows = db.query(DevelopmentCycle.id).join(latest, (DevelopmentCycle.player_id == latest.c.player_id) &
                                              (DevelopmentCycle.period_id == latest.c.period_id) & (DevelopmentCycle.number == latest.c.n))
    return {row.id for row in rows}
