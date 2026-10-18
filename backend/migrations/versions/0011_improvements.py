"""improvements: changes to rules and routines, tested on past cases (blast radius) before they go live

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'improvements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('task_type_id', sa.String(36), sa.ForeignKey('task_types.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('rule_id', sa.String(36), sa.ForeignKey('rules.id'), nullable=True),
        sa.Column('candidate', JSON, nullable=False),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('source', sa.String(20), nullable=False, server_default='mentor'),
        sa.Column('signal', sa.String(40), nullable=False, server_default='taught'),
        sa.Column('status', sa.String(20), nullable=False, server_default='testing'),
        sa.Column('blast', JSON, nullable=False),
        sa.Column('proposed_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decided_by', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('repredict_run_id', sa.String(36), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('improvements')
