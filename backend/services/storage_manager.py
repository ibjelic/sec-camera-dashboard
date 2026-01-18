import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from backend.config import runtime_settings
from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages storage cleanup and disk monitoring."""

    def __init__(self, data_dir: Path, ws_manager: ConnectionManager):
        self.data_dir = data_dir
        self.ws_manager = ws_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self):
        """Start periodic cleanup task."""
        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("Storage manager started")

    async def stop(self):
        """Stop the cleanup task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Storage manager stopped")

    async def _cleanup_loop(self):
        """Periodic cleanup loop - runs every 10 minutes."""
        while self._running:
            try:
                await self.cleanup_old_recordings()
                await self.broadcast_storage_stats()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

            await asyncio.sleep(600)  # 10 minutes

    async def cleanup_old_recordings(self):
        """Remove recordings older than retention period."""
        retention_hours = runtime_settings.retention_hours
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)

        recordings_dir = self.data_dir / "recordings"
        deleted_count = 0
        deleted_size = 0

        for date_dir in recordings_dir.glob("*"):
            if not date_dir.is_dir():
                continue

            for recording in date_dir.glob("*.mp4"):
                try:
                    # Parse timestamp from filename: YYYYMMDD_HHMMSS.mp4
                    filename = recording.stem
                    file_time = datetime.strptime(filename, "%Y%m%d_%H%M%S")

                    if file_time < cutoff_time:
                        size = recording.stat().st_size
                        recording.unlink()
                        deleted_count += 1
                        deleted_size += size
                        logger.info(f"Deleted old recording: {recording}")
                except (ValueError, OSError) as e:
                    logger.warning(f"Could not process {recording}: {e}")

            # Remove empty date directories
            if date_dir.exists() and not any(date_dir.iterdir()):
                date_dir.rmdir()
                logger.info(f"Removed empty directory: {date_dir}")

        if deleted_count > 0:
            logger.info(
                f"Cleanup complete: deleted {deleted_count} files, "
                f"freed {deleted_size / (1024 * 1024):.2f} MB"
            )

        # Also cleanup old thumbnails (keep 24 hours)
        await self.cleanup_old_thumbnails()

    async def cleanup_old_thumbnails(self):
        """Remove thumbnails older than 24 hours."""
        thumbnails_dir = self.data_dir / "thumbnails"
        cutoff_time = datetime.now() - timedelta(hours=24)

        for thumbnail in thumbnails_dir.glob("*.jpg"):
            try:
                mtime = datetime.fromtimestamp(thumbnail.stat().st_mtime)
                if mtime < cutoff_time:
                    thumbnail.unlink()
            except OSError:
                pass

    def get_storage_stats(self) -> dict:
        """Get disk storage statistics."""
        try:
            total, used, free = shutil.disk_usage(self.data_dir)

            # Calculate data directory size
            data_size = self._get_directory_size(self.data_dir)

            # Get recordings size
            recordings_size = self._get_directory_size(self.data_dir / "recordings")

            return {
                "total_gb": round(total / (1024 ** 3), 2),
                "used_gb": round(used / (1024 ** 3), 2),
                "free_gb": round(free / (1024 ** 3), 2),
                "used_percent": round((used / total) * 100, 1),
                "data_size_gb": round(data_size / (1024 ** 3), 2),
                "recordings_size_gb": round(recordings_size / (1024 ** 3), 2),
            }
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {
                "total_gb": 0,
                "used_gb": 0,
                "free_gb": 0,
                "used_percent": 0,
                "data_size_gb": 0,
                "recordings_size_gb": 0,
            }

    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of a directory."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except OSError:
            pass
        return total

    async def broadcast_storage_stats(self):
        """Broadcast storage stats via WebSocket."""
        stats = self.get_storage_stats()
        await self.ws_manager.send_storage_update(
            stats["total_gb"],
            stats["used_gb"],
            stats["free_gb"]
        )

    def get_recordings_count(self) -> int:
        """Get total number of recording files."""
        recordings_dir = self.data_dir / "recordings"
        return sum(1 for _ in recordings_dir.rglob("*.mp4"))
