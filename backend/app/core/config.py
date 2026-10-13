from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "Agentic Denial Management"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # PostgreSQL Database
    POSTGRES_USER: str = "denial_app"
    POSTGRES_PASSWORD: str = "local_dev_only_change_this_2026"
    POSTGRES_DB: str = "denial_management"
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # Local LLM / Ollama
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_TEMPERATURE: float = 0.0

    # Embeddings & Retrieval
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    FAISS_INDEX_DIR: str = "data/indexes"

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sanitized_database_url(self) -> str:
        """Returns connection URL with masked password for safe logging."""
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:***"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
