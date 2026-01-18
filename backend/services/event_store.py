import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class EventStore:
    """SQLite storage for detection events."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS detection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                confidence REAL NOT NULL,
                thumbnail_path TEXT,
                analysis TEXT,
                analysis_confidence REAL,
                analysis_model TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON detection_events(timestamp)
        """)

        await self._ensure_columns(
            ["analysis", "analysis_confidence", "analysis_model"]
        )

        await self._db.commit()
        logger.info(f"Event store initialized at {self.db_path}")

    async def _ensure_columns(self, columns: List[str]) -> None:
        cursor = await self._db.execute("PRAGMA table_info(detection_events)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for column in columns:
            if column in existing:
                continue
            if column == "analysis":
                col_type = "TEXT"
            elif column == "analysis_model":
                col_type = "TEXT"
            else:
                col_type = "REAL"
            await self._db.execute(
                f"ALTER TABLE detection_events ADD COLUMN {column} {col_type}"
            )

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def add_event(
        self,
        timestamp: datetime,
        confidence: float,
        thumbnail_path: Optional[str] = None,
        analysis: Optional[str] = None,
        analysis_confidence: Optional[float] = None,
        analysis_model: Optional[str] = None
    ) -> int:
        """Add a detection event."""
        async with self._lock:
            cursor = await self._db.execute(
                """
                INSERT INTO detection_events (
                    timestamp,
                    confidence,
                    thumbnail_path,
                    analysis,
                    analysis_confidence,
                    analysis_model
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.isoformat(),
                    confidence,
                    thumbnail_path,
                    analysis,
                    analysis_confidence,
                    analysis_model
                )
            )
            await self._db.commit()
            return cursor.lastrowid

    async def get_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get detection events within a time range."""
        query = "SELECT * FROM detection_events WHERE 1=1"
        params = []

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._lock:
            cursor = await self._db.execute(query, params)
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_graph_data(self, range_minutes: int = 60) -> List[dict]:
        """
        Get detection data aggregated for graph display.
        Returns data points with timestamp and max confidence per minute.
        """
        start_time = datetime.now() - timedelta(minutes=range_minutes)

        query = """
            SELECT
                strftime('%Y-%m-%dT%H:%M:00', timestamp) as minute,
                MAX(confidence) as max_confidence,
                COUNT(*) as count
            FROM detection_events
            WHERE timestamp >= ?
            GROUP BY minute
            ORDER BY minute ASC
        """

        async with self._lock:
            cursor = await self._db.execute(query, (start_time.isoformat(),))
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_recent_events(self, limit: int = 10) -> List[dict]:
        """Get most recent detection events."""
        query = """
            SELECT * FROM detection_events
            ORDER BY timestamp DESC
            LIMIT ?
        """

        async with self._lock:
            cursor = await self._db.execute(query, (limit,))
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_event_count(self, hours: int = 24) -> int:
        """Get total event count in the last N hours."""
        start_time = datetime.now() - timedelta(hours=hours)

        async with self._lock:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM detection_events WHERE timestamp >= ? AND confidence > 0",
                (start_time.isoformat(),)
            )
            row = await cursor.fetchone()

        return row[0] if row else 0

    async def cleanup_old_events(self, retention_hours: int = 48):
        """Delete events older than retention period."""
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM detection_events WHERE timestamp < ?",
                (cutoff_time.isoformat(),)
            )
            await self._db.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old detection events")

        return deleted
