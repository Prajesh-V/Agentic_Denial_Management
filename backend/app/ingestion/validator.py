import hashlib
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.models.billing import DenialEvent, PayerPolicyVersion
from backend.app.db.models.clinical import (
    ClinicalDocument,
)
from backend.app.db.models.investigation import EvidenceChunk


class EvidenceCorpusValidator:
    """Rigorous validator for evidence corpus integrity and scoping."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def validate_corpus(self, dataset_build_id: str | None = None) -> dict[str, Any]:
        """Runs comprehensive validation checks across all active evidence chunks."""
        query = self.session.query(EvidenceChunk).filter(EvidenceChunk.is_active == True)
        if dataset_build_id:
            # Check chunks associated with this build or shared policies
            query = query.filter(
                (EvidenceChunk.dataset_build_id == dataset_build_id)
                | (EvidenceChunk.dataset_build_id.is_(None))
            )

        chunks = query.all()
        report: dict[str, Any] = {
            "total_chunks_inspected": len(chunks),
            "passed": True,
            "violations": [],
            "counts_by_role": {},
            "counts_by_source_type": {},
        }

        for chunk in chunks:
            role = chunk.evidentiary_role
            stype = chunk.source_resource_type
            report["counts_by_role"][role] = report["counts_by_role"].get(role, 0) + 1
            report["counts_by_source_type"][stype] = report["counts_by_source_type"].get(stype, 0) + 1

            # 1. Content Hash Verification
            recomputed_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            if recomputed_hash != chunk.text_hash:
                report["passed"] = False
                report["violations"].append(
                    f"Chunk {chunk.id}: text_hash mismatch (expected {recomputed_hash}, got {chunk.text_hash})"
                )

            # 2. Character Count Verification
            if len(chunk.content) != chunk.char_count:
                report["passed"] = False
                report["violations"].append(
                    f"Chunk {chunk.id}: char_count mismatch (actual {len(chunk.content)}, recorded {chunk.char_count})"
                )

            # 3. Token Count Sanity
            if chunk.token_count <= 0:
                report["passed"] = False
                report["violations"].append(f"Chunk {chunk.id}: invalid token_count {chunk.token_count}")

            # 4. Scope and Role Consistency
            if role == "PAYER_POLICY":
                if chunk.patient_id is not None:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: PAYER_POLICY chunk has non-null patient_id {chunk.patient_id}"
                    )
                if chunk.payer_id is None or chunk.payer_policy_version_id is None:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: PAYER_POLICY chunk missing payer_id or payer_policy_version_id"
                    )
                if stype != "PayerPolicyVersion":
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: PAYER_POLICY chunk has invalid source_resource_type {stype}"
                    )

            elif role == "CLINICAL_SUPPORTING":
                if chunk.patient_id is None:
                    report["passed"] = False
                    report["violations"].append(f"Chunk {chunk.id}: CLINICAL_SUPPORTING chunk has null patient_id")
                if chunk.payer_id is not None or chunk.payer_policy_version_id is not None:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: CLINICAL_SUPPORTING chunk contaminated with payer_id or policy version"
                    )
                if chunk.denial_event_id is not None:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: CLINICAL_SUPPORTING chunk contaminated with denial_event_id"
                    )

            elif role == "DENIAL_CONTEXT":
                if chunk.patient_id is None or chunk.claim_id is None or chunk.denial_event_id is None:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: DENIAL_CONTEXT chunk missing patient_id, claim_id, or denial_event_id"
                    )
                if stype != "DenialEvent":
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: DENIAL_CONTEXT chunk has invalid source_resource_type {stype}"
                    )

            # 5. Relational Provenance Check against canonical records
            if chunk.clinical_document_id:
                doc = self.session.query(ClinicalDocument).filter_by(id=chunk.clinical_document_id).first()
                if not doc:
                    report["passed"] = False
                    report["violations"].append(f"Chunk {chunk.id}: referenced ClinicalDocument not found")
                elif doc.patient_id != chunk.patient_id:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: patient_id {chunk.patient_id} does not match ClinicalDocument patient {doc.patient_id}"
                    )

            if chunk.payer_policy_version_id:
                pol = self.session.query(PayerPolicyVersion).filter_by(id=chunk.payer_policy_version_id).first()
                if not pol:
                    report["passed"] = False
                    report["violations"].append(f"Chunk {chunk.id}: referenced PayerPolicyVersion not found")
                elif pol.payer_id != chunk.payer_id:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: payer_id {chunk.payer_id} does not match policy payer {pol.payer_id}"
                    )

            if chunk.denial_event_id:
                den = self.session.query(DenialEvent).filter_by(id=chunk.denial_event_id).first()
                if not den:
                    report["passed"] = False
                    report["violations"].append(f"Chunk {chunk.id}: referenced DenialEvent not found")
                elif den.claim_id != chunk.claim_id:
                    report["passed"] = False
                    report["violations"].append(
                        f"Chunk {chunk.id}: claim_id {chunk.claim_id} does not match DenialEvent claim {den.claim_id}"
                    )

        report["violation_count"] = len(report["violations"])
        return report
