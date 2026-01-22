import asyncio
import logging
import subprocess
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.config import settings, runtime_settings

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
    asyncio.create_task(hls_streamer.start())
    asyncio.create_task(recorder.start())

    logger.info("Streams restarted by user request")

    return {"status": "restarting", "message": "Streams are restarting"}


def _probe_stream(rtsp_url: str) -> dict:
    """Probe an RTSP stream using ffprobe to get resolution and bitrate."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-rtsp_transport", "tcp",
            "-print_format", "json",
            "-show_streams",
            "-analyzeduration", "2000000",
            "-probesize", "2000000",
            rtsp_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"error": f"ffprobe failed: {result.stderr}"}

        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        video_stream = None
        for s in streams:
            if s.get("codec_type") == "video":
                video_stream = s
                break

        if not video_stream:
            return {"error": "No video stream found"}

        return {
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "codec": video_stream.get("codec_name", "unknown"),
            "fps": video_stream.get("r_frame_rate", "unknown"),
            "bit_rate": int(video_stream.get("bit_rate", 0)) if video_stream.get("bit_rate") else 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Probe timeout"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/switch/{stream_type}")
async def switch_stream(stream_type: int, request: Request):
    """Switch to a different stream type (0=high, 1=low) and restart HLS streamer."""
    if stream_type not in [0, 1]:
        raise HTTPException(status_code=400, detail="stream_type must be 0 or 1")

    # Update runtime settings
    runtime_settings.update(stream_type=stream_type)

    # Get the RTSP URL for the new stream type
    new_url = settings.rtsp_url_high if stream_type == 0 else settings.rtsp_url_low

    # Stop HLS streamer
    hls_streamer = request.app.state.hls_streamer
    await hls_streamer.stop()

    # Update RTSP URL and restart
    hls_streamer.rtsp_url = new_url
    asyncio.create_task(hls_streamer.start())

    logger.info(f"Switched HLS stream to type {stream_type}: {new_url}")

    return {
        "status": "switching",
        "stream_type": stream_type,
        "message": f"Switching to stream type {stream_type}"
    }


@router.get("/compare")
async def compare_streams():
    """Probe both stream types and return their properties for comparison."""
    # Run probes in parallel using threads (ffprobe is blocking)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_high = executor.submit(_probe_stream, settings.rtsp_url_high)
        future_low = executor.submit(_probe_stream, settings.rtsp_url_low)

        result_high = future_high.result()
        result_low = future_low.result()

    return {
        "stream_0": {
            "url": settings.rtsp_url_high,
            "label": "High",
            **result_high
        },
        "stream_1": {
            "url": settings.rtsp_url_low,
            "label": "Low",
            **result_low
        },
        "current": runtime_settings.stream_type
    }
