import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kodiak.core.config import settings
from kodiak.database import init_db

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Kodiak Backend...")
    # Import models so SQLModel metadata is populated
    from kodiak.database import models  # noqa
    await init_db()
    yield
    # Shutdown
    logger.info("Shutting down Kodiak Backend...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}

# app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    import sys
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
