import re

from sqlalchemy.orm import Session

from backend.app.db.models.billing import PayerPolicyVersion
from backend.app.ingestion.adapters.base import BaseSourceAdapter
from backend.app.ingestion.normalizer import SafeTextNormalizer
from backend.app.ingestion.schemas import (
    CanonicalDocument,
    CanonicalSourceType,
    DocumentSection,
    EvidentiaryRole,
)


class PayerPolicyAdapter(BaseSourceAdapter):
    """Adapter for shared PayerPolicyVersions (payer-scoped, zero patient linkage)."""

    SECTION_HEADER_RE = re.compile(r"^(\d+\.\s+[A-Z\s\-/]{3,50}:)", re.MULTILINE)

    def extract(self, session: Session, dataset_build_id: str | None = None) -> list[CanonicalDocument]:
        # Payer policies are shared across the system
        policies = session.query(PayerPolicyVersion).all()
        documents: list[CanonicalDocument] = []

        for pol in policies:
            if not pol.full_text:
                continue

            normalized_text, content_hash = SafeTextNormalizer.normalize(pol.full_text)

            sections: list[DocumentSection] = []
            matches = list(self.SECTION_HEADER_RE.finditer(normalized_text))

            if matches:
                if matches[0].start() > 0:
                    preamble = normalized_text[: matches[0].start()].strip()
                    if preamble:
                        sections.append(
                            DocumentSection(
                                title="POLICY_HEADER",
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
                        title="POLICY_TEXT",
                        content=normalized_text,
                        start_char=0,
                        end_char=len(normalized_text),
                    )
                )

            # If structured requirements exist, add structured criteria section
            if pol.requirements_spec and isinstance(pol.requirements_spec, dict):
                criteria_list = pol.requirements_spec.get("criteria", [])
                if criteria_list:
                    crit_lines = [f"- [{c.get('rule_id')}]: {c.get('description')}" for c in criteria_list]
                    crit_text = "STRUCTURED POLICY CRITERIA REQUIREMENTS:\n" + "\n".join(crit_lines)
                    crit_start = len(normalized_text)
                    crit_norm, _ = SafeTextNormalizer.normalize(crit_text)
                    sections.append(
                        DocumentSection(
                            title="STRUCTURED_CRITERIA",
                            content=crit_norm,
                            start_char=crit_start,
                            end_char=crit_start + len(crit_norm),
                        )
                    )

            documents.append(
                CanonicalDocument(
                    source_id=pol.id,
                    source_type=CanonicalSourceType.PAYER_POLICY_VERSION,
                    evidentiary_role=EvidentiaryRole.PAYER_POLICY,
                    patient_id=None,  # STRICT: Payer policies MUST NEVER have patient_id!
                    payer_id=pol.payer_id,
                    payer_policy_version_id=pol.id,
                    dataset_build_id=None,  # Shared across builds
                    effective_date=pol.effective_start,
                    raw_content=pol.full_text,
                    normalized_content=normalized_text,
                    content_hash=content_hash,
                    sections=sections,
                    metadata={
                        "policy_number": pol.policy_number,
                        "title": pol.title,
                        "version": pol.version,
                        "payer_id": str(pol.payer_id),
                        "requirements_spec": pol.requirements_spec,
                    },
                    is_synthetic=True,
                )
            )

        return documents
