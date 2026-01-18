import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class RTSPRecorder:
    """Records RTSP stream to 10-minute MP4 segments using FFmpeg."""

    def __init__(
        self,
        rtsp_url: str,
        output_dir: Path,
        ws_manager: ConnectionManager,
        segment_duration: int = 600  # 10 minutes
    ):
        self.rtsp_url = rtsp_url
        self.output_dir = output_dir
        self.ws_manager = ws_manager
        self.segment_duration = segment_duration
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    async def start(self):
        """Start the recording process."""
        if self._running:
            logger.warning("Recorder already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._recording_loop())
        logger.info("RTSP recorder started")
        await self.ws_manager.send_status_update("recorder", "running", "Recording started")

    async def stop(self):
        """Stop the recording process."""
        self._running = False
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("RTSP recorder stopped")
        await self.ws_manager.send_status_update("recorder", "stopped", "Recording stopped")

    def _get_output_pattern(self) -> str:
        """Generate output file pattern for FFmpeg segment muxer."""
        # Organize by date
        date_dir = self.output_dir / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return str(date_dir / "%Y%m%d_%H%M%S.mp4")

    def _build_ffmpeg_command(self) -> list:
        """Build FFmpeg command for segmented recording."""
        return [
            "ffmpeg",
            "-y",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            # Video only - no audio
            "-an",
            # Copy HEVC video directly (no re-encoding needed without audio)
            "-c:v", "copy",
            # Segment output
            "-f", "segment",
            "-segment_time", str(self.segment_duration),
            "-segment_format", "mp4",
            "-segment_format_options", "movflags=+frag_keyframe+empty_moov+default_base_moof",
            "-strftime", "1",
            "-reset_timestamps", "1",
            self._get_output_pattern()
        ]

    async def _recording_loop(self):
        """Main recording loop with auto-reconnection."""
        retry_delay = 5  # seconds

        while self._running:
            try:
                cmd = self._build_ffmpeg_command()
                logger.info(f"Starting FFmpeg recording: {' '.join(cmd)}")

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                await self.ws_manager.send_status_update("recorder", "connected", "Recording in progress")

                # Monitor process
                while self._running and self._process.poll() is None:
                    await asyncio.sleep(1)

                if self._process.returncode is not None and self._process.returncode != 0:
                    stderr = self._process.stderr.read().decode() if self._process.stderr else ""
                    logger.error(f"FFmpeg exited with code {self._process.returncode}: {stderr[-500:]}")

            except Exception as e:
                logger.error(f"Recording error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {retry_delay} seconds...")
                await self.ws_manager.send_status_update(
                    "recorder", "reconnecting",
                    f"Reconnecting in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff

    def get_recordings(self, date: Optional[str] = None) -> list:
        """List all recording files, optionally filtered by date."""
        recordings = []

        if date:
            date_dir = self.output_dir / date
            if date_dir.exists():
                dirs = [date_dir]
            else:
                dirs = []
        else:
            dirs = sorted(self.output_dir.glob("*"), reverse=True)

        for date_dir in dirs:
            if date_dir.is_dir() and date_dir.name != ".":
                for file in sorted(date_dir.glob("*.mp4"), reverse=True):
                    stat = file.stat()
                    recordings.append({
                        "name": file.name,
                        "date": date_dir.name,
                        "path": str(file.relative_to(self.output_dir)),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                    })

        return recordings

    def get_recording_path(self, date: str, filename: str) -> Optional[Path]:
        """Get full path to a recording file."""
        file_path = self.output_dir / date / filename
        if file_path.exists() and file_path.is_file():
            return file_path
        return None

    def delete_recording(self, date: str, filename: str) -> bool:
        """Delete a recording file."""
        file_path = self.output_dir / date / filename
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            # Remove empty date directory
            date_dir = self.output_dir / date
            if date_dir.exists() and not any(date_dir.iterdir()):
                date_dir.rmdir()
            return True
        return False
