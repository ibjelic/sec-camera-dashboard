import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings, runtime_settings
from backend.routers import stream, recordings, detection, settings as settings_router, storage
from backend.services.rtsp_recorder import RTSPRecorder
from backend.services.hls_streamer import HLSStreamer
from backend.services.person_detector import PersonDetector
from backend.services.storage_manager import StorageManager
from backend.services.event_store import EventStore
from backend.services.notification import NotificationService
from backend.websocket.manager import ws_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Service instances
recorder: RTSPRecorder = None
hls_streamer: HLSStreamer = None
detector: PersonDetector = None
storage_manager: StorageManager = None
event_store: EventStore = None
notification_service: NotificationService = None


def check_ffmpeg():
    """Verify FFmpeg is installed."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg not found. Please install FFmpeg.")
    logger.info("FFmpeg found")


def setup_directories():
    """Create required data directories."""
    dirs = [
        settings.data_dir / "recordings",
        settings.data_dir / "hls",
        settings.data_dir / "detections",
        settings.data_dir / "thumbnails",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directories ready at {settings.data_dir}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global recorder, hls_streamer, detector, storage_manager, event_store, notification_service

    # Startup
    logger.info("Starting Security Camera Dashboard...")

    check_ffmpeg()
    setup_directories()

    # Initialize services
    event_store = EventStore(settings.data_dir / "detections" / "events.db")
    await event_store.initialize()

    notification_service = NotificationService(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        data_dir=settings.data_dir
    )

    storage_manager = StorageManager(
        data_dir=settings.data_dir,
        ws_manager=ws_manager
    )

    detector = PersonDetector(
        rtsp_url=settings.rtsp_url_high,
        event_store=event_store,
        notification_service=notification_service,
        ws_manager=ws_manager,
        thumbnails_dir=settings.data_dir / "thumbnails"
    )

    recorder = RTSPRecorder(
        rtsp_url=settings.rtsp_url_high,
        output_dir=settings.data_dir / "recordings",
        ws_manager=ws_manager
    )

    hls_streamer = HLSStreamer(
        rtsp_url=settings.rtsp_url_low,
        output_dir=settings.data_dir / "hls",
        ws_manager=ws_manager
    )

    # Store services in app state for routers
    app.state.recorder = recorder
    app.state.hls_streamer = hls_streamer
    app.state.detector = detector
    app.state.storage_manager = storage_manager
    app.state.event_store = event_store
    app.state.notification_service = notification_service
    app.state.ws_manager = ws_manager

    # Start services
    asyncio.create_task(recorder.start())
    asyncio.create_task(hls_streamer.start())
    asyncio.create_task(detector.start())
    asyncio.create_task(storage_manager.start_cleanup_task())

    logger.info("All services started")

    yield

    # Shutdown
    logger.info("Shutting down services...")
    await recorder.stop()
    await hls_streamer.stop()
    await detector.stop()
    await storage_manager.stop()
    await event_store.close()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Security Camera Dashboard",
    description="RTSP stream monitoring with person detection",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stream.router, prefix="/api/stream", tags=["Stream"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["Recordings"])
app.include_router(detection.router, prefix="/api/detections", tags=["Detection"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Mount HLS output directory
app.mount("/hls", StaticFiles(directory=str(settings.data_dir / "hls")), name="hls")

# Mount thumbnails directory
app.mount("/thumbnails", StaticFiles(directory=str(settings.data_dir / "thumbnails")), name="thumbnails")


@app.get("/")
async def root():
    """Redirect to dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            data = await websocket.receive_text()
            # Echo back or handle commands
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "services": {
            "recorder": recorder.is_running if recorder else False,
            "hls_streamer": hls_streamer.is_running if hls_streamer else False,
            "detector": detector.is_running if detector else False,
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
