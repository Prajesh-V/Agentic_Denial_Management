"""Command-line interface for the Synthetic Data Factory: generate, validate, and reset operations."""

import argparse
import json
import logging
import sys

from sqlalchemy import select

from backend.app.data_factory.config import PROFILES
from backend.app.data_factory.pipeline import DataFactoryPipeline
from backend.app.db.models import DatasetBuild
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
        print(f"  Config hash: {build.configuration_hash}")
        print(f"  Validation passed: {build.validation_passed}")
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
    parser = argparse.ArgumentParser(description="Synthetic Data Factory Management CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose error output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate command
    gen_p = subparsers.add_parser("generate", help="Deterministically generate synthetic data")
    gen_p.add_argument("--profile", choices=list(PROFILES.keys()), default="smoke", help="Dataset profile")
    gen_p.add_argument("--seed", type=int, default=20261013, help="Master integer seed")
    gen_p.add_argument("--build-id", type=str, default=None, help="Explicit build ID (optional)")
    gen_p.add_argument("--replace", action="store_true", help="Replace existing build if present")

    # validate command
    val_p = subparsers.add_parser("validate", help="Inspect and display validation manifest for a build")
    val_p.add_argument("--build-id", type=str, required=True, help="Dataset build ID to validate")

    # reset command
    rst_p = subparsers.add_parser("reset", help="Safely roll back and purge a synthetic dataset build")
    rst_p.add_argument("--build-id", type=str, required=True, help="Dataset build ID to purge")

    parsed = parser.parse_args(argv)
    if parsed.command == "generate":
        return cmd_generate(parsed)
    elif parsed.command == "validate":
        return cmd_validate(parsed)
    elif parsed.command == "reset":
        return cmd_reset(parsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
