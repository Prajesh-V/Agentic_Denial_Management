#!/usr/bin/env python3
"""CLI tool to validate vector index integrity, dimensions, and freshness against PostgreSQL."""

import argparse
import json
import sys
from pathlib import Path

# Add backend directory to sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "backend"))

from backend.app.db.session import SessionLocal
from backend.app.retrieval.service import HybridRetrievalService


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate FAISS vector index integrity and freshness.")
    parser.add_argument(
        "--dataset",
        "--dataset-build-id",
        required=True,
        help="Target DatasetBuild ID (e.g., synth_smoke_20261013_v1)",
    )
    parser.add_argument(
        "--index-id",
        default=None,
        help="Target Index ID to validate",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output validation results in JSON format",
    )

    args = parser.parse_args()

    session = SessionLocal()
    try:
        service = HybridRetrievalService(session=session)
        result = service.validate_index(
            dataset_build_id=args.dataset,
            index_id=args.index_id,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("\n" + "=" * 50)
            print(f"VECTOR INDEX VALIDATION REPORT: {args.dataset}")
            print("=" * 50)
            print(f"Index ID:        {result.get('index_id')}")
            print(f"Valid:           {result.get('valid')}")
            print(f"Stale:           {result.get('is_stale')}")
            print(f"Chunk Count:     {result.get('chunk_count')}")
            print(f"Dimension:       {result.get('embedding_dimension')}")
            if result.get("faiss_index_hash"):
                print(f"File Hash:       {result.get('faiss_index_hash')[:16]}...")
            if result.get("errors"):
                print("\nDiscrepancies:")
                for err in result["errors"]:
                    print(f"  - {err}")
            print("=" * 50)

        return 0 if result.get("valid") else 1
    except Exception as e:
        print(f"ERROR: Index validation failed: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
