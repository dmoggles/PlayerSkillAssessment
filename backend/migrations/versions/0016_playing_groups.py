"""Playing groups: the age group each player competes in, per period, replacing the single team age group.

Coaches rate players against the cohort they play in, which need not match the team (a mixed U10-U12 squad) or
birth year (league cut-offs, playing up). Each team's age group is copied to all its players in all its periods.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_groups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("period_id", sa.Integer, sa.ForeignKey("periods.id"), nullable=False, index=True),
        sa.Column("age_group", sa.SmallInteger, nullable=False),
        sa.UniqueConstraint("player_id", "period_id", name="uq_player_groups_player_period"),
        sa.CheckConstraint("age_group BETWEEN 5 AND 21", name="ck_player_groups_age_group"),
    )
    op.add_column("periods", sa.Column("starts_season", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute("INSERT INTO player_groups (player_id, period_id, age_group) "
               "SELECT pl.id, pe.id, t.age_group FROM teams t JOIN players pl ON pl.team_id = t.id "
               "JOIN periods pe ON pe.team_id = t.id WHERE t.age_group IS NOT NULL")
    op.drop_constraint("ck_teams_age_group", "teams", type_="check")
    op.drop_column("teams", "age_group")


def downgrade():
    op.add_column("teams", sa.Column("age_group", sa.SmallInteger))
    op.create_check_constraint("ck_teams_age_group", "teams", "age_group BETWEEN 5 AND 21")
    # A team's age group comes back as its most common playing group.
    op.execute("UPDATE teams t SET age_group = (SELECT g.age_group FROM player_groups g JOIN players p ON p.id = g.player_id "
               "WHERE p.team_id = t.id GROUP BY g.age_group ORDER BY count(*) DESC LIMIT 1)")
    op.drop_column("periods", "starts_season")
    op.drop_table("player_groups")
