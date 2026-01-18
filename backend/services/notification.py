import asyncio
import io
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from backend.config import runtime_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Telegram notification service for detection alerts."""

    def __init__(self, bot_token: str, chat_id: str, data_dir: Path):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.data_dir = data_dir
        self._bot = None
        self._initialized = False

    async def _ensure_bot(self):
        """Initialize Telegram bot lazily."""
        if self._initialized:
            return self._bot is not None

        if not self.bot_token or self.bot_token == "your_bot_token":
            logger.warning("Telegram bot token not configured")
            self._initialized = True
            return False

        if not self.chat_id or self.chat_id == "your_chat_id":
            logger.warning("Telegram chat ID not configured")
            self._initialized = True
            return False

        try:
            from telegram import Bot
            self._bot = Bot(token=self.bot_token)
            self._initialized = True
            logger.info("Telegram bot initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self._initialized = True
            return False

    async def send_detection_alert(
        self,
        frame: np.ndarray,
        confidence: float,
        timestamp: datetime,
        analysis_text: Optional[str] = None,
        analysis_confidence: Optional[float] = None
    ):
        """Send detection alert with screenshot and optional GIF."""
        if not runtime_settings.telegram_enabled:
            return

        if not await self._ensure_bot():
            return

        try:
            # Send screenshot
            if runtime_settings.telegram_screenshot:
                await self._send_screenshot(frame, confidence, timestamp, analysis_text, analysis_confidence)

            # Generate and send GIF (runs in background)
            if runtime_settings.telegram_gif:
                asyncio.create_task(
                    self._send_detection_gif(confidence, timestamp)
                )

            if analysis_text and not runtime_settings.telegram_screenshot:
                await self._send_analysis_message(analysis_text, analysis_confidence, timestamp)

        except Exception as e:
            logger.error(f"Failed to send detection alert: {e}")

    async def _send_screenshot(
        self,
        frame: np.ndarray,
        confidence: float,
        timestamp: datetime,
        analysis_text: Optional[str] = None,
        analysis_confidence: Optional[float] = None
    ):
        """Send screenshot to Telegram."""
        try:
            # Convert frame to JPEG
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb_frame)

            # Save to buffer
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)

            # Send photo
            confidence_value = analysis_confidence if analysis_confidence is not None else confidence
            caption = (
                f"Person Detected!\n"
                f"Confidence: {confidence_value:.1f}%\n"
                f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if analysis_text:
                trimmed = analysis_text.strip()[:200]
                caption += f"\nAI: {trimmed}"

            await self._bot.send_photo(
                chat_id=self.chat_id,
                photo=buffer,
                caption=caption
            )

            logger.info("Detection screenshot sent to Telegram")

        except Exception as e:
            logger.error(f"Failed to send screenshot: {e}")

    async def _send_analysis_message(
        self,
        analysis_text: str,
        analysis_confidence: Optional[float],
        timestamp: datetime
    ):
        """Send a text-only analysis message."""
        try:
            confidence_line = ""
            if analysis_confidence is not None:
                confidence_line = f"Confidence: {analysis_confidence:.1f}%\n"
            text = (
                "Detection Analysis\n"
                f"{confidence_line}"
                f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{analysis_text.strip()[:400]}"
            )
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text
            )
        except Exception as e:
            logger.error(f"Failed to send analysis message: {e}")

    async def _send_detection_gif(self, confidence: float, timestamp: datetime):
        """Generate and send a 10-second GIF from the detection."""
        try:
            # Wait a bit to capture more footage
            await asyncio.sleep(2)

            # Generate GIF using FFmpeg from RTSP stream
            gif_path = await self._generate_gif(duration=10)

            if gif_path and gif_path.exists():
                caption = (
                    f"Detection Clip\n"
                    f"Confidence: {confidence:.1f}%\n"
                    f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Send as animation
                with open(gif_path, "rb") as f:
                    await self._bot.send_animation(
                        chat_id=self.chat_id,
                        animation=f,
                        caption=caption
                    )

                # Cleanup
                gif_path.unlink()
                logger.info("Detection GIF sent to Telegram")

        except Exception as e:
            logger.error(f"Failed to send GIF: {e}")

    async def _generate_gif(self, duration: int = 10) -> Optional[Path]:
        """Generate GIF from RTSP stream using FFmpeg."""
        try:
            from backend.config import settings

            with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
                output_path = Path(f.name)

            cmd = [
                "ffmpeg",
                "-y",
                "-rtsp_transport", "tcp",
                "-t", str(duration),
                "-i", settings.rtsp_url_low,  # Use low quality stream
                "-vf", "fps=10,scale=480:-1:flags=lanczos",
                "-c:v", "gif",
                str(output_path)
            ]

            # Run FFmpeg
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=duration + 30
                )
            )

            if process.returncode == 0 and output_path.exists():
                return output_path
            else:
                logger.error(f"FFmpeg GIF generation failed: {process.stderr.decode()[-500:]}")
                return None

        except Exception as e:
            logger.error(f"GIF generation error: {e}")
            return None

    async def send_test_message(self) -> bool:
        """Send a test message to verify configuration."""
        if not await self._ensure_bot():
            return False

        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text="Security Camera Dashboard - Test notification\nConnection successful!"
            )
            logger.info("Test message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send test message: {e}")
            return False

    async def send_startup_message(self):
        """Send a startup notification."""
        if not runtime_settings.telegram_enabled:
            return

        if not await self._ensure_bot():
            return

        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text="Security Camera Dashboard started\nMonitoring active."
            )
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
