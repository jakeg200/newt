"""backtest

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17 14:37:23.221856
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    op.create_table('backtest_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('task_type_id', sa.String(length=36), nullable=False),
    sa.Column('agent_id', sa.String(length=36), nullable=False),
    sa.Column('requested_by', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('params', JSON, nullable=False),
    sa.Column('agent_version', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('handbook_version', sa.Integer(), nullable=True),
    sa.Column('rules_version', sa.Integer(), nullable=True),
    sa.Column('config_hash', sa.String(length=64), nullable=False),
    sa.Column('progress', JSON, nullable=False),
    sa.Column('stats', JSON, nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backtest_runs_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_backtest_runs_task_type_id'), ['task_type_id'], unique=False)

    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=200), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('config', JSON, nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('run_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('model', sa.String(length=100), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index(batch_op.f('ix_predictions_run_id'), ['run_id'], unique=False)
        batch_op.create_foreign_key('fk_predictions_run', 'backtest_runs', ['run_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_predictions_run', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_predictions_run_id'))
        for col in ('latency_ms', 'cost_usd', 'output_tokens', 'input_tokens', 'error', 'model', 'run_id'):
            batch_op.drop_column(col)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        for col in ('finished_at', 'started_at', 'error', 'attempts'):
            batch_op.drop_column(col)

    with op.batch_alter_table('agents', schema=None) as batch_op:
        for col in ('created_at', 'config', 'name'):
            batch_op.drop_column(col)

    with op.batch_alter_table('backtest_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backtest_runs_task_type_id'))
        batch_op.drop_index(batch_op.f('ix_backtest_runs_agent_id'))
    op.drop_table('backtest_runs')
