"""DriftWatch FastAPI app: lifespan (init_db + scheduler), CORS, /api routes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db import init_db
from app.scheduler import create_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("DriftWatch started: db initialized, scheduler running")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("DriftWatch scheduler shut down")


app = FastAPI(title="DriftWatch", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# In the Docker image the built frontend is copied to backend/static and the
# app serves it directly — one container, one port. In local dev (no static
# bundle) the Vite dev server handles the UI and "/" stays a JSON health route.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
else:

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "driftwatch", "docs": "/docs"}
