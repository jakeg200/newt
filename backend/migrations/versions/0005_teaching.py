"""teaching

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 15:10:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('apprenticeships', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rules_version', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('comparisons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('attribution', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('excluded', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prediction_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('reply_ok', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_lessons_prediction_id'), ['prediction_id'], unique=False)
        batch_op.create_foreign_key('fk_lessons_created_by', 'users', ['created_by'], ['id'])
        batch_op.create_foreign_key('fk_lessons_prediction', 'predictions', ['prediction_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('rules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('decision', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='inferred'))
        batch_op.add_column(sa.Column('evidence_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('stats', JSON, nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('created_by', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        batch_op.create_foreign_key('fk_rules_created_by', 'users', ['created_by'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('rules', schema=None) as batch_op:
        batch_op.drop_constraint('fk_rules_created_by', type_='foreignkey')
        for col in ('updated_at', 'created_at', 'created_by', 'stats', 'evidence_until', 'source', 'decision'):
            batch_op.drop_column(col)

    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.drop_constraint('fk_lessons_prediction', type_='foreignkey')
        batch_op.drop_constraint('fk_lessons_created_by', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_lessons_prediction_id'))
        for col in ('created_by', 'reply_ok', 'prediction_id'):
            batch_op.drop_column(col)

    with op.batch_alter_table('comparisons', schema=None) as batch_op:
        batch_op.drop_column('excluded')
        batch_op.drop_column('attribution')

    with op.batch_alter_table('apprenticeships', schema=None) as batch_op:
        batch_op.drop_column('rules_version')
