"""Use unguessable Jitsi room names instead of sequential call IDs."""
import secrets

from alembic import op
import sqlalchemy as sa


revision = 'c9d2e4f6a801'
down_revision = 'b8d5f0a3c214'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('calls', sa.Column('room_name', sa.String(64), nullable=True))
    calls = sa.table('calls', sa.column('id', sa.Integer()),
                     sa.column('room_name', sa.String(64)))
    connection = op.get_bind()
    for call_id in connection.execute(sa.select(calls.c.id)).scalars().all():
        connection.execute(calls.update().where(calls.c.id == call_id).values(
            room_name=secrets.token_hex(24),
        ))
    with op.batch_alter_table('calls') as batch:
        batch.alter_column('room_name', existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint('uq_calls_room_name', ['room_name'])


def downgrade() -> None:
    with op.batch_alter_table('calls') as batch:
        batch.drop_constraint('uq_calls_room_name', type_='unique')
        batch.drop_column('room_name')