"""add started_at to calls

Revision ID: 9b8d2f4a6c31
Revises: 0f7277457b45
Create Date: 2026-06-30 11:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b8d2f4a6c31'
down_revision: Union[str, Sequence[str], None] = '0f7277457b45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'calls',
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('calls', 'started_at')
