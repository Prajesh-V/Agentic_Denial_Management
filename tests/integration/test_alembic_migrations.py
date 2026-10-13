import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

TEST_DB_URL = "postgresql+psycopg://denial_app:local_dev_only_change_this_2026@127.0.0.1:5432/denial_management_test"


@pytest.fixture(scope="module")
def isolated_test_db():
    """Ensures an isolated test database is prepared for migration testing."""
    admin_engine = create_engine(
        "postgresql+psycopg://denial_app:local_dev_only_change_this_2026@127.0.0.1:5432/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS denial_management_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE denial_management_test"))
    admin_engine.dispose()

    yield TEST_DB_URL

    # Cleanup after module tests
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS denial_management_test WITH (FORCE)"))
    admin_engine.dispose()


def test_alembic_migration_lifecycle(isolated_test_db):
    """Verifies that Alembic can upgrade, downgrade, and re-upgrade cleanly on an isolated database."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_test_db)

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        # 40 application tables + 1 alembic_version = 41
        assert count == 41, f"Expected 41 tables after upgrade, got {count}"
    test_engine.dispose()

    # 2. Downgrade to base
    command.downgrade(alembic_cfg, "base")
    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        # Only alembic_version should exist
        assert count <= 1, f"Expected <= 1 table after downgrade, got {count}"
    test_engine.dispose()

    # 3. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        assert count == 41, f"Expected 41 tables after re-upgrade, got {count}"
    test_engine.dispose()
