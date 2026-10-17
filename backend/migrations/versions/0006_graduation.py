"""graduation

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 16:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    op.create_table('drift_checks',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('task_type_id', sa.String(length=36), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('drifted', sa.Boolean(), nullable=False),
    sa.Column('result', JSON, nullable=False),
    sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('drift_checks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_drift_checks_task_type_id'), ['task_type_id'], unique=False)

    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prediction_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('mode', sa.String(length=20), nullable=False, server_default='supervised'))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
        batch_op.add_column(sa.Column('decided_by', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch_op.create_index(batch_op.f('ix_action_log_prediction_id'), ['prediction_id'], unique=False)
        batch_op.create_foreign_key('fk_action_log_prediction', 'predictions', ['prediction_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_action_log_decided_by', 'users', ['decided_by'], ['id'])

    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_type_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('prediction_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('mentor_payload', JSON, nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_audits_task_type_id'), ['task_type_id'], unique=False)
        batch_op.create_foreign_key('fk_audits_prediction', 'predictions', ['prediction_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_audits_task_type', 'task_types', ['task_type_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('task_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('calibration', JSON, nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('task_types', schema=None) as batch_op:
        batch_op.drop_column('calibration')

    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audits_task_type', type_='foreignkey')
        batch_op.drop_constraint('fk_audits_prediction', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_audits_task_type_id'))
        for col in ('completed_at', 'mentor_payload', 'prediction_id', 'task_type_id'):
            batch_op.drop_column(col)

    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.drop_constraint('fk_action_log_decided_by', type_='foreignkey')
        batch_op.drop_constraint('fk_action_log_prediction', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_action_log_prediction_id'))
        for col in ('created_at', 'decided_by', 'status', 'mode', 'prediction_id'):
            batch_op.drop_column(col)

    with op.batch_alter_table('drift_checks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_drift_checks_task_type_id'))
    op.drop_table('drift_checks')
