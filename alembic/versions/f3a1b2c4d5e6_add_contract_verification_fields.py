"""add_contract_verification_fields

Revision ID: f3a1b2c4d5e6
Revises: 5e6adf8b3b02
Create Date: 2026-05-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1b2c4d5e6'
down_revision: Union[str, Sequence[str], None] = '5e6adf8b3b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contracts', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('contracts', sa.Column('source_code', sa.Text(), nullable=True))
    op.add_column('contracts', sa.Column('abi_json', sa.Text(), nullable=True))
    op.add_column('contracts', sa.Column('compiler_version', sa.String(32), nullable=True))
    op.add_column('contracts', sa.Column('optimization_enabled', sa.Boolean(), nullable=True))
    op.add_column('contracts', sa.Column('optimization_runs', sa.Integer(), nullable=True))
    op.add_column('contracts', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('contracts', 'verified_at')
    op.drop_column('contracts', 'optimization_runs')
    op.drop_column('contracts', 'optimization_enabled')
    op.drop_column('contracts', 'compiler_version')
    op.drop_column('contracts', 'abi_json')
    op.drop_column('contracts', 'source_code')
    op.drop_column('contracts', 'is_verified')
