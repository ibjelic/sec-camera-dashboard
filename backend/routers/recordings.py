import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_recordings(request: Request, date: Optional[str] = None):
    """
    List all recordings, optionally filtered by date.

    Args:
        date: Filter by date in YYYY-MM-DD format
    """
    recorder = request.app.state.recorder
    recordings = recorder.get_recordings(date)

    # Get unique dates for navigation
    dates = sorted(set(r["date"] for r in recordings), reverse=True)

    return {
        "recordings": recordings,
        "dates": dates,
        "total": len(recordings)
    }


@router.get("/file/{date}/{filename}")
async def stream_recording(request: Request, date: str, filename: str):
    """
    Stream a recording file.

    Args:
        date: Date in YYYY-MM-DD format
        filename: Recording filename (e.g., 20240115_120000.mp4)
    """
    recorder = request.app.state.recorder
    file_path = recorder.get_recording_path(date, filename)

    if not file_path:
        raise HTTPException(status_code=404, detail="Recording not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache"
        }
    )


@router.delete("/file/{date}/{filename}")
async def delete_recording(request: Request, date: str, filename: str):
    """
    Delete a recording file.

    Args:
        date: Date in YYYY-MM-DD format
        filename: Recording filename
    """
    recorder = request.app.state.recorder

    if recorder.delete_recording(date, filename):
        logger.info(f"Deleted recording: {date}/{filename}")
        return {"status": "deleted", "file": f"{date}/{filename}"}

    raise HTTPException(status_code=404, detail="Recording not found")


@router.get("/dates")
async def list_dates(request: Request):
    """List all dates with recordings."""
    recorder = request.app.state.recorder
    recordings = recorder.get_recordings()
    dates = sorted(set(r["date"] for r in recordings), reverse=True)

    return {
        "dates": dates,
        "total": len(dates)
    }
