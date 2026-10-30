"""add call notification interval

Revision ID: e5a8c1f0b742
Revises: d4f0b2c6e913
Create Date: 2026-07-02 12:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a8c1f0b742'
down_revision: Union[str, Sequence[str], None] = 'd4f0b2c6e913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('call_notification_interval', sa.Integer(), nullable=False, server_default='5'),
    )
    op.execute(
        "UPDATE users SET call_notification_mode = "
        "CASE WHEN call_notification_mode = 'repeat' THEN 'enabled' ELSE 'disabled' END"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE users SET call_notification_mode = "
        "CASE WHEN call_notification_mode = 'enabled' THEN 'repeat' ELSE 'once' END"
    )
    op.drop_column('users', 'call_notification_interval')
