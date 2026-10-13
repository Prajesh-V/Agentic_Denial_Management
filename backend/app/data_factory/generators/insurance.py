"""Deterministic generator for primary insurance coverage."""

import random
import uuid
from datetime import date

from backend.app.data_factory.config import DataFactoryProfile, derive_subseed
from backend.app.db.models import Coverage, Patient, PayerPlan


def deterministic_uuid(rng: random.Random) -> str:
    """Generate a RFC 4122 compliant UUID string deterministically from a seeded RNG."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def generate_insurance(
    master_seed: int,
    profile: DataFactoryProfile,
    patients: list[Patient],
    plans: list[PayerPlan],
) -> list[Coverage]:
    """Deterministically generates primary insurance coverage for every patient."""
    if not plans:
        raise ValueError("Cannot generate coverage without at least one payer plan.")
    if not patients:
        return []

    subseed = derive_subseed(master_seed, "insurance")
    rng = random.Random(subseed)

    coverages: list[Coverage] = []
    base_start_date = date(2025, 1, 1)

    for p_idx, patient in enumerate(patients):
        selected_plan = plans[p_idx % len(plans)]
        mem_suffix = f"{p_idx + 1:06d}{rng.randint(1000, 9999)}"
        grp_suffix = f"{rng.randint(10000, 99999)}"

        cov = Coverage(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            payer_plan_id=selected_plan.id,
            member_id=f"MEM-SYNTH-{mem_suffix}",
            group_number=f"GRP-SYNTH-{grp_suffix}",
            status="active",
            start_date=base_start_date,
            end_date=None,
        )
        coverages.append(cov)

    return coverages
