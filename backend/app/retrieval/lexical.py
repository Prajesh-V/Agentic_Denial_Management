"""PostgreSQL native full-text search service for lexical evidence retrieval."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.ingestion.schemas import EvidentiaryRole
from backend.app.retrieval.schemas import RetrievalScopeContext


class PostgresLexicalSearchService:
    """Executes safe, parameterized PostgreSQL full-text search with scope constraints and ts_rank ranking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _sanitize_and_build_tsquery(self, query: str) -> str:
        """Extract alphanumeric and code tokens and construct a valid OR tsquery."""
        tokens = re.findall(r"[A-Za-z0-9]+(?:[\.\-][A-Za-z0-9]+)*", query)
        clean_tokens: list[str] = []
        for t in tokens:
            cleaned = t.strip("-.").strip()
            if cleaned and len(cleaned) > 1:
                safe_tok = re.sub(r"[^A-Za-z0-9]", "", cleaned)
                if safe_tok:
                    clean_tokens.append(safe_tok)

        if not clean_tokens:
            return ""

        return " | ".join(clean_tokens)

    def search(
        self,
        query: str,
        scope: RetrievalScopeContext,
        top_k: int = 50,
    ) -> list[tuple[UUID, float, int]]:
        """Execute parameterized lexical search over evidence chunks matching scope constraints."""
        if not query or not query.strip():
            return []

        or_tsquery = self._sanitize_and_build_tsquery(query)
        if not or_tsquery:
            return []

        allowed_roles_str = [r.value for r in scope.allowed_roles] if scope.allowed_roles else [r.value for r in EvidentiaryRole]

        sql = """
            SELECT
                id,
                ts_rank(to_tsvector('english', content), to_tsquery('english', :tsquery)) as rank_score
            FROM evidence_chunks
            WHERE is_active = TRUE
              AND evidentiary_role = ANY(:allowed_roles)
              AND to_tsvector('english', content) @@ to_tsquery('english', :tsquery)
              AND (
                  -- Clinical supporting evidence: strictly authorized patient
                  (evidentiary_role = 'CLINICAL_SUPPORTING' AND patient_id = CAST(:patient_id AS UUID))
                  OR
                  -- Payer policy evidence: shared document, strictly payer-scoped, never patient-owned
                  (evidentiary_role = 'PAYER_POLICY' AND patient_id IS NULL AND (CAST(:payer_id AS UUID) IS NULL OR payer_id = CAST(:payer_id AS UUID)))
                  OR
                  -- Denial context: strictly investigated claim and patient
                  (evidentiary_role = 'DENIAL_CONTEXT' AND claim_id = CAST(:claim_id AS UUID) AND patient_id = CAST(:patient_id AS UUID))
                  OR
                  -- Administrative context
                  (evidentiary_role = 'ADMINISTRATIVE' AND (claim_id = CAST(:claim_id AS UUID) OR patient_id = CAST(:patient_id AS UUID)))
              )
            ORDER BY rank_score DESC, id ASC
            LIMIT :limit;
        """

        params: dict[str, Any] = {
            "tsquery": or_tsquery,
            "allowed_roles": allowed_roles_str,
            "patient_id": str(scope.patient_id),
            "claim_id": str(scope.claim_id),
            "payer_id": str(scope.payer_id) if scope.payer_id else None,
            "limit": top_k,
        }

        rows = self.session.execute(text(sql), params).fetchall()

        results: list[tuple[UUID, float, int]] = []
        for idx, (cid, score) in enumerate(rows):
            results.append((UUID(str(cid)), float(score), idx + 1))

        return results
