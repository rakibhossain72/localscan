"""update_address_balance_type

Revision ID: 901dbd3fc1ed
Revises: d051d45f043f
Create Date: 2026-02-02 00:03:06.003397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '901dbd3fc1ed'
down_revision: Union[str, Sequence[str], None] = 'd051d45f043f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('addresses', schema=None) as batch_op:
        batch_op.alter_column('balance_cached',
                   existing_type=sa.BIGINT(),
                   type_=sa.String(length=78),
                   existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('addresses', schema=None) as batch_op:
        batch_op.alter_column('balance_cached',
                   existing_type=sa.String(length=78),
                   type_=sa.BIGINT(),
                   existing_nullable=True)
