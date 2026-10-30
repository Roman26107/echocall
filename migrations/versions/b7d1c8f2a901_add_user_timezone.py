"""add user timezone

Revision ID: b7d1c8f2a901
Revises: 9b8d2f4a6c31
Create Date: 2026-07-01 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1c8f2a901'
down_revision: Union[str, Sequence[str], None] = '9b8d2f4a6c31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'timezone',
            sa.String(length=64),
            nullable=False,
            server_default='Europe/Moscow',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'timezone')
