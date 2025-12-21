"""redesign_goals

Revision ID: d1e2f3g4h5i6
Revises: bfc36cb480ac
Create Date: 2025-12-21 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3g4h5i6'
down_revision: Union[str, None] = 'bfc36cb480ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop old tables (Data Loss accepted by user)
    # We use raw SQL with IF EXISTS to handle cases where they were already manually dropped
    op.execute("DROP TABLE IF EXISTS user_goals CASCADE")
    op.execute("DROP TABLE IF EXISTS ref_goals CASCADE")
    
    # 2. Drop the Enum type
    op.execute("DROP TYPE IF EXISTS goaltype CASCADE")

    # 3. Recreate user_goals with new schema
    op.create_table('user_goals',
        sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="personal"),
        sa.Column('icon', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="Target"),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="in_progress"),
        sa.Column('progress', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('target_amount', sa.Numeric(), nullable=True, server_default="0"),
        sa.Column('current_amount', sa.Numeric(), nullable=True, server_default="0"),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # We generally don't support downgrade for destructive dev changes like this easily
    # But strictly speaking we would have to recreate ref_goals etc.
    pass
