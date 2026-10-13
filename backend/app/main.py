from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.health import router as health_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
origins = [
    settings.FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(health_router, prefix="/api")


@app.get("/", tags=["root"])
def root():
    return {
        "message": "Welcome to Agentic Denial Management API",
        "principle": "AI investigates. Evidence supports. A human decides.",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
