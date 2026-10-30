"""add blacklist entries

Revision ID: d4f0b2c6e913
Revises: c3e9a1b4d802
Create Date: 2026-07-02 11:47:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f0b2c6e913'
down_revision: Union[str, Sequence[str], None] = 'c3e9a1b4d802'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blacklist_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('blocked_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['blocked_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'blocked_user_id', name='uq_user_blocked_user'),
    )
    op.create_index(op.f('ix_blacklist_entries_user_id'), 'blacklist_entries', ['user_id'], unique=False)
    op.create_index(op.f('ix_blacklist_entries_blocked_user_id'), 'blacklist_entries', ['blocked_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_blacklist_entries_blocked_user_id'), table_name='blacklist_entries')
    op.drop_index(op.f('ix_blacklist_entries_user_id'), table_name='blacklist_entries')
    op.drop_table('blacklist_entries')
