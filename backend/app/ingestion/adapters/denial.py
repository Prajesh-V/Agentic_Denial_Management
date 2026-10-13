from sqlalchemy.orm import Session

from backend.app.db.models.billing import Claim, DenialEvent
from backend.app.db.models.identity import Patient
from backend.app.ingestion.adapters.base import BaseSourceAdapter
from backend.app.ingestion.normalizer import SafeTextNormalizer
from backend.app.ingestion.schemas import (
    CanonicalDocument,
    CanonicalSourceType,
    DocumentSection,
    EvidentiaryRole,
)


class DenialContextAdapter(BaseSourceAdapter):
    """Adapter for DenialEvents providing adjudication context (not clinical evidence)."""

    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        query = (
            session.query(DenialEvent, Claim, Patient)
            .join(Claim, DenialEvent.claim_id == Claim.id)
            .join(Patient, Claim.patient_id == Patient.id)
        )
        if dataset_build_id:
            query = query.filter(Patient.dataset_build_id == dataset_build_id)

        records = query.all()
        documents: list[CanonicalDocument] = []

        for den, clm, pat in records:
            if not den.denial_reason_text:
                continue

            raw_text = (
                f"Claim Denial Adjudication Record (Context Only):\n"
                f"Claim ID: {clm.id}\n"
                f"Denial Category: {den.denial_category}\n"
                f"CARC Code: {den.carc_code} | RARC Code: {den.rarc_code}\n"
                f"Denied Amount: ${den.denied_amount}\n"
                f"Denial Date: {den.denial_date} | Appeal Deadline: {den.appeal_deadline}\n"
                f"Adjudication Reason:\n{den.denial_reason_text}"
            )
            normalized_text, content_hash = SafeTextNormalizer.normalize(raw_text)

            section = DocumentSection(
                title="DENIAL_ADJUDICATION_REASON",
                content=normalized_text,
                start_char=0,
                end_char=len(normalized_text),
            )

            documents.append(
                CanonicalDocument(
                    source_id=den.id,
                    source_type=CanonicalSourceType.DENIAL_EVENT,
                    evidentiary_role=EvidentiaryRole.DENIAL_CONTEXT,  # Explicit denial context role
                    patient_id=pat.id,
                    claim_id=clm.id,
                    denial_event_id=den.id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=den.denial_date,
                    raw_content=raw_text,
                    normalized_content=normalized_text,
                    content_hash=content_hash,
                    sections=[section],
                    metadata={
                        "denial_category": den.denial_category,
                        "carc_code": den.carc_code,
                        "rarc_code": den.rarc_code,
                        "denied_amount": float(den.denied_amount) if den.denied_amount else 0.0,
                    },
                    is_synthetic=True,
                )
            )

        return documents
