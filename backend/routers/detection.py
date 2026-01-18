import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events")
async def get_detection_events(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(default=100, le=1000)
):
    """
    Get detection events within a time range.

    Args:
        start: Start time in ISO format
        end: End time in ISO format
        limit: Maximum number of events to return
    """
    event_store = request.app.state.event_store

    start_time = datetime.fromisoformat(start) if start else None
    end_time = datetime.fromisoformat(end) if end else None

    events = await event_store.get_events(
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )

    return {
        "events": events,
        "total": len(events)
    }


@router.get("/recent")
async def get_recent_events(request: Request, limit: int = Query(default=10, le=50)):
    """Get the most recent detection events."""
    event_store = request.app.state.event_store
    events = await event_store.get_recent_events(limit=limit)

    return {
        "events": events,
        "total": len(events)
    }


@router.get("/graph")
async def get_graph_data(
    request: Request,
    range: str = Query(default="1h", regex="^(10m|30m|1h|6h|12h|24h|48h)$")
):
    """
    Get detection data for timeline graph.

    Args:
        range: Time range - 10m, 30m, 1h, 6h, 12h, 24h, or 48h
    """
    event_store = request.app.state.event_store

    # Convert range to minutes
    range_map = {
        "10m": 10,
        "30m": 30,
        "1h": 60,
        "6h": 360,
        "12h": 720,
        "24h": 1440,
        "48h": 2880
    }
    range_minutes = range_map.get(range, 60)

    data = await event_store.get_graph_data(range_minutes=range_minutes)

    # Fill in gaps with zero values for continuous graph
    filled_data = _fill_timeline_gaps(data, range_minutes)

    return {
        "range": range,
        "range_minutes": range_minutes,
        "data": filled_data
    }


@router.get("/stats")
async def get_detection_stats(request: Request):
    """Get detection statistics."""
    event_store = request.app.state.event_store

    count_1h = await event_store.get_event_count(hours=1)
    count_24h = await event_store.get_event_count(hours=24)
    recent = await event_store.get_recent_events(limit=1)

    last_detection = None
    if recent:
        last_detection = recent[0]["timestamp"]

    return {
        "detections_1h": count_1h,
        "detections_24h": count_24h,
        "last_detection": last_detection
    }


@router.get("/status")
async def get_detector_status(request: Request):
    """Get the current status of the person detector."""
    detector = request.app.state.detector

    return {
        "running": detector.is_running,
        "threshold": request.app.state.detector.event_store is not None
    }


def _fill_timeline_gaps(data: list, range_minutes: int) -> list:
    """Fill gaps in timeline data with zero values."""
    # Create a map of existing data points
    data_map = {item["minute"]: item for item in data} if data else {}

    # Generate all minutes in range
    now = datetime.now()
    start_time = now - timedelta(minutes=range_minutes)

    filled = []
    current = start_time.replace(second=0, microsecond=0)

    while current <= now:
        minute_str = current.strftime("%Y-%m-%dT%H:%M:00")
        if minute_str in data_map:
            filled.append(data_map[minute_str])
        else:
            filled.append({
                "minute": minute_str,
                "max_confidence": 0,
                "count": 0
            })
        current += timedelta(minutes=1)

    return filled
