"""stored files

Revision ID: 3b9e1c7d2a40
Revises: 07f875ffbd89
Create Date: 2026-10-29 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b9e1c7d2a40'
down_revision: Union[str, Sequence[str], None] = '07f875ffbd89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stored_files',
    sa.Column('path', sa.String(length=255), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('path')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('stored_files')
