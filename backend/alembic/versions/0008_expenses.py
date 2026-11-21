"""expenses pack reference data: employees, spending categories, card statement lines

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21 18:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=False),
        sa.PrimaryKeyConstraint("employee_id"),
    )
    op.create_table(
        "expense_categories",
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("cap", sa.Numeric(18, 4), nullable=False),
        sa.Column("blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("category"),
    )
    op.create_table(
        "card_transactions",
        sa.Column("txn_id", sa.Text(), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("txn_id"),
    )
    op.create_index("ix_card_transactions_card", "card_transactions", ["card_last4"])


def downgrade() -> None:
    op.drop_index("ix_card_transactions_card", table_name="card_transactions")
    op.drop_table("card_transactions")
    op.drop_table("expense_categories")
    op.drop_table("employees")
