"""channels: Newt's messages delivered in Slack, Teams or email, and the org-level chat installs

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19 14:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('external_ref', sa.String(200), nullable=True))
        batch_op.create_index('ix_messages_external_ref', ['external_ref'])
    op.create_table(
        'chat_installs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('provider', sa.String(10), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False, index=True),
        sa.Column('encrypted_token', sa.Text(), nullable=True),
        sa.Column('config', JSON, nullable=False),
        sa.Column('installed_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('chat_installs')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('ix_messages_external_ref')
        batch_op.drop_column('external_ref')
        batch_op.drop_column('channel')
