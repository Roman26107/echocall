"""add system metrics and analytics history

Revision ID: b8d5f0a3c214
Revises: a7c4e9d2f103
Create Date: 2026-08-04 15:48:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d5f0a3c214'
down_revision: Union[str, Sequence[str], None] = 'a7c4e9d2f103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_metric_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('server', sa.String(length=16), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=False),
        sa.Column('memory_percent', sa.Float(), nullable=False),
        sa.Column('disk_percent', sa.Float(), nullable=False),
        sa.Column('services', sa.JSON(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_system_metric_samples_server', 'system_metric_samples', ['server'], unique=False)
    op.create_index('ix_system_metric_samples_recorded_at', 'system_metric_samples', ['recorded_at'], unique=False)
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_analytics_snapshots_snapshot_date', 'analytics_snapshots', ['snapshot_date'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_analytics_snapshots_snapshot_date', table_name='analytics_snapshots')
    op.drop_table('analytics_snapshots')
    op.drop_index('ix_system_metric_samples_recorded_at', table_name='system_metric_samples')
    op.drop_index('ix_system_metric_samples_server', table_name='system_metric_samples')
    op.drop_table('system_metric_samples')
