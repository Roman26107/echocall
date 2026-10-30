"""add user call settings

Revision ID: c3e9a1b4d802
Revises: b7d1c8f2a901
Create Date: 2026-07-02 11:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e9a1b4d802'
down_revision: Union[str, Sequence[str], None] = 'b7d1c8f2a901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'incoming_call_policy',
            sa.String(length=32),
            nullable=False,
            server_default='everyone',
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'call_notification_mode',
            sa.String(length=32),
            nullable=False,
            server_default='once',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'call_notification_mode')
    op.drop_column('users', 'incoming_call_policy')
