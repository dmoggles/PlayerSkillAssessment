"""Development cycles: a period can hold several rounds of focus areas and a plan, kept as history.

Periods are often semi-annual while plans run about four weeks. Each cycle has its own confirmed priorities and
saved plan; the latest cycle is the current one. Existing priorities and plans become cycle 1 of their period.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "development_cycles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False, index=True),
        sa.Column("number", sa.SmallInteger, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.UniqueConstraint("player_id", "period_id", "number", name="uq_development_cycles_number"),
    )
    op.execute("""
        INSERT INTO development_cycles (player_id, period_id, number, started_at)
        SELECT player_id, period_id, 1, MIN(started) FROM (
            SELECT pc.player_id, pc.period_id, pe.created_at AS started FROM priority_confirmations pc JOIN periods pe ON pe.id = pc.period_id
            UNION ALL
            SELECT pp.player_id, pp.period_id, pp.created_at FROM player_plans pp
        ) existing GROUP BY player_id, period_id""")
    for table in ("priority_confirmations", "player_plans"):
        op.add_column(table, sa.Column("cycle_id", sa.Integer, sa.ForeignKey("development_cycles.id"), index=True))
        op.execute(f"UPDATE {table} t SET cycle_id = c.id FROM development_cycles c "
                   f"WHERE c.player_id = t.player_id AND c.period_id = t.period_id AND c.number = 1")
        op.alter_column(table, "cycle_id", nullable=False)
    op.drop_constraint("priority_confirmations_player_id_period_id_rank_key", "priority_confirmations", type_="unique")
    op.drop_constraint("priority_confirmations_player_id_period_id_skill_id_key", "priority_confirmations", type_="unique")
    op.create_unique_constraint("uq_priority_confirmations_cycle_rank", "priority_confirmations", ["cycle_id", "rank"])
    op.create_unique_constraint("uq_priority_confirmations_cycle_skill", "priority_confirmations", ["cycle_id", "skill_id"])
    op.drop_constraint("uq_player_plans_player_period", "player_plans", type_="unique")
    op.create_unique_constraint("uq_player_plans_cycle", "player_plans", ["cycle_id"])


def downgrade():
    # Only each period's latest cycle survives: earlier cycles' priorities and plans are deleted.
    for table in ("priority_confirmations", "player_plans"):
        op.execute(f"DELETE FROM {table} t USING development_cycles c WHERE c.id = t.cycle_id AND c.number < "
                   f"(SELECT MAX(number) FROM development_cycles l WHERE l.player_id = c.player_id AND l.period_id = c.period_id)")
    op.drop_constraint("uq_player_plans_cycle", "player_plans", type_="unique")
    op.create_unique_constraint("uq_player_plans_player_period", "player_plans", ["player_id", "period_id"])
    op.drop_constraint("uq_priority_confirmations_cycle_skill", "priority_confirmations", type_="unique")
    op.drop_constraint("uq_priority_confirmations_cycle_rank", "priority_confirmations", type_="unique")
    op.create_unique_constraint("priority_confirmations_player_id_period_id_skill_id_key", "priority_confirmations", ["player_id", "period_id", "skill_id"])
    op.create_unique_constraint("priority_confirmations_player_id_period_id_rank_key", "priority_confirmations", ["player_id", "period_id", "rank"])
    for table in ("priority_confirmations", "player_plans"):
        op.drop_column(table, "cycle_id")
    op.drop_table("development_cycles")
