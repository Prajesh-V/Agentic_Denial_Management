#!/usr/bin/env python3
"""CLI tool to build or rebuild the dense FAISS vector index for an evidence corpus."""

import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "backend"))

from backend.app.db.session import SessionLocal
from backend.app.retrieval.service import HybridRetrievalService


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild FAISS vector index for evidence retrieval.")
    parser.add_argument(
        "--dataset",
        "--dataset-build-id",
        required=True,
        help="Target DatasetBuild ID (e.g., synth_smoke_20261013_v1)",
    )
    parser.add_argument(
        "--index-id",
        default=None,
        help="Custom Index ID (default: idx_bge_small_v1_<dataset_build_id>)",
    )
    parser.add_argument(
        "--chunker-version",
        default="v1.0",
        help="Expected chunker configuration version (default: v1.0)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if index is already marked READY",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output build manifest in JSON format",
    )

    args = parser.parse_args()

    session = SessionLocal()
    try:
        service = HybridRetrievalService(session=session)
        if not args.json:
            print(f"Building FAISS vector index for dataset: {args.dataset}...")
            print(f"Embedding model: {service.embedder.model_name}")

        manifest = service.build_index(
            dataset_build_id=args.dataset,
            index_id=args.index_id,
            chunker_version=args.chunker_version,
            force=args.force,
        )

        if args.json:
            print(manifest.model_dump_json(indent=2))
        else:
            print("\n" + "=" * 50)
            print("VECTOR INDEX BUILD COMPLETE")
            print("=" * 50)
            print(f"Index ID:            {manifest.index_id}")
            print(f"Dataset Build:       {manifest.dataset_build_id}")
            print(f"Embedding Model:     {manifest.embedding_model}")
            print(f"Dimension:           {manifest.embedding_dimension}")
            print(f"Chunk Count:         {manifest.chunk_count}")
            print(f"Index File Hash:     {manifest.faiss_index_hash[:16]}...")
            print(f"Corpus Fingerprint:  {manifest.corpus_fingerprint[:16]}...")
            print(f"Status:              {manifest.status}")
            print("=" * 50)
        return 0
    except Exception as e:
        print(f"ERROR: Index build failed: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
