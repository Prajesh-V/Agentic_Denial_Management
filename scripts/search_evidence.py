#!/usr/bin/env python3
"""CLI tool to query evidence using hybrid, semantic, or lexical retrieval."""

import argparse
import sys
from pathlib import Path
from uuid import UUID

# Add backend directory to sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "backend"))

from backend.app.db.session import SessionLocal
from backend.app.ingestion.schemas import EvidentiaryRole
from backend.app.retrieval.schemas import RetrievalChannel, RetrievalRequest
from backend.app.retrieval.service import HybridRetrievalService


def main() -> int:
    parser = argparse.ArgumentParser(description="Query evidence chunks via hybrid retrieval.")
    parser.add_argument("--query", "-q", required=True, help="Search query string")
    parser.add_argument("--claim-id", required=True, help="Target Claim UUID")
    parser.add_argument("--patient-id", required=True, help="Target Patient UUID")
    parser.add_argument(
        "--channel",
        choices=["hybrid", "semantic", "lexical"],
        default="hybrid",
        help="Retrieval channel (default: hybrid)",
    )
    parser.add_argument(
        "--role",
        choices=["CLINICAL_SUPPORTING", "PAYER_POLICY", "DENIAL_CONTEXT", "ADMINISTRATIVE"],
        default=None,
        help="Optional filter for specific evidentiary role",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum results to return (default: 5)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Minimum fused score threshold",
    )
    parser.add_argument(
        "--dataset",
        default="synth_smoke_20261013_v1",
        help="Target DatasetBuild ID (default: synth_smoke_20261013_v1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    args = parser.parse_args()

    session = SessionLocal()
    try:
        service = HybridRetrievalService(session=session)
        allowed_roles = [EvidentiaryRole(args.role)] if args.role else None

        req = RetrievalRequest(
            query=args.query,
            claim_id=UUID(args.claim_id),
            patient_id=UUID(args.patient_id),
            channel=RetrievalChannel(args.channel),
            allowed_roles=allowed_roles,
            limit=args.limit,
            min_score=args.min_score,
        )

        response = service.retrieve(req, dataset_build_id=args.dataset)

        if args.json:
            print(response.model_dump_json(indent=2))
        else:
            print("\n" + "=" * 60)
            print(f"HYBRID RETRIEVAL RESULTS (Channel: {response.channel.value.upper()})")
            print("=" * 60)
            print(f"Query:        {response.query}")
            print(f"Claim ID:     {response.claim_id}")
            print(f"Patient ID:   {response.patient_id}")
            print(f"Found:        {response.total_candidates} chunks")
            print(f"Duration:     {response.retrieval_metadata.get('duration_ms')} ms")
            print("=" * 60)

            for item in response.results:
                print(f"\n[Rank #{item.fused_rank}] Score: {item.fused_score:.6f} | Role: {item.evidentiary_role.value}")
                print(f"Source: {item.source_resource_type} (ID: {item.source_resource_id})")
                if item.semantic_rank:
                    print(f"  - Semantic Rank #{item.semantic_rank} (Cosine Sim: {item.semantic_score:.4f})")
                if item.lexical_rank:
                    print(f"  - Lexical Rank #{item.lexical_rank} (ts_rank: {item.lexical_score:.4f})")
                print(f"Text Snippet:\n  {item.content[:200]}...")
                print(f"Explanation: {item.explanation}")
                print("-" * 60)

        return 0
    except Exception as e:
        print(f"ERROR: Retrieval failed: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
