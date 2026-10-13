from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from backend.app.core.config import get_settings


@pytest.fixture(scope="module")
def isolated_test_db():
    settings = get_settings()
    test_db_url = settings.effective_test_database_url
    admin_db_url = settings.effective_test_admin_database_url

    # Ensure disposable test database safety checks
    settings.validate_disposable_test_database(settings.TEST_DATABASE_NAME)

    admin_engine = create_engine(admin_db_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(
            text(f"DROP DATABASE IF EXISTS {settings.TEST_DATABASE_NAME} WITH (FORCE)")
        )
        conn.execute(text(f"CREATE DATABASE {settings.TEST_DATABASE_NAME}"))
    admin_engine.dispose()

    yield test_db_url

    # Cleanup after module tests
    with admin_engine.connect() as conn:
        conn.execute(
            text(f"DROP DATABASE IF EXISTS {settings.TEST_DATABASE_NAME} WITH (FORCE)")
        )
    admin_engine.dispose()


def test_alembic_migration_lifecycle(isolated_test_db):
    """Verifies that Alembic can upgrade, downgrade, and re-upgrade cleanly on an isolated database."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", isolated_test_db)

    # 1. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        assert count >= 41, f"Expected at least 41 tables after upgrade, got {count}"
    test_engine.dispose()

    # 2. Downgrade to base
    command.downgrade(alembic_cfg, "base")
    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        assert count <= 1, f"Expected <= 1 table after downgrade, got {count}"
    test_engine.dispose()

    # 3. Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
    test_engine = create_engine(isolated_test_db, pool_pre_ping=True)
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar()
        assert count >= 41, f"Expected at least 41 tables after re-upgrade, got {count}"
    test_engine.dispose()
