import re

from sqlalchemy.orm import Session

from backend.app.db.models.clinical import (
    ClinicalDocument,
    Condition,
    DiagnosticReport,
    Observation,
    Procedure,
)
from backend.app.db.models.identity import Patient
from backend.app.ingestion.adapters.base import BaseSourceAdapter
from backend.app.ingestion.normalizer import SafeTextNormalizer
from backend.app.ingestion.schemas import (
    CanonicalDocument,
    CanonicalSourceType,
    DocumentSection,
    EvidentiaryRole,
)


class ClinicalDocumentAdapter(BaseSourceAdapter):
    """Adapter for narrative ClinicalDocuments."""

    SECTION_HEADER_RE = re.compile(r"^([A-Z\s\-/]{3,40}):", re.MULTILINE)

    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        query = session.query(ClinicalDocument, Patient).join(Patient, ClinicalDocument.patient_id == Patient.id)
        if dataset_build_id:
            query = query.filter(Patient.dataset_build_id == dataset_build_id)

        records = query.all()
        documents: list[CanonicalDocument] = []

        for doc, pat in records:
            if not doc.body_text:
                continue

            normalized_text, content_hash = SafeTextNormalizer.normalize(doc.body_text)

            # Extract sections by header regex
            sections: list[DocumentSection] = []
            matches = list(self.SECTION_HEADER_RE.finditer(normalized_text))

            if matches:
                if matches[0].start() > 0:
                    preamble = normalized_text[: matches[0].start()].strip()
                    if preamble:
                        sections.append(
                            DocumentSection(
                                title="PREAMBLE",
                                content=preamble,
                                start_char=0,
                                end_char=matches[0].start(),
                            )
                        )

                for i, match in enumerate(matches):
                    title = match.group(1).strip()
                    start_pos = match.start()
                    end_pos = matches[i + 1].start() if (i + 1 < len(matches)) else len(normalized_text)
                    sec_text = normalized_text[start_pos:end_pos].strip()
                    if sec_text:
                        sections.append(
                            DocumentSection(
                                title=title,
                                content=sec_text,
                                start_char=start_pos,
                                end_char=end_pos,
                            )
                        )
            else:
                sections.append(
                    DocumentSection(
                        title=doc.document_type or "CLINICAL_NOTE",
                        content=normalized_text,
                        start_char=0,
                        end_char=len(normalized_text),
                    )
                )

            effective_dt = doc.authored_at.date() if doc.authored_at else None

            documents.append(
                CanonicalDocument(
                    source_id=doc.id,
                    source_type=CanonicalSourceType.CLINICAL_DOCUMENT,
                    evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
                    patient_id=pat.id,
                    encounter_id=doc.encounter_id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=effective_dt,
                    raw_content=doc.body_text,
                    normalized_content=normalized_text,
                    content_hash=content_hash,
                    sections=sections,
                    metadata={
                        "title": doc.title,
                        "document_type": doc.document_type,
                        "practitioner_id": str(doc.practitioner_id) if doc.practitioner_id else None,
                    },
                    is_synthetic=True,
                )
            )

        return documents


class DiagnosticReportAdapter(BaseSourceAdapter):
    """Adapter for DiagnosticReports and conclusions."""

    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        query = session.query(DiagnosticReport, Patient).join(Patient, DiagnosticReport.patient_id == Patient.id)
        if dataset_build_id:
            query = query.filter(Patient.dataset_build_id == dataset_build_id)

        records = query.all()
        documents: list[CanonicalDocument] = []

        for rep, pat in records:
            if not rep.conclusion:
                continue

            raw_text = (
                f"Diagnostic Report: {rep.display or 'Diagnostic Finding'} (Code: {rep.code})\n"
                f"Status: {rep.status}\n"
                f"Conclusion: {rep.conclusion}"
            )
            normalized_text, content_hash = SafeTextNormalizer.normalize(raw_text)

            section = DocumentSection(
                title="DIAGNOSTIC_CONCLUSION",
                content=normalized_text,
                start_char=0,
                end_char=len(normalized_text),
            )

            effective_dt = rep.effective_time.date() if rep.effective_time else None

            documents.append(
                CanonicalDocument(
                    source_id=rep.id,
                    source_type=CanonicalSourceType.DIAGNOSTIC_REPORT,
                    evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
                    patient_id=pat.id,
                    encounter_id=rep.encounter_id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=effective_dt,
                    raw_content=raw_text,
                    normalized_content=normalized_text,
                    content_hash=content_hash,
                    sections=[section],
                    metadata={
                        "code": rep.code,
                        "display": rep.display,
                        "status": rep.status,
                    },
                    is_synthetic=True,
                )
            )

        return documents


