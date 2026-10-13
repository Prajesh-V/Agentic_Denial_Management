import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal

T = TypeVar("T")


@contextmanager
def transaction_scope(session: Session | None = None) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations with auto-commit/rollback."""
    if session is not None:
        yield session
    else:
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def get_patient_scoped_record[T](
    session: Session,
    model: type[T],
    record_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> T | None:
    """Safely retrieves a record ensuring it belongs strictly to the target patient."""
    stmt = select(model).where(
        model.id == record_id,
        model.patient_id == patient_id,
    )
    return session.execute(stmt).scalar_one_or_none()


def get_organization_scoped_record[T](
    session: Session,
    model: type[T],
    record_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> T | None:
    """Safely retrieves a record ensuring it belongs strictly to the target organization (tenant)."""
    stmt = select(model).where(
        model.id == record_id,
        model.organization_id == organization_id,
    )
    return session.execute(stmt).scalar_one_or_none()
