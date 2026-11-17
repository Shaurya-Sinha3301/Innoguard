import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import DBAPIError, IntegrityError

from invoiceguard.db.models import Base


def test_migrations_match_the_models(engine):
    """No drift: applying every migration yields exactly the schema the models describe."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def _insert_invoice(conn) -> str:
    return conn.execute(
        sa.text(
            """
            INSERT INTO invoices
              (invoice_number, number_norm, vendor_id, currency, subtotal, tax, total, file_hash)
            VALUES ('INV-1', 'INV1', 'V001', 'INR', 100, 5, 105, 'hash-1')
            RETURNING id
            """
        )
    ).scalar_one()


def test_invoice_defaults(engine):
    with engine.connect() as conn:
        invoice_id = _insert_invoice(conn)
        row = conn.execute(
            sa.text("SELECT status, version, invoice_type FROM invoices WHERE id = :i"),
            {"i": invoice_id},
        ).one()
        conn.rollback()  # leave the table clean for the other tests
    assert tuple(row) == ("RECEIVED", 1, "INVOICE")


def test_audit_events_can_be_appended(engine):
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO audit_events (event_type, actor) VALUES ('invoice.received', 'system')"
            )
        )
        count = conn.execute(sa.text("SELECT count(*) FROM audit_events")).scalar_one()
    assert count >= 1


def test_audit_events_reject_update_delete_and_truncate(engine):
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO audit_events (event_type, actor) VALUES ('x', 'system')")
        )

    for statement in (
        "UPDATE audit_events SET actor = 'someone-else'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ):
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(statement))
        except DBAPIError as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError(f"expected the database to reject: {statement}")


def test_posting_idempotency_key_is_unique(engine):
    with engine.begin() as conn:
        invoice_id = _insert_invoice(conn)
        insert = sa.text(
            "INSERT INTO postings (idempotency_key, invoice_id, invoice_version, status) "
            "VALUES ('key-1', :i, 1, 'POSTED')"
        )
        conn.execute(insert, {"i": invoice_id})

    try:
        with engine.begin() as conn:
            conn.execute(insert, {"i": invoice_id})
    except IntegrityError:
        pass
    else:
        raise AssertionError("duplicate idempotency key was accepted")
