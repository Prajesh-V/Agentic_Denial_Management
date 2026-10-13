from backend.app.db.models import Base

EXPECTED_TABLES = [
    # Identity (8)
    "organizations",
    "facilities",
    "practitioners",
    "users",
    "roles",
    "user_roles",
    "organization_memberships",
    "patients",
    # Clinical (8)
    "encounters",
    "conditions",
    "procedures",
    "observations",
    "medication_requests",
    "diagnostic_reports",
    "clinical_documents",
    "fhir_resources",
    # Billing (16)
    "payers",
    "payer_plans",
    "coverage",
    "service_codes",
    "authorizations",
    "claims",
    "claim_diagnoses",
    "claim_lines",
    "remittances",
    "remittance_lines",
    "denial_events",
    "payer_policy_versions",
    "appeals",
    "appeal_draft_versions",
    "appeal_decisions",
    "exports",
    # Investigation (8)
    "investigation_runs",
    "retrieval_attempts",
    "evidence_chunks",
    "evidence_assessments",
    "ground_truth_labels",
    "audit_events",
    "dataset_builds",
    "index_builds",
]


def test_authoritative_table_inventory_count():
    """Verify that exactly 40 tables are registered in SQLAlchemy metadata."""
    registered = list(Base.metadata.tables.keys())
    assert len(registered) == 40, f"Expected 40 tables, found {len(registered)}: {registered}"


def test_table_names_match_authoritative_list():
    """Verify each expected table name exists in the metadata."""
    registered_tables = set(Base.metadata.tables.keys())
    for table_name in EXPECTED_TABLES:
        assert table_name in registered_tables, f"Missing table: {table_name}"


def test_tables_have_primary_keys():
    """Verify every table has a defined primary key."""
    for table_name, table in Base.metadata.tables.items():
        pks = [col.name for col in table.primary_key.columns]
        assert len(pks) >= 1, f"Table {table_name} has no primary key"


def test_tenant_and_patient_composite_foreign_keys():
    """Verify composite foreign keys designed for tenant and patient isolation."""
    # Check claim composite FK to patients(id, organization_id)
    claims_table = Base.metadata.tables["claims"]
    fk_names = [fk.name for fk in claims_table.foreign_key_constraints]
    assert "fk_claim_patient_org" in fk_names, "Missing fk_claim_patient_org composite foreign key"

    # Check condition composite FK to encounters(id, patient_id)
    conditions_table = Base.metadata.tables["conditions"]
    cond_fk_names = [fk.name for fk in conditions_table.foreign_key_constraints]
    assert "fk_condition_encounter_patient" in cond_fk_names, "Missing fk_condition_encounter_patient composite foreign key"
