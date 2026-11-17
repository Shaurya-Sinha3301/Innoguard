from collections.abc import Iterator

from sqlalchemy.orm import Session

from invoiceguard.db.session import SessionLocal


def get_session() -> Iterator[Session]:
    """One transaction per request: commit on success, roll back on any error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
