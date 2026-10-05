"""Team setting for player gender, and pronoun placeholders in the starter matrix.

The starter's version 1 is converted in place: every pronoun for a player (she/her and the neutral they/their
already used in some descriptors) becomes a placeholder. The meaning is unchanged; each team now sees pronouns
matching its setting. Published versions are otherwise never edited.

Revision ID: 0008
Revises: 0007
"""
import json
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# (skill id, level): (original wording, wording with placeholders)
CONVERSIONS = {
    ("communication", "1"): (
        "Silent during play; teammates don't know where she is or what she wants",
        "Silent during play; teammates don't know where {they} {is|are} or what {they} {wants|want}"),
    ("handling_shot_stopping", "1"): (
        "Drops or parries balls she should hold; uncomfortable with shots at height",
        "Drops or parries balls {they} should hold; uncomfortable with shots at height"),
    ("handling_shot_stopping", "3"): (
        "Holds most shots at her body cleanly; diving stops still developing",
        "Holds most shots at {their} body cleanly; diving stops still developing"),
    ("handling_shot_stopping", "5"): (
        "Gets behind the ball consistently, strong hands, deals with shots across her body",
        "Gets behind the ball consistently, strong hands, deals with shots across {their} body"),
    ("commanding_area", "5"): (
        "Claims crosses confidently, organises the backline, comes off her line to deal with through balls",
        "Claims crosses confidently, organises the backline, comes off {their} line to deal with through balls"),
    ("positioning_angles", "5"): (
        "Consistently sets her position based on where the ball is, making herself big without being exposed",
        "Consistently sets {their} position based on where the ball is, making {themself} big without being exposed"),
    ("first_touch_body_shape", "1"): (
        "Ball bounces away; receives square-on with no idea what's behind them",
        "Ball bounces away; receives square-on with no idea what's behind {them}"),
    ("restarts", "1"): (
        "Plays the restart to the nearest player regardless of whether they're marked; no awareness of options",
        "Plays the restart to the nearest player regardless of whether {they}{'s|'re} marked; no awareness of options"),
    ("receiving_movement", "5"): (
        "Consistently moves to create an angle, times the run so they're free when the ball arrives",
        "Consistently moves to create an angle, times the run so {they}{'s|'re} free when the ball arrives"),
    ("shape_awareness", "1"): (
        "Doesn't know their starting position or drifts far from it",
        "Doesn't know {their} starting position or drifts far from it"),
    ("shape_awareness", "5"): (
        "Adjusts position based on where the ball is, not just their own zone",
        "Adjusts position based on where the ball is, not just {their} own zone"),
}


def convert(to_placeholders: bool):
    conn = op.get_bind()
    doc = conn.execute(sa.text("SELECT document FROM matrix_versions WHERE id = 1")).scalar_one()
    for section in doc["sections"]:
        for skill in section["skills"]:
            for level, text in skill["descriptors"].items():
                pair = CONVERSIONS.get((skill["id"], level))
                if pair:
                    original, converted = pair
                    expected, replacement = (original, converted) if to_placeholders else (converted, original)
                    if text != expected:
                        raise RuntimeError(f"Unexpected wording for {skill['id']} level {level}: {text!r}")
                    skill["descriptors"][level] = replacement
    conn.execute(sa.text("UPDATE matrix_versions SET document = CAST(:doc AS jsonb) WHERE id = 1"), {"doc": json.dumps(doc)})


def upgrade():
    op.add_column("teams", sa.Column("player_gender", sa.String(10), nullable=False, server_default="mixed"))
    op.create_check_constraint("ck_teams_player_gender", "teams", "player_gender IN ('girls', 'boys', 'mixed')")
    convert(to_placeholders=True)


def downgrade():
    convert(to_placeholders=False)
    op.drop_constraint("ck_teams_player_gender", "teams", type_="check")
    op.drop_column("teams", "player_gender")
