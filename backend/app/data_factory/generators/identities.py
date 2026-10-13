"""Deterministic generator for synthetic patients partitioned into train_dev and holdout_test sets."""

import random
import uuid
from datetime import date, timedelta

from faker import Faker

from backend.app.data_factory.config import DataFactoryProfile, derive_subseed
from backend.app.db.models import Organization, Patient


def deterministic_uuid(rng: random.Random) -> str:
    """Generate a RFC 4122 compliant UUID string deterministically from a seeded RNG."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def generate_identities(
    master_seed: int,
    profile: DataFactoryProfile,
    organizations: list[Organization],
    build_id: str,
) -> list[Patient]:
    """Deterministically generates synthetic patients partitioned into train_dev and holdout_test sets."""
    if not organizations:
        raise ValueError("Cannot generate patients without at least one organization.")

    subseed = derive_subseed(master_seed, "identities")
    rng = random.Random(subseed)
    fake = Faker()
    fake.seed_instance(subseed)

    patients: list[Patient] = []
    split_cutoff = int(profile.patient_count * profile.train_dev_ratio)

    genders = ["male", "female", "other"]
    gender_weights = [0.48, 0.50, 0.02]

    base_reference_date = date(2026, 1, 1)

    for p_idx in range(profile.patient_count):
        org = organizations[p_idx % len(organizations)]
        gender = rng.choices(genders, weights=gender_weights, k=1)[0]

        if gender == "male":
            first_name = fake.first_name_male()
        elif gender == "female":
            first_name = fake.first_name_female()
        else:
            first_name = fake.first_name()

        last_name = fake.last_name()
        age_days = rng.randint(18 * 365, 85 * 365)
        birth_date = base_reference_date - timedelta(days=age_days)

        split_group = "train_dev" if p_idx < split_cutoff else "holdout_test"
        mrn_suffix = f"{p_idx + 1:06d}{rng.randint(1000, 9999)}"

        patient = Patient(
            id=deterministic_uuid(rng),
            organization_id=org.id,
            dataset_build_id=build_id,
            synthetic_mrn=f"MRN-SYNTH-{mrn_suffix}",
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            birth_date=birth_date,
            split_group=split_group,
            is_synthetic=True,
        )
        patients.append(patient)

    return patients
