import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_storage_stats(request: Request):
    """Get storage statistics."""
    storage_manager = request.app.state.storage_manager

    stats = storage_manager.get_storage_stats()
    stats["recordings_count"] = storage_manager.get_recordings_count()

    return stats


@router.post("/cleanup")
async def trigger_cleanup(request: Request):
    """Manually trigger storage cleanup."""
    storage_manager = request.app.state.storage_manager

    try:
        await storage_manager.cleanup_old_recordings()
        stats = storage_manager.get_storage_stats()

        logger.info("Manual cleanup triggered")

        return {
            "status": "completed",
            "message": "Cleanup completed",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
