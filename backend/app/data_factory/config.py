import hashlib
import json
from dataclasses import asdict, dataclass

GENERATOR_VERSION: str = "1.0.0"
SCHEMA_VERSION: str = "2.1"


def derive_subseed(master_seed: int, domain: str) -> int:
    """Derives an independent, reproducible 64-bit integer seed for a subsystem domain."""
    h = hashlib.sha256(f"{master_seed}:{domain}".encode()).hexdigest()
    return int(h[:16], 16)


@dataclass(frozen=True)
class DataFactoryProfile:
    name: str
    patient_count: int
    organization_count: int
    facilities_per_org: int
    practitioners_per_org: int
    payers_count: int
    plans_per_payer: int
    train_dev_ratio: float = 0.8

    def validate(self) -> None:
        if self.patient_count <= 0:
            raise ValueError(f"patient_count must be positive, got {self.patient_count}")
        if self.organization_count <= 0:
            raise ValueError(f"organization_count must be positive, got {self.organization_count}")
        if self.facilities_per_org <= 0:
            raise ValueError(f"facilities_per_org must be positive, got {self.facilities_per_org}")
        if self.practitioners_per_org <= 0:
            raise ValueError(f"practitioners_per_org must be positive, got {self.practitioners_per_org}")
        if self.payers_count <= 0:
            raise ValueError(f"payers_count must be positive, got {self.payers_count}")
        if self.plans_per_payer <= 0:
            raise ValueError(f"plans_per_payer must be positive, got {self.plans_per_payer}")
        if not (0.0 < self.train_dev_ratio < 1.0):
            raise ValueError(f"train_dev_ratio must be between 0 and 1, got {self.train_dev_ratio}")


PROFILES: dict[str, DataFactoryProfile] = {
    "smoke": DataFactoryProfile(
        name="smoke",
        patient_count=25,
        organization_count=2,
        facilities_per_org=2,
        practitioners_per_org=4,
        payers_count=3,
        plans_per_payer=2,
        train_dev_ratio=0.8,
    ),
    "dev": DataFactoryProfile(
        name="dev",
        patient_count=1000,
        organization_count=5,
        facilities_per_org=4,
        practitioners_per_org=20,
        payers_count=6,
        plans_per_payer=3,
        train_dev_ratio=0.8,
    ),
    "research": DataFactoryProfile(
        name="research",
        patient_count=10000,
        organization_count=10,
        facilities_per_org=8,
        practitioners_per_org=50,
        payers_count=10,
        plans_per_payer=4,
        train_dev_ratio=0.8,
    ),
    "stress": DataFactoryProfile(
        name="stress",
        patient_count=25000,
        organization_count=15,
        facilities_per_org=10,
        practitioners_per_org=80,
        payers_count=12,
        plans_per_payer=5,
        train_dev_ratio=0.8,
    ),
}


def get_profile(name: str) -> DataFactoryProfile:
    """Retrieves a named profile or raises ValueError."""
    key = name.lower()
    if key not in PROFILES:
        raise ValueError(f"Unknown data factory profile '{name}'. Supported profiles: {list(PROFILES.keys())}")
    profile = PROFILES[key]
    profile.validate()
    return profile


def calculate_config_hash(profile: DataFactoryProfile, seed: int) -> str:
    """Calculates canonical SHA-256 hash of the configuration parameters and seed."""
    payload = {
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "profile": asdict(profile),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
