import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.db.session import check_database_connection
from backend.app.llm.client import check_ollama_connection
from backend.app.main import app


@pytest.mark.asyncio
async def test_health_liveness():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Agentic Denial Management"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "principle" in data
    assert data["principle"] == "AI investigates. Evidence supports. A human decides."


def test_database_connection():
    result = check_database_connection()
    assert result["status"] == "connected"
    assert result["database"] == "denial_management"
    assert "PostgreSQL 18" in result["version"]


def test_ollama_connection():
    result = check_ollama_connection()
    assert result["status"] == "connected"
    assert result["target_model"] == "qwen3:8b"
    assert result["target_model_available"] is True
