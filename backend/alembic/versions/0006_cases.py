"""invoices become cases: one table for every pack's unit of work

Renames only (metadata changes in Postgres, no data is rewritten), plus two columns:
`pack_id` says which workflow owns a case and `data` holds a pack's own fields. Existing
rows belong to the invoices pack. Audit events keep their original `invoice.*` names, since
the log is append-only; readers accept both families.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21 14:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# (table, old column, new column)
COLUMN_RENAMES = [
    ("documents", "invoice_id", "case_id"),
    ("case_lines", "invoice_id", "case_id"),
    ("extraction_fields", "invoice_id", "case_id"),
    ("approvals", "invoice_id", "case_id"),
    ("approvals", "invoice_version", "case_version"),
    ("postings", "invoice_id", "case_id"),
    ("postings", "invoice_version", "case_version"),
    ("failed_jobs", "invoice_id", "case_id"),
    ("llm_calls", "invoice_id", "case_id"),
    ("audit_events", "invoice_id", "case_id"),
]

INDEX_RENAMES = [
    ("ix_invoices_file_hash", "ix_cases_file_hash"),
    ("ix_invoices_vendor_number_norm", "ix_cases_vendor_number_norm"),
    ("ix_invoices_status", "ix_cases_status"),
    ("ix_audit_events_invoice", "ix_audit_events_case"),
]


def upgrade() -> None:
    op.rename_table("invoices", "cases")
    op.rename_table("invoice_lines", "case_lines")
    for table, old, new in COLUMN_RENAMES:
        op.alter_column(table, old, new_column_name=new)
    for old, new in INDEX_RENAMES:
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    op.add_column("cases", sa.Column("pack_id", sa.Text(), server_default="invoices", nullable=False))
    op.add_column(
        "cases",
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("cases", "data")
    op.drop_column("cases", "pack_id")
    for old, new in INDEX_RENAMES:
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    for table, old, new in reversed(COLUMN_RENAMES):
        op.alter_column(table, new, new_column_name=old)
    op.rename_table("case_lines", "invoice_lines")
    op.rename_table("cases", "invoices")
