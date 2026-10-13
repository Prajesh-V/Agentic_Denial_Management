"""Authoritative scope filter and relational access control validator for evidence retrieval."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Claim, Coverage, EvidenceChunk, PayerPlan, PayerPolicyVersion
from backend.app.ingestion.schemas import EvidentiaryRole
from backend.app.retrieval.schemas import RetrievalScopeContext


class ScopeValidationError(Exception):
    """Raised when an authorization or scope violation occurs."""


class RetrievalScopeFilter:
    """Enforces patient, tenant, claim, payer, and temporal validity boundaries at the database level."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_context(self, context: RetrievalScopeContext) -> RetrievalScopeContext:
        """Enrich scope context with claim payer and service date if omitted."""
        if not context.claim_id or not context.patient_id:
            raise ScopeValidationError("Investigation retrieval requires both claim_id and patient_id.")

        payer_id = context.payer_id
        service_date = context.service_date

        if payer_id is None or service_date is None:
            claim = self.session.execute(
                select(Claim).where(Claim.id == context.claim_id)
            ).scalars().first()

            if claim is not None:
                if claim.patient_id != context.patient_id:
                    raise ScopeValidationError(
                        f"Scope contradiction: Claim {context.claim_id} belongs to patient {claim.patient_id}, "
                        f"not requested patient {context.patient_id}."
                    )
                if service_date is None:
                    service_date = claim.service_start_date

                if payer_id is None and claim.coverage_id:
                    cov_plan = self.session.execute(
                        select(PayerPlan.payer_id)
                        .select_from(Coverage)
                        .join(PayerPlan, Coverage.payer_plan_id == PayerPlan.id)
                        .where(Coverage.id == claim.coverage_id)
                    ).first()
                    if cov_plan:
                        payer_id = cov_plan[0]

        return RetrievalScopeContext(
            claim_id=context.claim_id,
            patient_id=context.patient_id,
            tenant_id=context.tenant_id,
            payer_id=payer_id,
            service_date=service_date,
            allowed_roles=context.allowed_roles,
        )

    def validate_chunk_scope(self, chunk: EvidenceChunk, scope: RetrievalScopeContext) -> tuple[bool, str | None]:
        """Validate an individual chunk against the authorized investigation scope.

        Returns:
            (is_valid, rejection_reason)
        """
        if not chunk.is_active:
            return False, "Chunk is inactive or superseded."

        role = EvidentiaryRole(chunk.evidentiary_role)

        # Evidentiary role allowlist check
        if scope.allowed_roles and role not in scope.allowed_roles:
            return False, f"Evidentiary role {role.value} not in allowed roles."

        # 1. Clinical Supporting Evidence: Strict patient isolation
        if role == EvidentiaryRole.CLINICAL_SUPPORTING:
            if chunk.patient_id is None:
                return False, "Clinical chunk lacks mandatory patient attribution."
            if chunk.patient_id != scope.patient_id:
                return False, f"Patient mismatch: chunk patient {chunk.patient_id} != authorized {scope.patient_id}."
            return True, None

        # 2. Payer Policy Evidence: Shared document, strictly payer-scoped, never patient-owned
        elif role == EvidentiaryRole.PAYER_POLICY:
            if chunk.patient_id is not None:
                return False, f"Policy chunk illegally attributed to patient {chunk.patient_id}."
            if scope.payer_id is not None and chunk.payer_id != scope.payer_id:
                return False, f"Payer mismatch: chunk payer {chunk.payer_id} != claim payer {scope.payer_id}."

            # Temporal validity check against claim service date
            if scope.service_date is not None and chunk.payer_policy_version_id is not None:
                policy_ver = self.session.execute(
                    select(PayerPolicyVersion).where(PayerPolicyVersion.id == chunk.payer_policy_version_id)
                ).scalars().first()
                if policy_ver is not None:
                    svc_dt = scope.service_date
                    if isinstance(svc_dt, datetime):
                        svc_dt = svc_dt.date()
                    if policy_ver.effective_start and svc_dt < policy_ver.effective_start:
                        return False, f"Policy effective start {policy_ver.effective_start} is after service date {svc_dt}."
                    if policy_ver.effective_end and svc_dt > policy_ver.effective_end:
                        return False, f"Policy expired on {policy_ver.effective_end} before service date {svc_dt}."
            return True, None

        # 3. Denial Context: Strictly investigated claim and patient
        elif role == EvidentiaryRole.DENIAL_CONTEXT:
            if chunk.claim_id is None or chunk.patient_id is None:
                return False, "Denial context chunk lacks mandatory claim or patient linkage."
            if chunk.claim_id != scope.claim_id:
                return False, f"Claim mismatch: denial chunk claim {chunk.claim_id} != investigated {scope.claim_id}."
            if chunk.patient_id != scope.patient_id:
                return False, f"Patient mismatch in denial chunk: {chunk.patient_id} != {scope.patient_id}."
            return True, None

        # 4. Administrative Context
        elif role == EvidentiaryRole.ADMINISTRATIVE:
            if chunk.patient_id and chunk.patient_id != scope.patient_id:
                return False, f"Administrative chunk patient mismatch: {chunk.patient_id} != {scope.patient_id}."
            if chunk.claim_id and chunk.claim_id != scope.claim_id:
                return False, f"Administrative chunk claim mismatch: {chunk.claim_id} != {scope.claim_id}."
            return True, None

        return False, f"Unrecognized evidentiary role: {chunk.evidentiary_role}"

    def filter_chunks(
        self,
        chunk_ids: list[UUID],
        scope: RetrievalScopeContext,
    ) -> dict[UUID, EvidenceChunk]:
        """Fetch authoritative active chunks from DB and filter against authorized scope."""
        if not chunk_ids:
            return {}

        resolved_scope = self.resolve_context(scope)
        stmt = select(EvidenceChunk).where(
            EvidenceChunk.id.in_(chunk_ids),
            EvidenceChunk.is_active == True,
        )
        chunks = self.session.execute(stmt).scalars().all()

        valid_chunks: dict[UUID, EvidenceChunk] = {}
        for c in chunks:
            is_valid, _reason = self.validate_chunk_scope(c, resolved_scope)
            if is_valid:
                valid_chunks[c.id] = c

        return valid_chunks
