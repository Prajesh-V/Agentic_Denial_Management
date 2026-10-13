import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import project settings and model metadata
from backend.app.core.config import get_settings
from backend.app.db.models import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata

# Determine database URL:
# 1. Custom URL set explicitly on alembic config (e.g. in test suites)
# 2. Environment variable DATABASE_URL
# 3. Application Pydantic settings DATABASE_URL
custom_url = config.get_main_option("sqlalchemy.url")
if custom_url and not custom_url.startswith("driver://"):
    db_url = custom_url
elif os.environ.get("DATABASE_URL"):
    db_url = os.environ["DATABASE_URL"]
else:
    db_url = get_settings().DATABASE_URL

config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
