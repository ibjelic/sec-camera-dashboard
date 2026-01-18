import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from backend.config import runtime_settings, settings
from backend.services.event_store import EventStore
from backend.services.notification import NotificationService
from backend.services.openrouter_client import OpenRouterClient
from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class PersonDetector:
    """Motion-triggered analysis with OpenRouter person detection."""

    def __init__(
        self,
        rtsp_url: str,
        event_store: EventStore,
        notification_service: NotificationService,
        ws_manager: ConnectionManager,
        thumbnails_dir: Path,
        sample_fps: float = 2.0  # Sample 2 frames per second
    ):
        self.rtsp_url = rtsp_url
        self.event_store = event_store
        self.notification_service = notification_service
        self.ws_manager = ws_manager
        self.thumbnails_dir = thumbnails_dir
        self.sample_interval = 1.0 / sample_fps
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_detection_time: Optional[datetime] = None
        self._prev_gray: Optional[np.ndarray] = None
        self._openrouter = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            daily_limit=settings.openrouter_daily_limit,
            min_interval_seconds=settings.openrouter_min_interval_seconds
        )
        self._analysis_prompt = (
            "Analyze this security camera frame. "
            "Is there a person in view? Describe the scene briefly."
        )

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        """Start the detection service."""
        if self._running:
            logger.warning("Detector already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
        logger.info("Person detector started")
        await self.ws_manager.send_status_update("detector", "running", "Detection active")

    async def stop(self):
        """Stop the detection service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Person detector stopped")
        await self.ws_manager.send_status_update("detector", "stopped", "Detection stopped")

    async def _detection_loop(self):
        """Main detection loop - samples frames from RTSP stream."""
        retry_delay = 5
        cap = None

        while self._running:
            try:
                # Open video capture
                cap = cv2.VideoCapture(self.rtsp_url)
                if not cap.isOpened():
                    raise RuntimeError("Failed to open RTSP stream")

                logger.info("Connected to RTSP stream for detection")
                await self.ws_manager.send_status_update("detector", "connected", "Analyzing stream")
                retry_delay = 5

                while self._running and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning("Failed to read frame, reconnecting...")
                        break

                    # Run detection
                    await self._process_frame(frame)

                    # Wait for next sample
                    await asyncio.sleep(self.sample_interval)

            except Exception as e:
                logger.error(f"Detection error: {e}")

            finally:
                if cap:
                    cap.release()

            if self._running:
                logger.info(f"Reconnecting detector in {retry_delay} seconds...")
                await self.ws_manager.send_status_update(
                    "detector", "reconnecting",
                    f"Reconnecting in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def _process_frame(self, frame: np.ndarray):
        """Process a single frame for motion-based detection."""
        try:
            motion_score = self._compute_motion_score(frame)
            if motion_score < runtime_settings.detection_threshold:
                return

            await self._handle_detection(frame, motion_score)

        except Exception as e:
            logger.error(f"Frame processing error: {e}")

    def _compute_motion_score(self, frame: np.ndarray) -> float:
        """Compute a simple motion score based on frame differencing."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return 0.0

        frame_delta = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray

        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        changed = cv2.countNonZero(thresh)
        total = thresh.shape[0] * thresh.shape[1]
        changed_ratio = changed / float(total) if total else 0.0

        return min(100.0, changed_ratio * 2000.0)

    async def _analyze_frame(self, frame: np.ndarray) -> dict:
        """Send the frame to OpenRouter for analysis."""
        try:
            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return {
                    "summary": "Failed to encode frame.",
                    "person_detected": None,
                    "confidence": 0,
                    "model": settings.openrouter_model,
                    "error": "encode_failed",
                }

            image_b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._openrouter.analyze_image_base64(image_b64, self._analysis_prompt)
            )
        except Exception as e:
            logger.error(f"OpenRouter analysis error: {e}")
            return {
                "summary": "OpenRouter analysis failed.",
                "person_detected": None,
                "confidence": 0,
                "model": settings.openrouter_model,
                "error": "analysis_failed",
            }

    async def _handle_detection(self, frame: np.ndarray, confidence: float):
        """Handle a positive detection."""
        now = datetime.now()

        # Save thumbnail
        thumbnail_path = await self._save_thumbnail(frame, now)
        thumbnail_relative = thumbnail_path.name if thumbnail_path else None

        analysis = await self._analyze_frame(frame)
        analysis_text = analysis.get("summary") or ""
        analysis_confidence = analysis.get("confidence")
        analysis_model = analysis.get("model")
        person_detected = analysis.get("person_detected")
        analysis_error = analysis.get("error")

        if not analysis_text:
            analysis_text = f"Motion detected ({confidence:.1f}% change)."
        elif analysis_error == "rate_limited":
            analysis_text = f"{analysis_text} Motion: {confidence:.1f}%."

        analysis_confidence_value = None
        if analysis_confidence is not None:
            try:
                analysis_confidence_value = float(analysis_confidence)
            except (TypeError, ValueError):
                analysis_confidence_value = None

        display_confidence = 0.0
        if person_detected is True and analysis_confidence_value is not None:
            display_confidence = analysis_confidence_value

        # Store event
        await self.event_store.add_event(
            timestamp=now,
            confidence=display_confidence,
            thumbnail_path=thumbnail_relative,
            analysis=analysis_text,
            analysis_confidence=analysis_confidence_value,
            analysis_model=analysis_model
        )

        # Broadcast via WebSocket
        await self.ws_manager.send_detection_event(
            timestamp=now.isoformat(),
            confidence=display_confidence,
            thumbnail_path=f"/thumbnails/{thumbnail_relative}" if thumbnail_relative else None
        )

        logger.info(
            f"Motion {confidence:.1f}% | "
            f"Person={person_detected} | "
            f"AI {analysis_confidence_value}%"
        )

        # Send notification (with cooldown check)
        if runtime_settings.telegram_enabled:
            cooldown = runtime_settings.notification_cooldown_seconds
            if self._last_detection_time is None or \
               (now - self._last_detection_time).total_seconds() >= cooldown:
                self._last_detection_time = now
                if person_detected is True:
                    asyncio.create_task(
                        self.notification_service.send_detection_alert(
                            frame=frame,
                            confidence=display_confidence,
                            timestamp=now,
                            analysis_text=analysis_text,
                            analysis_confidence=analysis_confidence_value
                        )
                    )

    async def _save_thumbnail(self, frame: np.ndarray, timestamp: datetime) -> Optional[Path]:
        """Save detection frame as thumbnail."""
        try:
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = self.thumbnails_dir / filename

            # Convert BGR to RGB and save
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(
                    filepath, "JPEG", quality=85
                )
            )

            return filepath

        except Exception as e:
            logger.error(f"Failed to save thumbnail: {e}")
            return None

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get a single frame from the stream (for manual snapshot)."""
        try:
            cap = cv2.VideoCapture(self.rtsp_url)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret:
                    return frame
        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
        return None
