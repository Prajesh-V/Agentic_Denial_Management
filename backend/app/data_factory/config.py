"""Configuration profiles, domain subseed derivation, and hashing for the Synthetic Data Factory."""

import hashlib
import json
from dataclasses import asdict, dataclass

GENERATOR_VERSION = "1.2.0"
SCHEMA_VERSION = "2.1"


@dataclass(frozen=True)
class DataFactoryProfile:
    name: str
    organization_count: int
    facilities_per_org: int
    practitioners_per_org: int
    payers_count: int
    plans_per_payer: int
    patient_count: int
    train_dev_ratio: float = 0.8


PROFILES: dict[str, DataFactoryProfile] = {
    "smoke": DataFactoryProfile(
        name="smoke",
        organization_count=2,
        facilities_per_org=2,
        practitioners_per_org=4,
        payers_count=3,
        plans_per_payer=2,
        patient_count=25,
        train_dev_ratio=0.8,
    ),
    "dev": DataFactoryProfile(
        name="dev",
        organization_count=5,
        facilities_per_org=3,
        practitioners_per_org=8,
        payers_count=6,
        plans_per_payer=3,
        patient_count=1000,
        train_dev_ratio=0.8,
    ),
    "research": DataFactoryProfile(
        name="research",
        organization_count=10,
        facilities_per_org=4,
        practitioners_per_org=10,
        payers_count=10,
        plans_per_payer=4,
        patient_count=10000,
        train_dev_ratio=0.8,
    ),
    "stress": DataFactoryProfile(
        name="stress",
        organization_count=15,
        facilities_per_org=5,
        practitioners_per_org=15,
        payers_count=12,
        plans_per_payer=5,
        patient_count=25000,
        train_dev_ratio=0.8,
    ),
}


def get_profile(name: str) -> DataFactoryProfile:
    """Retrieves a configuration profile by name."""
    if name not in PROFILES:
        raise ValueError(
            f"Unknown data factory profile '{name}'. Supported profiles: {list(PROFILES.keys())}"
        )
    return PROFILES[name]


def derive_subseed(master_seed: int, domain_name: str) -> int:
    """Derives an independent, reproducible 64-bit integer subseed for a specific domain.

    Ensures modifying one generator's random consumption does not disrupt other domains.
    """
    key = f"{master_seed}:{domain_name}".encode()
    digest = hashlib.sha256(key).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def calculate_config_hash(profile: DataFactoryProfile, master_seed: int) -> str:
    """Computes a deterministic SHA-256 hash of the fully resolved build configuration."""
    payload = {
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "master_seed": master_seed,
        "profile": asdict(profile),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
