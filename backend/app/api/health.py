from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.app.core.config import get_settings
from backend.app.db.session import check_database_connection
from backend.app.llm.client import check_ollama_connection

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("", summary="Application liveness probe")
def get_health():
    """Returns honest application status and metadata."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "debug": settings.DEBUG,
    }


@router.get("/db", summary="Database readiness check")
def get_db_health():
    """Verifies PostgreSQL connectivity."""
    db_status = check_database_connection()
    status_code = (
        status.HTTP_200_OK if db_status["status"] == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=db_status)


@router.get("/llm", summary="Local LLM service check")
def get_llm_health():
    """Verifies Ollama connectivity and model availability."""
    llm_status = check_ollama_connection()
    status_code = (
        status.HTTP_200_OK if llm_status["status"] == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=llm_status)


@router.get("/all", summary="Full system readiness check")
def get_full_health():
    """Runs all readiness probes."""
    db_status = check_database_connection()
    llm_status = check_ollama_connection()
    
    all_healthy = (
        db_status.get("status") == "connected"
        and llm_status.get("status") == "connected"
    )
    
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "app": {
                "status": "ok",
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
            },
            "database": db_status,
            "llm": llm_status,
        },
    )
