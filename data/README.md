# Synthetic Data Directory

This directory holds synthetic healthcare, claims, and denial management data produced by the versioned data factory.

## Strict Rules (docs/SYNTHETIC_DATA_FACTORY.md)
1. **100% Synthetic**: All patients, claims, clinical notes, coverage, and outcomes are synthetic fictional records.
2. **Deterministic**: Every dataset is generated from a defined generator version, seed, and profile.
3. **Partition Isolation**: Patient populations are strictly partitioned across `train`, `dev`, `holdout`, and `locked_test` to prevent leakage.
4. **No Real PII / PHI**: No actual payer or patient data is stored or downloaded.

## Layout
- `raw/`: Raw synthetic sources and configuration templates.
- `generated/`: Output datasets organized by namespace (`smoke`, `dev`, `benchmark`).
- `manifests/`: Dataset manifests with seeds, row counts, and generation hashes.
- `validation/`: Schema validation and clinical timeline audit reports.
- `indexes/`: Derived vector / lexical indexes (rebuildable from PostgreSQL).
