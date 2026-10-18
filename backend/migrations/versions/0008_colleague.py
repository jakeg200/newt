"""colleague: messages between Newt and people, and per-person contact preferences

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferences', JSON, nullable=False, server_default='{}'))
    op.create_table(
        'messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('task_type_id', sa.String(36), sa.ForeignKey('task_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('payload', JSON, nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('urgency', sa.String(10), nullable=False, server_default='normal'),
        sa.Column('dedupe_key', sa.String(200), nullable=True),
        sa.Column('deliver_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_messages_task_type_id', 'messages', ['task_type_id'])
    op.create_index('ix_messages_user_id', 'messages', ['user_id'])
    op.create_index('ix_messages_dedupe_key', 'messages', ['dedupe_key'])


def downgrade() -> None:
    op.drop_index('ix_messages_dedupe_key', 'messages')
    op.drop_index('ix_messages_user_id', 'messages')
    op.drop_index('ix_messages_task_type_id', 'messages')
    op.drop_table('messages')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('preferences')
