"""add user theme

Revision ID: f6b9a2d4e801
Revises: e5a8c1f0b742
Create Date: 2026-07-02 17:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6b9a2d4e801'
down_revision: Union[str, Sequence[str], None] = 'e5a8c1f0b742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'theme',
            sa.String(length=16),
            nullable=False,
            server_default='light',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'theme')
