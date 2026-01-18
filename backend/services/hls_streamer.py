import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class HLSStreamer:
    """Converts RTSP stream to HLS for web playback."""

    def __init__(
        self,
        rtsp_url: str,
        output_dir: Path,
        ws_manager: ConnectionManager,
        segment_duration: int = 2,  # 2 seconds for low latency
        playlist_size: int = 5
    ):
        self.rtsp_url = rtsp_url
        self.output_dir = output_dir
        self.ws_manager = ws_manager
        self.segment_duration = segment_duration
        self.playlist_size = playlist_size
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    async def start(self):
        """Start the HLS streaming process."""
        if self._running:
            logger.warning("HLS streamer already running")
            return

        # Clean old HLS files
        self._cleanup_old_segments()

        self._running = True
        self._task = asyncio.create_task(self._streaming_loop())
        logger.info("HLS streamer started")
        await self.ws_manager.send_status_update("hls_streamer", "running", "Streaming started")

    async def stop(self):
        """Stop the HLS streaming process."""
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

        self._cleanup_old_segments()
        logger.info("HLS streamer stopped")
        await self.ws_manager.send_status_update("hls_streamer", "stopped", "Streaming stopped")

    def _cleanup_old_segments(self):
        """Remove old HLS segments and playlist."""
        for file in self.output_dir.glob("*.ts"):
            file.unlink()
        for file in self.output_dir.glob("*.m3u8"):
            file.unlink()

    def _build_ffmpeg_command(self) -> list:
        """Build FFmpeg command for HLS streaming."""
        playlist_path = self.output_dir / "stream.m3u8"
        segment_path = self.output_dir / "segment%03d.ts"

        return [
            "ffmpeg",
            "-y",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            # Video encoding - re-encode for HLS compatibility
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-crf", "28",
            "-g", str(self.segment_duration * 25),  # GOP size = segment * fps
            "-sc_threshold", "0",
            # Audio
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            # HLS output
            "-f", "hls",
            "-hls_time", str(self.segment_duration),
            "-hls_list_size", str(self.playlist_size),
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", str(segment_path),
            str(playlist_path)
        ]

    async def _streaming_loop(self):
        """Main streaming loop with auto-reconnection."""
        retry_delay = 5

        while self._running:
            try:
                cmd = self._build_ffmpeg_command()
                logger.info(f"Starting FFmpeg HLS: {' '.join(cmd)}")

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                await self.ws_manager.send_status_update("hls_streamer", "connected", "Live stream active")

                # Monitor process
                while self._running and self._process.poll() is None:
                    await asyncio.sleep(1)

                if self._process.returncode is not None and self._process.returncode != 0:
                    stderr = self._process.stderr.read().decode() if self._process.stderr else ""
                    logger.error(f"FFmpeg HLS exited with code {self._process.returncode}: {stderr[-500:]}")

            except Exception as e:
                logger.error(f"HLS streaming error: {e}")

            if self._running:
                logger.info(f"Reconnecting HLS in {retry_delay} seconds...")
                await self.ws_manager.send_status_update(
                    "hls_streamer", "reconnecting",
                    f"Reconnecting in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def get_playlist_path(self) -> Path:
        """Get path to HLS playlist."""
        return self.output_dir / "stream.m3u8"

    def is_playlist_ready(self) -> bool:
        """Check if HLS playlist is available."""
        return self.get_playlist_path().exists()
