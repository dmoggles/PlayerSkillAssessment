"""Repair saved plans whose drill version ids went stale.

The drill loader used to recreate every drill's versions on each deploy, giving them new ids, so plans saved
earlier pointed at versions that no longer existed (links opened the base version; coaches' chosen starting
versions were lost). The loader now keeps ids stable; this re-points saved plans by drill and version title.

Revision ID: 0020
Revises: 0019
"""
import json
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    current = {(slug, title): vid for vid, slug, title in conn.execute(sa.text(
        "SELECT v.id, d.slug, v.title FROM drill_variations v JOIN drills d ON d.id = v.drill_id"))}
    for plan_id, plan in conn.execute(sa.text("SELECT id, plan FROM player_plans")).all():
        changed = False
        for slot in plan.get("slots", []):
            for week in slot.get("weeks", []):
                vid = current.get((slot["drill"], week.get("title")))
                if vid and vid != week.get("id"):
                    week["id"], changed = vid, True
        if changed:
            conn.execute(sa.text("UPDATE player_plans SET plan = CAST(:plan AS jsonb) WHERE id = :id"), {"plan": json.dumps(plan), "id": plan_id})


def downgrade():
    pass  # nothing to undo: the plans now point at versions that exist
