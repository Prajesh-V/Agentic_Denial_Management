"""Deterministic generator for synthetic provider organizations, facilities, practitioners, payers, plans, and system users."""

import random
import uuid
from dataclasses import dataclass, field

from faker import Faker

from backend.app.data_factory.config import DataFactoryProfile, derive_subseed
from backend.app.db.models import (
    Facility,
    Organization,
    OrganizationMembership,
    Payer,
    PayerPlan,
    Practitioner,
    User,
    UserRole,
)

ORGANIZATION_NAMES = [
    ("Apex Regional Medical Center", "HOSPITAL_SYSTEM"),
    ("Northstar Health Network", "HOSPITAL_SYSTEM"),
    ("Mercy Health System", "HOSPITAL_SYSTEM"),
    ("Pacific Medical Center", "HOSPITAL_SYSTEM"),
    ("Cascades Healthcare Partners", "PROVIDER_GROUP"),
    ("Pinnacle Orthopedics & Spine", "PROVIDER_GROUP"),
    ("Summit Valley Community Hospital", "HOSPITAL_SYSTEM"),
    ("Beacon Hill Specialty Clinics", "PROVIDER_GROUP"),
    ("Evergreen Health Alliance", "HOSPITAL_SYSTEM"),
    ("Metro Ambulatory Surgery Network", "PROVIDER_GROUP"),
    ("Highland Memorial Hospital", "HOSPITAL_SYSTEM"),
    ("Crestview Medical Group", "PROVIDER_GROUP"),
    ("Silverlake Integrated Health", "HOSPITAL_SYSTEM"),
    ("Oakridge Surgical Associates", "PROVIDER_GROUP"),
    ("St. Jude Community Health Network", "HOSPITAL_SYSTEM"),
]

SPECIALTIES = [
    ("Orthopedic Surgery", "MD"),
    ("Cardiology", "MD"),
    ("Internal Medicine", "MD"),
    ("General Surgery", "MD"),
    ("Neurology", "MD"),
    ("Radiology", "MD"),
    ("Physical Medicine & Rehabilitation", "DO"),
    ("Anesthesiology", "MD"),
    ("Family Medicine", "DO"),
    ("Sports Medicine", "MD"),
]

FACILITY_TYPES = [
    ("Main Hospital Campus", "21"),        # Inpatient Hospital
    ("Outpatient Surgical Center", "24"),  # Ambulatory Surgical Center
    ("Orthopedic Specialty Clinic", "11"), # Office
    ("Ambulatory Care Pavilion", "22"),    # Outpatient Hospital
    ("Diagnostic Imaging Center", "11"),   # Office
    ("Rehabilitation Center", "11"),       # Office
]

PAYER_DEFINITIONS = [
    ("Aegis Blue Commercial", "COMMERCIAL", 90, 180),
    ("United Health Assurance", "COMMERCIAL", 90, 180),
    ("Apex Medicare Advantage", "MEDICARE_ADVANTAGE", 180, 60),
    ("Summit Care Managed Medicaid", "MANAGED_MEDICAID", 90, 90),
    ("Continental Health PPO", "COMMERCIAL", 90, 180),
    ("Silverstar Senior Health", "MEDICARE_ADVANTAGE", 180, 60),
    ("Cascade Community Care", "MANAGED_MEDICAID", 90, 90),
    ("Pinnacle National Insurance", "COMMERCIAL", 90, 180),
    ("Evergreen Medicare Plus", "MEDICARE_ADVANTAGE", 180, 60),
    ("Harbor State Family Plan", "MANAGED_MEDICAID", 90, 90),
    ("Empire Standard Commercial", "COMMERCIAL", 90, 180),
    ("Valley Comprehensive Care", "COMMERCIAL", 90, 180),
]

PLAN_SUFFIXES = [
    ("Gold Comprehensive PPO", "PPO"),
    ("Silver Choice HMO", "HMO"),
    ("Bronze Essential EPO", "EPO"),
    ("Advantage Preferred PPO", "PPO"),
    ("Select Access HMO", "HMO"),
]


