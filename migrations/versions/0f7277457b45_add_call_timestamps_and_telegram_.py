"""add call timestamps and telegram message fields

Revision ID: 0f7277457b45
Revises: 000000000001
Create Date: 2026-05-12 11:17:28.849154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f7277457b45'
down_revision: Union[str, Sequence[str], None] = '000000000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('call_participants', sa.Column('telegram_message_id', sa.BigInteger(), nullable=True))
    op.add_column('call_participants', sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('call_participants', 'telegram_chat_id')
    op.drop_column('call_participants', 'telegram_message_id')
