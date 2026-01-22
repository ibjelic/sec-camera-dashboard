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
        analysis_confidence: Optional[float] = None,
        send_gif: bool = False
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
            if runtime_settings.telegram_gif and send_gif:
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
        """Generate and send a 10-second video clip from the detection."""
        try:
            # Notify user that recording is starting
            await self._bot.send_message(
                chat_id=self.chat_id,
                text="Recording 10 second clip..."
            )

            # Record 10 seconds from NOW
            logger.info("Starting 10 second clip recording...")
            clip_path = await self._generate_gif(duration=10)

            if clip_path and clip_path.exists():
                file_size = clip_path.stat().st_size / 1024  # KB
                logger.info(f"Clip generated: {clip_path} ({file_size:.1f} KB)")

                caption = (
                    f"Detection Clip\n"
                    f"Confidence: {confidence:.1f}%\n"
                    f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Send as video (MP4 works better than GIF)
                with open(clip_path, "rb") as f:
                    await self._bot.send_video(
                        chat_id=self.chat_id,
                        video=f,
                        caption=caption,
                        supports_streaming=True
                    )

                # Cleanup
                clip_path.unlink()
                logger.info("Detection clip sent to Telegram")
            else:
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text="Failed to record clip"
                )
                logger.error("Clip generation returned None or file doesn't exist")

        except Exception as e:
            logger.error(f"Failed to send clip: {e}")

    async def _generate_gif(self, duration: int = 10) -> Optional[Path]:
        """Generate MP4 clip from RTSP stream using FFmpeg (better than GIF)."""
        try:
            from backend.config import settings

            # Use MP4 instead of GIF - smaller file, better quality
            output_path = Path(tempfile.mktemp(suffix=".mp4"))

            rtsp_url = settings.rtsp_url_low
            logger.info(f"Recording {duration}s clip from: {rtsp_url}")

            cmd = [
                "ffmpeg",
                "-y",
                "-rtsp_transport", "tcp",
                "-fflags", "+genpts+discardcorrupt",
                "-analyzeduration", "2000000",
                "-probesize", "2000000",
                "-i", rtsp_url,
                "-t", str(duration),
                "-vf", "scale=480:-2",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-an",  # No audio
                "-movflags", "+faststart",
                str(output_path)
            ]

            logger.info(f"FFmpeg command: {' '.join(cmd)}")

            # Use async subprocess for better handling
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=duration + 30
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error("FFmpeg timed out")
                return None

            if process.returncode == 0 and output_path.exists():
                file_size = output_path.stat().st_size
                if file_size > 0:
                    logger.info(f"Clip created successfully: {file_size} bytes")
                    return output_path
                else:
                    logger.error("FFmpeg created empty file")
                    output_path.unlink()
                    return None
            else:
                stderr_text = stderr.decode()[-1000:] if stderr else "No stderr"
                logger.error(f"FFmpeg failed (code {process.returncode}): {stderr_text}")
                if output_path.exists():
                    output_path.unlink()
                return None

        except Exception as e:
            logger.error(f"Clip generation error: {e}")
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

    async def send_test_gif(self) -> bool:
        """Send a test GIF - records next 10 seconds from live stream."""
        if not await self._ensure_bot():
            return False

        try:
            # Notify user that recording is starting
            await self._bot.send_message(
                chat_id=self.chat_id,
                text="Recording 10 second test clip..."
            )

            # Record 10 seconds from NOW
            logger.info("Starting test clip recording (10 seconds)...")
            clip_path = await self._generate_gif(duration=10)

            if clip_path and clip_path.exists():
                file_size = clip_path.stat().st_size / 1024  # KB
                logger.info(f"Test clip generated: {clip_path} ({file_size:.1f} KB)")

                caption = (
                    f"Test Clip\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Duration: 10 seconds"
                )

                with open(clip_path, "rb") as f:
                    await self._bot.send_video(
                        chat_id=self.chat_id,
                        video=f,
                        caption=caption,
                        supports_streaming=True
                    )

                clip_path.unlink()
                logger.info("Test GIF sent successfully")
                return True
            else:
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text="Failed to record test clip - check RTSP stream"
                )
                logger.error("Failed to generate test GIF - clip_path is None or doesn't exist")
                return False

        except Exception as e:
            logger.error(f"Failed to send test GIF: {e}")
            return False
