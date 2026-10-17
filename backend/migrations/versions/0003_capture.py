"""capture

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 14:20:40.200537
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    op.create_table('capture_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('connection_id', sa.String(length=36), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stats', JSON, nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('capture_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_capture_runs_connection_id'), ['connection_id'], unique=False)

    op.create_table('unmatched_actions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('connection_id', sa.String(length=36), nullable=False),
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('source_ref', sa.String(length=500), nullable=False),
    sa.Column('acted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.String(length=200), nullable=False),
    sa.Column('summary', JSON, nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['capture_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('unmatched_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_unmatched_actions_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_unmatched_actions_run_id'), ['run_id'], unique=False)

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_type_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('name', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('config', JSON, nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch_op.create_index(batch_op.f('ix_connections_task_type_id'), ['task_type_id'], unique=False)
        batch_op.create_foreign_key('fk_connections_task_type', 'task_types', ['task_type_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('connection_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('match_keys', JSON, nullable=False, server_default='{}'))
        batch_op.create_index(batch_op.f('ix_cases_connection_id'), ['connection_id'], unique=False)
        batch_op.create_unique_constraint('uq_cases_connection_source', ['connection_id', 'source_ref'])
        batch_op.create_foreign_key('fk_cases_connection', 'connections', ['connection_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('human_actions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_ref', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('match_method', sa.String(length=30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('human_actions', schema=None) as batch_op:
        batch_op.drop_column('match_method')
        batch_op.drop_column('source_ref')

    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cases_connection', type_='foreignkey')
        batch_op.drop_constraint('uq_cases_connection_source', type_='unique')
        batch_op.drop_index(batch_op.f('ix_cases_connection_id'))
        batch_op.drop_column('match_keys')
        batch_op.drop_column('connection_id')

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_constraint('fk_connections_task_type', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_connections_task_type_id'))
        batch_op.drop_column('created_at')
        batch_op.drop_column('config')
        batch_op.drop_column('name')
        batch_op.drop_column('task_type_id')

    with op.batch_alter_table('unmatched_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_unmatched_actions_run_id'))
        batch_op.drop_index(batch_op.f('ix_unmatched_actions_connection_id'))
    op.drop_table('unmatched_actions')

    with op.batch_alter_table('capture_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_capture_runs_connection_id'))
    op.drop_table('capture_runs')
