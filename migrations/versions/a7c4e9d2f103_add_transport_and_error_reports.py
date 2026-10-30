"""add call transport mode and error reports

Revision ID: a7c4e9d2f103
Revises: f6b9a2d4e801
Create Date: 2026-08-03 23:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c4e9d2f103'
down_revision: Union[str, Sequence[str], None] = 'f6b9a2d4e801'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('calls', sa.Column('transport_mode', sa.String(length=16), nullable=True))
    op.create_table(
        'error_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('attachment_type', sa.String(length=16), nullable=True),
        sa.Column('telegram_file_id', sa.String(length=512), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('mime_type', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_error_reports_user_id', 'error_reports', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_error_reports_user_id', table_name='error_reports')
    op.drop_table('error_reports')
    op.drop_column('calls', 'transport_mode')
