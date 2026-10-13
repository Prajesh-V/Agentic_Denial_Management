import argparse
import json
import sys
from pathlib import Path

# Add project root and backend to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "backend"))

from backend.app.db.session import SessionLocal
from backend.app.ingestion.pipeline import EvidenceIngestionPipeline
from backend.app.ingestion.validator import EvidenceCorpusValidator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evidence Corpus Ingestion and Document Processing CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        "--dataset-build-id",
        dest="dataset_build_id",
        required=True,
        help="Target DatasetBuild ID (e.g., synth_smoke_20261013_v1)",
    )
    parser.add_argument(
        "--source-types",
        help="Comma-separated list of source types to ingest (e.g., ClinicalDocument,PayerPolicyVersion)",
    )
    parser.add_argument(
        "--chunker-version",
        default="v1.0",
        help="Chunker configuration version string",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=600,
        help="Target character size per chunk",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=80,
        help="Target character overlap between consecutive chunks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute extraction, normalization, chunking, and validation without writing to DB",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Force reprocessing and superseding of existing chunks",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run comprehensive validation on existing corpus chunks for the target build",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Safely remove evidence chunks belonging to the target build (canonical records preserved)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    session = SessionLocal()

    try:
        if args.validate:
            validator = EvidenceCorpusValidator(session)
            report = validator.validate_corpus(dataset_build_id=args.dataset_build_id)
            if args.json:
                print(json.dumps(report, indent=2, default=str))
            else:
                print("==================================================")
                print(f"EVIDENCE CORPUS VALIDATION REPORT: {args.dataset_build_id}")
                print("==================================================")
                print(f"Total Chunks Inspected: {report['total_chunks_inspected']}")
                print(f"Validation Passed:      {report['passed']}")
                print(f"Violation Count:        {report['violation_count']}")
                print("\nCounts by Evidentiary Role:")
                for role, cnt in report.get("counts_by_role", {}).items():
                    print(f"  - {role}: {cnt}")
                print("\nCounts by Source Type:")
                for stype, cnt in report.get("counts_by_source_type", {}).items():
                    print(f"  - {stype}: {cnt}")
                if report.get("violations"):
                    print("\nViolations:")
                    for v in report["violations"][:20]:
                        print(f"  [!] {v}")
            sys.exit(0 if report["passed"] else 1)

        pipeline = EvidenceIngestionPipeline(session)

        if args.reset:
            deleted_count = pipeline.reset_build_chunks(dataset_build_id=args.dataset_build_id)
            if args.json:
                print(json.dumps({"reset_build": args.dataset_build_id, "deleted_chunks": deleted_count}))
            else:
                print(f"Successfully removed {deleted_count} chunks for dataset build '{args.dataset_build_id}'.")
                print("Canonical sources and other builds remain intact.")
            sys.exit(0)

        # Ingestion run
        source_types = [s.strip() for s in args.source_types.split(",")] if args.source_types else None
        manifest = pipeline.ingest(
            dataset_build_id=args.dataset_build_id,
            source_types=source_types,
            chunker_version=args.chunker_version,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            dry_run=args.dry_run,
            reprocess=args.reprocess,
        )

        if args.json:
            print(manifest.model_dump_json(indent=2))
        else:
            print("==================================================")
            print("EVIDENCE CORPUS INGESTION MANIFEST")
            print("==================================================")
            print(f"Run ID:                 {manifest.run_id}")
            print(f"Dataset Build:          {manifest.dataset_build_id}")
            print(f"Processor Version:      {manifest.processor_version}")
            print(f"Chunker Version:        {manifest.chunker_version}")
            print(f"Duration (s):           {manifest.duration_seconds}s")
            print(f"Validation Passed:      {manifest.validation_passed}")
            print("--------------------------------------------------")
            print(f"Sources Discovered:     {manifest.sources_discovered}")
            print(f"Sources Processed:      {manifest.sources_processed}")
            print(f"Sources Skipped:        {manifest.sources_skipped}")
            print(f"Chunks Generated:       {manifest.chunks_generated}")
            print(f"Chunks Persisted:       {manifest.chunks_persisted}")
            print(f"Chunks Skipped (Dupe):  {manifest.chunks_skipped_duplicate}")
            print(f"Chunks Superseded:      {manifest.chunks_superseded}")
            print("\nDocuments Processed by Source Type:")
            for st, cnt in manifest.by_source_type.items():
                print(f"  - {st}: {cnt}")
            print("\nDocuments by Evidentiary Role:")
            for role, cnt in manifest.by_evidentiary_role.items():
                print(f"  - {role}: {cnt}")
            if manifest.errors:
                print("\nErrors / Warnings:")
                for err in manifest.errors:
                    print(f"  [!] {err}")

        sys.exit(0 if manifest.validation_passed else 1)

    finally:
        session.close()


if __name__ == "__main__":
    main()
