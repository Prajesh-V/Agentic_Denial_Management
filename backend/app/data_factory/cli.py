"""Command-line interface for the Synthetic Data Factory: generate, validate, and reset operations."""

import argparse
import json
import logging
import sys

from sqlalchemy import func, select

from backend.app.data_factory.config import PROFILES
from backend.app.data_factory.pipeline import DataFactoryPipeline
from backend.app.db.models import (
    Authorization,
    DatasetBuild,
    DenialEvent,
    Remittance,
)
from backend.app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("synthetic_factory_cli")


def cmd_generate(args: argparse.Namespace) -> int:
    pipeline = DataFactoryPipeline()
    try:
        build = pipeline.generate(
            profile_name=args.profile,
            seed=args.seed,
            build_id=args.build_id,
            replace_existing=args.replace,
        )
        print(f"SUCCESS: Generated build '{build.id}' (profile: {build.profile_name}, seed: {build.seed})")
        print(f"  Patients: {build.patient_count}")
        print(f"  Claims: {build.claim_count}")
        print(f"  Config hash: {build.configuration_hash}")
        print(f"  Validation passed: {build.validation_passed}")

        # Query and display revenue-cycle persisted counts
        db = SessionLocal()
        try:
            auth_cnt = db.execute(select(func.count(Authorization.id))).scalar() or 0
            remit_cnt = db.execute(select(func.count(Remittance.id))).scalar() or 0
            denial_cnt = db.execute(select(func.count(DenialEvent.id))).scalar() or 0
            print(f"  Total Authorizations in DB: {auth_cnt}")
            print(f"  Total Remittances in DB: {remit_cnt}")
            print(f"  Total Denial Events in DB: {denial_cnt}")
        finally:
            db.close()

        return 0
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=args.verbose)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        build = db.execute(
            select(DatasetBuild).where(DatasetBuild.id == args.build_id)
        ).scalar_one_or_none()

        if not build:
            print(f"ERROR: Dataset build '{args.build_id}' not found in database.")
            return 1

        print(f"Dataset build: {build.id}")
        print(f"  Generator Version: {build.generator_version}")
        print(f"  Profile: {build.profile_name}")
        print(f"  Seed: {build.seed}")
        print(f"  Patients: {build.patient_count}")
        print(f"  Claims: {build.claim_count}")
        print(f"  Validation Passed: {build.validation_passed}")
        print("  Validation Details:")
        print(json.dumps(build.validation_report, indent=4))
        return 0 if build.validation_passed else 1
    finally:
        db.close()


def cmd_reset(args: argparse.Namespace) -> int:
    pipeline = DataFactoryPipeline()
    try:
        counts = pipeline.reset(build_id=args.build_id)
        print(f"SUCCESS: Reset dataset build '{args.build_id}'")
        for entity, count in counts.items():
            print(f"  Deleted {entity}: {count}")
        return 0
    except Exception as e:
        logger.error(f"Reset failed: {e}", exc_info=args.verbose)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="synthetic_factory_cli",
        description="CLI tool for the deterministic Synthetic Data Factory.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose stack traces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: generate
    gen_parser = subparsers.add_parser("generate", help="Generate and persist a synthetic dataset build.")
    gen_parser.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        default="smoke",
        help="Configuration profile (default: smoke).",
    )
    gen_parser.add_argument(
        "--seed",
        type=int,
        default=20261013,
        help="Deterministic master seed (default: 20261013).",
    )
    gen_parser.add_argument(
        "--build-id",
        type=str,
        default=None,
        help="Optional explicit build identifier override.",
    )
    gen_parser.add_argument(
        "--replace",
        action="store_true",
        help="Safely rollback and replace existing build if it already exists.",
    )

    # Subcommand: validate
    val_parser = subparsers.add_parser("validate", help="Inspect validation manifest of an existing build.")
    val_parser.add_argument("--build-id", type=str, required=True, help="Build identifier to validate.")

    # Subcommand: reset
    reset_parser = subparsers.add_parser("reset", help="Safely delete all records of a specific dataset build.")
    reset_parser.add_argument("--build-id", type=str, required=True, help="Build identifier to reset.")

    args = parser.parse_args(argv)

    if args.command == "generate":
        return cmd_generate(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "reset":
        return cmd_reset(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
