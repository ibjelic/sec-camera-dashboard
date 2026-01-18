import asyncio
import json
from typing import Set

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(message_json)
                except Exception:
                    disconnected.add(connection)

            # Remove disconnected clients
            self.active_connections -= disconnected

    async def send_detection_event(self, timestamp: str, confidence: float, thumbnail_path: str = None):
        """Broadcast a detection event."""
        await self.broadcast({
            "type": "detection",
            "data": {
                "timestamp": timestamp,
                "confidence": confidence,
                "thumbnail": thumbnail_path
            }
        })

    async def send_status_update(self, service: str, status: str, message: str = ""):
        """Broadcast a service status update."""
        await self.broadcast({
            "type": "status",
            "data": {
                "service": service,
                "status": status,
                "message": message
            }
        })

    async def send_storage_update(self, total_gb: float, used_gb: float, free_gb: float):
        """Broadcast storage statistics."""
        await self.broadcast({
            "type": "storage",
            "data": {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb
            }
        })


# Global instance
ws_manager = ConnectionManager()
