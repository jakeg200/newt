"""trajectories: how Newt reached each answer (tool steps), and the checks on them

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18 21:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trajectory', JSON, nullable=True))
    with op.batch_alter_table('comparisons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('steps', JSON, nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('comparisons', schema=None) as batch_op:
        batch_op.drop_column('steps')
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_column('trajectory')
