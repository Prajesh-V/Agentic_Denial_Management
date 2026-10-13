from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from backend.app.ingestion.schemas import CanonicalDocument


class BaseSourceAdapter(ABC):
    """Abstract base class for all canonical source adapters."""

    @abstractmethod
    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        """Extracts canonical records and produces normalized CanonicalDocument objects."""
