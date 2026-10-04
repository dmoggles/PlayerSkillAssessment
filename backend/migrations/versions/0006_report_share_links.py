"""Read-only share link for a player report.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("player_reports", sa.Column("share_token_hash", sa.String(64), nullable=True))
    op.add_column("player_reports", sa.Column("share_issued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("player_reports", sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("player_reports", sa.Column("share_opened_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_player_reports_share_token_hash", "player_reports", ["share_token_hash"])


def downgrade():
    op.drop_constraint("uq_player_reports_share_token_hash", "player_reports", type_="unique")
    for column in ("share_opened_at", "share_expires_at", "share_issued_at", "share_token_hash"):
        op.drop_column("player_reports", column)
