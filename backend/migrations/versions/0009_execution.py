"""execution: doing the work in the firm's systems, confirmed completions, destinations

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18 18:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('exec_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('destination_id', sa.String(36), nullable=True))
        batch_op.add_column(sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('external_ref', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('result', JSON, nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'destinations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_type_id', sa.String(36), sa.ForeignKey('task_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False, server_default='webhook'),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('actions', JSON, nullable=False, server_default='[]'),
        sa.Column('encrypted_secret', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('last_test', JSON, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_destinations_org_id', 'destinations', ['org_id'])
    op.create_index('ix_destinations_task_type_id', 'destinations', ['task_type_id'])


def downgrade() -> None:
    op.drop_index('ix_destinations_task_type_id', 'destinations')
    op.drop_index('ix_destinations_org_id', 'destinations')
    op.drop_table('destinations')
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_column('completed_at')
    with op.batch_alter_table('action_log', schema=None) as batch_op:
        for col in ('completed_at', 'result', 'external_ref', 'attempts', 'destination_id', 'exec_status'):
            batch_op.drop_column(col)
