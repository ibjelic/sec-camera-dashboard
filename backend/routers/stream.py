import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/hls/stream.m3u8")
async def get_hls_playlist(request: Request):
    """
    Get the HLS playlist file.
    Returns the m3u8 playlist for live streaming.
    """
    hls_streamer = request.app.state.hls_streamer

    if not hls_streamer.is_playlist_ready():
        raise HTTPException(
            status_code=503,
            detail="Stream not ready. Please wait a few seconds."
        )

    return FileResponse(
        hls_streamer.get_playlist_path(),
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/status")
async def get_stream_status(request: Request):
    """Get the current status of the HLS stream."""
    hls_streamer = request.app.state.hls_streamer
    recorder = request.app.state.recorder

    return {
        "hls_streaming": hls_streamer.is_running,
        "hls_ready": hls_streamer.is_playlist_ready(),
        "recording": recorder.is_running,
        "stream_url": "/hls/stream.m3u8" if hls_streamer.is_playlist_ready() else None
    }


@router.post("/restart")
async def restart_streams(request: Request):
    """Restart all streaming services."""
    hls_streamer = request.app.state.hls_streamer
    recorder = request.app.state.recorder

    # Stop services
    await hls_streamer.stop()
    await recorder.stop()

    # Restart services
    import asyncio
    asyncio.create_task(hls_streamer.start())
    asyncio.create_task(recorder.start())

    logger.info("Streams restarted by user request")

    return {"status": "restarting", "message": "Streams are restarting"}
