"""manager settings

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 17:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('apprenticeships', schema=None) as batch_op:
        batch_op.add_column(sa.Column('settings', JSON, nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('apprenticeships', schema=None) as batch_op:
        batch_op.drop_column('settings')
