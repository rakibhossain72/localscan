"""convert_large_integers_to_strings

Revision ID: d051d45f043f
Revises: eb87305453a8
Create Date: 2026-01-31 18:04:40.927777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd051d45f043f'
down_revision: Union[str, Sequence[str], None] = 'eb87305453a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support ALTER COLUMN directly, so we use batch operations
    # which recreate the table with the new schema
    
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('value',
                   existing_type=sa.BIGINT(),
                   type_=sa.String(length=78),
                   existing_nullable=False)
        batch_op.alter_column('gas_price',
                   existing_type=sa.BIGINT(),
                   type_=sa.String(length=78),
                   existing_nullable=False)
    
    with op.batch_alter_table('tokens', schema=None) as batch_op:
        batch_op.alter_column('total_supply',
                   existing_type=sa.BIGINT(),
                   type_=sa.String(length=78),
                   existing_nullable=True)
    
    with op.batch_alter_table('token_transfers', schema=None) as batch_op:
        batch_op.alter_column('amount',
                   existing_type=sa.BIGINT(),
                   type_=sa.String(length=78),
                   existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite doesn't support ALTER COLUMN directly, so we use batch operations
    
    with op.batch_alter_table('token_transfers', schema=None) as batch_op:
        batch_op.alter_column('amount',
                   existing_type=sa.String(length=78),
                   type_=sa.BIGINT(),
                   existing_nullable=False)
    
    with op.batch_alter_table('tokens', schema=None) as batch_op:
        batch_op.alter_column('total_supply',
                   existing_type=sa.String(length=78),
                   type_=sa.BIGINT(),
                   existing_nullable=True)
    
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('gas_price',
                   existing_type=sa.String(length=78),
                   type_=sa.BIGINT(),
                   existing_nullable=False)
        batch_op.alter_column('value',
                   existing_type=sa.String(length=78),
                   type_=sa.BIGINT(),
                   existing_nullable=False)
