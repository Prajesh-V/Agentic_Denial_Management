"""Reciprocal Rank Fusion (RRF) engine combining dense semantic and sparse lexical retrieval rankings."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.ingestion.schemas import EvidentiaryRole


@dataclass
class FusedCandidate:
    """Intermediate candidate with fused metrics and channel rankings."""
    chunk_id: UUID
    fused_score: float
    fused_rank: int
    semantic_rank: int | None = None
    semantic_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    explanation: str = ""


class ReciprocalRankFusionEngine:
    """Implements Reciprocal Rank Fusion: RRF(d) = sum(1 / (k + rank_i(d)))."""

    def __init__(self, k: int = 60) -> None:
        if k < 1:
            raise ValueError(f"RRF constant k must be >= 1, got {k}")
        self.k = k

    def fuse(
        self,
        semantic_results: list[tuple[UUID, float, int]],
        lexical_results: list[tuple[UUID, float, int]],
        limit: int = 10,
        min_score: float | None = None,
    ) -> list[FusedCandidate]:
        """Combine dense semantic and sparse lexical rankings using RRF."""
        candidates: dict[UUID, dict] = {}

        # 1. Process semantic results
        for chunk_id, sim_score, sem_rank in semantic_results:
            candidates[chunk_id] = {
                "sem_rank": sem_rank,
                "sem_score": sim_score,
                "lex_rank": None,
                "lex_score": None,
                "rrf_score": 1.0 / (self.k + sem_rank),
            }

        # 2. Process lexical results
        for chunk_id, lex_score, lex_rank in lexical_results:
            rrf_contrib = 1.0 / (self.k + lex_rank)
            if chunk_id in candidates:
                candidates[chunk_id]["lex_rank"] = lex_rank
                candidates[chunk_id]["lex_score"] = lex_score
                candidates[chunk_id]["rrf_score"] += rrf_contrib
            else:
                candidates[chunk_id] = {
                    "sem_rank": None,
                    "sem_score": None,
                    "lex_rank": lex_rank,
                    "lex_score": lex_score,
                    "rrf_score": rrf_contrib,
                }

        # 3. Deterministic sorting: higher rrf_score first, then better best-rank, then sem_rank, then lex_rank, then chunk_id UUID str
        sorted_candidates = sorted(
            candidates.items(),
            key=lambda item: (
                -item[1]["rrf_score"],
                min(item[1]["sem_rank"] or 999999, item[1]["lex_rank"] or 999999),
                item[1]["sem_rank"] or 999999,
                item[1]["lex_rank"] or 999999,
                str(item[0]),
            ),
        )

        # 4. Filter by min_score and apply limit
        fused_list: list[FusedCandidate] = []
        rank_counter = 1
        for cid, data in sorted_candidates:
            if min_score is not None and data["rrf_score"] < min_score:
                continue

            fused_cand = FusedCandidate(
                chunk_id=cid,
                fused_score=round(data["rrf_score"], 6),
                fused_rank=rank_counter,
                semantic_rank=data["sem_rank"],
                semantic_score=round(data["sem_score"], 4) if data["sem_score"] is not None else None,
                lexical_rank=data["lex_rank"],
                lexical_score=round(data["lex_score"], 4) if data["lex_score"] is not None else None,
            )
            fused_list.append(fused_cand)
            rank_counter += 1

            if len(fused_list) >= limit:
                break

        return fused_list

    @staticmethod
    def generate_explanation(
        candidate: FusedCandidate,
        role: EvidentiaryRole,
        source_type: str,
    ) -> str:
        """Deterministic explanation of why the evidence was retrieved and ranked."""
        if candidate.semantic_rank is not None and candidate.lexical_rank is not None:
            return (
                f"Retrieved via hybrid fusion (Fused rank #{candidate.fused_rank}, RRF score: {candidate.fused_score:.6f}). "
                f"Matched both channels: Semantic rank #{candidate.semantic_rank} (sim: {candidate.semantic_score:.3f}), "
                f"Lexical rank #{candidate.lexical_rank} (ts_rank: {candidate.lexical_score:.3f}). "
                f"Role: {role.value} from {source_type}."
            )
        elif candidate.semantic_rank is not None:
            return (
                f"Retrieved via semantic channel (Fused rank #{candidate.fused_rank}, RRF score: {candidate.fused_score:.6f}). "
                f"Semantic rank #{candidate.semantic_rank} (sim: {candidate.semantic_score:.3f}). "
                f"Role: {role.value} from {source_type}."
            )
        elif candidate.lexical_rank is not None:
            return (
                f"Retrieved via lexical channel (Fused rank #{candidate.fused_rank}, RRF score: {candidate.fused_score:.6f}). "
                f"Lexical rank #{candidate.lexical_rank} (ts_rank: {candidate.lexical_score:.3f}). "
                f"Role: {role.value} from {source_type}."
            )
        return f"Retrieved chunk (Fused rank #{candidate.fused_rank}, RRF score: {candidate.fused_score:.6f}). Role: {role.value}."