class StructuredClinicalAdapter(BaseSourceAdapter):
    """Adapter for structured Observation, Condition, and Procedure records."""

    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        documents: list[CanonicalDocument] = []

        # 1. Observations
        obs_query = session.query(Observation, Patient).join(Patient, Observation.patient_id == Patient.id)
        if dataset_build_id:
            obs_query = obs_query.filter(Patient.dataset_build_id == dataset_build_id)

        for obs, pat in obs_query.all():
            val_display = (
                f"{obs.value_numeric} {obs.value_unit or ''}".strip()
                if obs.value_numeric is not None
                else (obs.value_string or "Normal")
            )
            ref_str = (
                f" (Ref: {obs.reference_range_low} - {obs.reference_range_high})"
                if (obs.reference_range_low is not None and obs.reference_range_high is not None)
                else ""
            )
            raw_text = (
                f"Clinical Observation: {obs.display or 'Lab/Vital'} (Code: {obs.code_system} {obs.code})\n"
                f"Value: {val_display}{ref_str}\n"
                f"Effective: {obs.effective_time}"
            )
            norm_text, chash = SafeTextNormalizer.normalize(raw_text)
            effective_dt = obs.effective_time.date() if obs.effective_time else None

            documents.append(
                CanonicalDocument(
                    source_id=obs.id,
                    source_type=CanonicalSourceType.OBSERVATION,
                    evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
                    patient_id=pat.id,
                    encounter_id=obs.encounter_id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=effective_dt,
                    raw_content=raw_text,
                    normalized_content=norm_text,
                    content_hash=chash,
                    sections=[DocumentSection(title="OBSERVATION", content=norm_text, start_char=0, end_char=len(norm_text))],
                    metadata={"code": obs.code, "code_system": obs.code_system, "display": obs.display},
                    is_synthetic=True,
                )
            )

        # 2. Conditions
        cond_query = session.query(Condition, Patient).join(Patient, Condition.patient_id == Patient.id)
        if dataset_build_id:
            cond_query = cond_query.filter(Patient.dataset_build_id == dataset_build_id)

        for cond, pat in cond_query.all():
            raw_text = (
                f"Clinical Condition: {cond.display or 'Condition'} (Code: {cond.code_system} {cond.code})\n"
                f"Clinical Status: {cond.clinical_status}\n"
                f"Onset: {cond.onset_time}"
            )
            norm_text, chash = SafeTextNormalizer.normalize(raw_text)
            effective_dt = cond.onset_time.date() if cond.onset_time else None

            documents.append(
                CanonicalDocument(
                    source_id=cond.id,
                    source_type=CanonicalSourceType.CONDITION,
                    evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
                    patient_id=pat.id,
                    encounter_id=cond.encounter_id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=effective_dt,
                    raw_content=raw_text,
                    normalized_content=norm_text,
                    content_hash=chash,
                    sections=[DocumentSection(title="CONDITION", content=norm_text, start_char=0, end_char=len(norm_text))],
                    metadata={"code": cond.code, "code_system": cond.code_system, "display": cond.display},
                    is_synthetic=True,
                )
            )

        # 3. Procedures
        proc_query = session.query(Procedure, Patient).join(Patient, Procedure.patient_id == Patient.id)
        if dataset_build_id:
            proc_query = proc_query.filter(Patient.dataset_build_id == dataset_build_id)

        for proc, pat in proc_query.all():
            raw_text = (
                f"Clinical Procedure: {proc.display or 'Procedure'} (Code: {proc.code_system} {proc.code})\n"
                f"Status: {proc.status}\n"
                f"Performed: {proc.performed_time}"
            )
            norm_text, chash = SafeTextNormalizer.normalize(raw_text)
            effective_dt = proc.performed_time.date() if proc.performed_time else None

            documents.append(
                CanonicalDocument(
                    source_id=proc.id,
                    source_type=CanonicalSourceType.PROCEDURE,
                    evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
                    patient_id=pat.id,
                    encounter_id=proc.encounter_id,
                    dataset_build_id=pat.dataset_build_id,
                    effective_date=effective_dt,
                    raw_content=raw_text,
                    normalized_content=norm_text,
                    content_hash=chash,
                    sections=[DocumentSection(title="PROCEDURE", content=norm_text, start_char=0, end_char=len(norm_text))],
                    metadata={"code": proc.code, "code_system": proc.code_system, "display": proc.display},
                    is_synthetic=True,
                )
            )

        return documents