def deterministic_uuid(rng: random.Random) -> str:
    """Generate a RFC 4122 compliant UUID string deterministically from a seeded RNG."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


@dataclass
class GeneratedOrganizationsResult:
    organizations: list[Organization] = field(default_factory=list)
    facilities: list[Facility] = field(default_factory=list)
    practitioners: list[Practitioner] = field(default_factory=list)
    payers: list[Payer] = field(default_factory=list)
    plans: list[PayerPlan] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    user_roles: list[UserRole] = field(default_factory=list)
    memberships: list[OrganizationMembership] = field(default_factory=list)


def generate_organizations(master_seed: int, profile: DataFactoryProfile) -> GeneratedOrganizationsResult:
    """Deterministically generates organizations, facilities, practitioners, payers, plans, and users."""
    subseed = derive_subseed(master_seed, "organizations")
    rng = random.Random(subseed)
    fake = Faker()
    fake.seed_instance(subseed)

    result = GeneratedOrganizationsResult()

    # 1. Organizations
    org_count = min(profile.organization_count, len(ORGANIZATION_NAMES))
    selected_org_templates = ORGANIZATION_NAMES[:org_count]

    for i, (org_name, org_type) in enumerate(selected_org_templates):
        uid = f"{i + 1:04d}{rng.randint(1000, 9999)}"
        org_id = deterministic_uuid(rng)
        org = Organization(
            id=org_id,
            name=f"{org_name} (Synthetic)",
            type=org_type,
            tax_id=f"TX-SYNTH-{uid}",
            npi=f"19{uid[:8]}",
        )
        result.organizations.append(org)

        # 2. Facilities per organization
        for f_idx in range(profile.facilities_per_org):
            fac_tmpl, pos_code = FACILITY_TYPES[f_idx % len(FACILITY_TYPES)]
            fac = Facility(
                id=deterministic_uuid(rng),
                organization_id=org.id,
                name=f"{org.name} - {fac_tmpl} #{f_idx + 1}",
                pos_code=pos_code,
                address={
                    "street": fake.street_address(),
                    "city": fake.city(),
                    "state": fake.state_abbr(),
                    "zip_code": fake.zipcode(),
                },
            )
            result.facilities.append(fac)

        # 3. Practitioners per organization
        for p_idx in range(profile.practitioners_per_org):
            p_uid = f"{i + 1:02d}{p_idx + 1:02d}{rng.randint(1000, 9999)}"
            spec_name, cred = SPECIALTIES[p_idx % len(SPECIALTIES)]
            prac = Practitioner(
                id=deterministic_uuid(rng),
                organization_id=org.id,
                npi=f"29{p_uid[:8]}",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                specialty=spec_name,
                credentials=cred,
            )
            result.practitioners.append(prac)

        # 4. System Users & Roles per organization (Analyst, Reviewer, Manager)
        org_slug = org_name.lower().replace(" ", "_")[:12]
        for role_name in ["analyst", "reviewer", "manager"]:
            u_code = f"{rng.randint(100000, 999999)}"
            user = User(
                id=deterministic_uuid(rng),
                email=f"{role_name}_{i + 1}_{u_code}@{org_slug}.synthetic",
                hashed_password="pbkdf2_sha256$synthetic_test_hash",
                full_name=f"{fake.first_name()} {fake.last_name()}",
                is_active=True,
            )
            result.users.append(user)

            membership = OrganizationMembership(
                id=deterministic_uuid(rng),
                user_id=user.id,
                organization_id=org.id,
                is_default=True,
            )
            result.memberships.append(membership)

            user_role = UserRole(
                user_id=user.id,
                role_id=role_name,
            )
            result.user_roles.append(user_role)

    # 5. Payers & Plans
    payer_count = min(profile.payers_count, len(PAYER_DEFINITIONS))
    selected_payer_templates = PAYER_DEFINITIONS[:payer_count]

    for p_idx, (payer_name, lob, tf_days, app_days) in enumerate(selected_payer_templates):
        payer_ident = f"PAYER_SYNTH_{p_idx + 1:03d}"
        payer = Payer(
            id=deterministic_uuid(rng),
            payer_identifier=payer_ident,
            name=f"{payer_name} (Synthetic)",
            line_of_business=lob,
            timely_filing_days=tf_days,
            appeal_filing_days=app_days,
        )
        result.payers.append(payer)

        for pl_idx in range(profile.plans_per_payer):
            plan_name_suffix, plan_type = PLAN_SUFFIXES[pl_idx % len(PLAN_SUFFIXES)]
            plan = PayerPlan(
                id=deterministic_uuid(rng),
                payer_id=payer.id,
                plan_name=f"{payer_name} {plan_name_suffix}",
                plan_type=plan_type,
            )
            result.plans.append(plan)

    return result
