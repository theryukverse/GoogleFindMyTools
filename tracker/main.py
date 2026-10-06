import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tracker import database as db
from tracker.api.routes import router as api_router
from tracker.config import settings
from tracker.device_sync import sync_devices
from tracker.poller import DevicePoller
from tracker.providers import get_provider

# Configure logging to standard output
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tracker")

# Global reference to the poller
poller_instance: DevicePoller = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global poller_instance
    logger.info("Starting Device Location Tracker service...")

    # 1. Initialize database schema
    db_path = settings.get_database_path()
    db.init_db(db_path)

    # 2. Sync devices from Google Find My network
    logger.info("Syncing devices from Google Find My (list_devices_with_return)...")
    try:
        with db.get_db_connection(db_path) as conn:
            sync_summary = await asyncio.to_thread(sync_devices, conn)
        logger.info("Startup device sync summary: %s", sync_summary)
    except Exception as e:
        logger.warning(
            "Initial device sync failed (service will continue running): %s", e
        )

    # 3. Instantiate location provider
    provider = get_provider(settings.LOCATION_PROVIDER)
    logger.info("Configured active location provider: %s", provider.__class__.__name__)

    # 4. Start background poller task
    poller_instance = DevicePoller(
        db_path=db_path,
        provider=provider,
        interval_seconds=settings.POLL_INTERVAL_SECONDS,
    )
    poller_instance.start()

    yield

    # Shutdown sequence
    logger.info("Shutting down Device Location Tracker service...")
    if poller_instance:
        await poller_instance.stop()
    logger.info("Graceful shutdown complete.")


app = FastAPI(
    title="Device Location Tracker",
    description="Lightweight Device Location Tracker with Map History",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for flexible integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Mount static web UI assets
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Device Location Tracker API is running. Web UI not found."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "tracker.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
