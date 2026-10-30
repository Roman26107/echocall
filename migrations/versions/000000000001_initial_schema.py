"""Create the original schema before the incremental migrations.

Revision ID: 000000000001
Revises: None
"""
from alembic import op
import sqlalchemy as sa


revision = '000000000001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(32), nullable=True),
        sa.Column('display_name', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_table(
        'calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('call_type', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('max_participants', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'call_participants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('call_id', sa.Integer(), sa.ForeignKey('calls.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('access_token', sa.String(128), nullable=False),
        sa.Column('role', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('call_id', 'user_id', name='uq_call_user'),
    )
    op.create_index('ix_call_participants_access_token', 'call_participants',
                    ['access_token'], unique=True)
    op.create_table(
        'contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('contact_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('is_favorite', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'contact_user_id', name='uq_user_contact'),
    )
    op.create_index('ix_contacts_user_id', 'contacts', ['user_id'], unique=False)
    op.create_index('ix_contacts_contact_user_id', 'contacts', ['contact_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_contacts_contact_user_id', table_name='contacts')
    op.drop_index('ix_contacts_user_id', table_name='contacts')
    op.drop_table('contacts')
    op.drop_index('ix_call_participants_access_token', table_name='call_participants')
    op.drop_table('call_participants')
    op.drop_table('calls')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_table('users')
