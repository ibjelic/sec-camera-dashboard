import asyncio
import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from backend.config import runtime_settings, settings
from backend.services.event_store import EventStore
from backend.services.notification import NotificationService
from backend.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

# MobileNet-SSD class labels (COCO)
MOBILENET_CLASSES = [
    "background", "person", "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat", "traffic light", "fire hydrant", "street sign",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse",
    "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "hat", "backpack",
    "umbrella", "shoe", "eye glasses", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "plate", "wine glass",
    "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "mirror", "dining table", "window", "desk",
    "toilet", "door", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "blender", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
]

# Classes we care about for security alerts
ALERT_CLASSES = {"person", "cat", "dog", "car", "motorcycle", "truck", "bird"}


class PersonDetector:
    """Motion + MobileNet-SSD based detection for Orange Pi / ARM devices.

    Uses MOG2 background subtraction for robust motion detection with:
    - Consecutive frame confirmation to reduce false positives
    - Adaptive sampling rate (faster when motion detected)
    """

    MODEL_URL = "https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"
    PROTOTXT_URL = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt"

    # MobileNet-SSD VOC classes (different from COCO)
    VOC_CLASSES = [
        "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus",
        "car", "cat", "chair", "cow", "diningtable", "dog", "horse", "motorbike",
        "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"
    ]
    VOC_ALERT_CLASSES = {"person", "cat", "dog", "car", "motorbike", "bird"}

    # Sampling rate constants
    FAST_INTERVAL = 0.2    # 5 FPS when motion detected
    NORMAL_INTERVAL = 0.5  # 2 FPS normal monitoring
    IDLE_INTERVAL = 1.0    # 1 FPS when idle for a while

    def __init__(
        self,
        rtsp_url: str,
        event_store: EventStore,
        notification_service: NotificationService,
        ws_manager: ConnectionManager,
        thumbnails_dir: Path,
        consecutive_frames_required: int = 1  # Faster detection with single frame
    ):
        self.rtsp_url = rtsp_url
        self.event_store = event_store
        self.notification_service = notification_service
        self.ws_manager = ws_manager
        self.thumbnails_dir = thumbnails_dir
        self.consecutive_frames_required = consecutive_frames_required
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_detection_time: Optional[datetime] = None
        self._net: Optional[cv2.dnn.Net] = None
        self._model_dir = Path("data/models")
        self._model_loaded = False

        # MOG2 background subtractor (better than frame differencing)
        self._bg_subtractor: Optional[cv2.BackgroundSubtractorMOG2] = None

        # Consecutive frame tracking
        self._motion_frame_count = 0
        self._last_motion_time: Optional[datetime] = None

        # Adaptive sampling
        self._current_interval = self.NORMAL_INTERVAL

        # Cached kernel for morphological operations (optimization)
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    @property
    def is_running(self) -> bool:
        return self._running

    def _download_model(self):
        """Download MobileNet-SSD model files if not present."""
        self._model_dir.mkdir(parents=True, exist_ok=True)

        caffemodel_path = self._model_dir / "mobilenet_ssd.caffemodel"
        prototxt_path = self._model_dir / "mobilenet_ssd.prototxt"

        if not caffemodel_path.exists():
            logger.info("Downloading MobileNet-SSD model (23MB)...")
            try:
                urllib.request.urlretrieve(self.MODEL_URL, caffemodel_path)
                logger.info("Model downloaded successfully")
            except Exception as e:
                logger.error(f"Failed to download model: {e}")
                return False

        if not prototxt_path.exists():
            logger.info("Downloading MobileNet-SSD prototxt...")
            try:
                urllib.request.urlretrieve(self.PROTOTXT_URL, prototxt_path)
                logger.info("Prototxt downloaded successfully")
            except Exception as e:
                logger.error(f"Failed to download prototxt: {e}")
                return False

        return True

    def _load_model(self):
        """Load MobileNet-SSD model for object detection."""
        if self._model_loaded:
            return self._net is not None

        caffemodel_path = self._model_dir / "mobilenet_ssd.caffemodel"
        prototxt_path = self._model_dir / "mobilenet_ssd.prototxt"

        if not caffemodel_path.exists() or not prototxt_path.exists():
            if not self._download_model():
                logger.warning("Model not available, using motion detection only")
                self._model_loaded = True
                return False

        try:
            self._net = cv2.dnn.readNetFromCaffe(
                str(prototxt_path),
                str(caffemodel_path)
            )
            # Use CPU backend (works on Orange Pi)
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self._model_loaded = True
            logger.info("MobileNet-SSD model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._model_loaded = True
            return False

    async def start(self):
        """Start the detection service."""
        if self._running:
            logger.warning("Detector already running")
            return

        # Initialize MOG2 background subtractor
        # history=500: Use last 500 frames for background model
        # varThreshold=12: Sensitivity (lower = more sensitive)
        # detectShadows=True: Detect and mark shadows separately
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=12,
            detectShadows=True
        )

        # Load model in background
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model)

        self._running = True
        self._task = asyncio.create_task(self._detection_loop())
        logger.info("Person detector started with MOG2 background subtraction")
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
        """Main detection loop - samples frames from RTSP stream with adaptive rate."""
        retry_delay = 5
        cap = None

        while self._running:
            try:
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer for real-time

                if not cap.isOpened():
                    raise RuntimeError("Failed to open RTSP stream")

                logger.info("Connected to RTSP stream for detection")
                await self.ws_manager.send_status_update("detector", "connected", "Analyzing stream")
                retry_delay = 5

                # Reset background subtractor on reconnect
                if self._bg_subtractor:
                    self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                        history=500, varThreshold=12, detectShadows=True
                    )

                while self._running and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning("Failed to read frame, reconnecting...")
                        break

                    await self._process_frame(frame)

                    # Adaptive sleep based on motion state
                    await asyncio.sleep(self._current_interval)

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
        """Process a single frame for detection with consecutive frame confirmation."""
        try:
            now = datetime.now()

            # Step 1: Compute motion using MOG2 background subtraction
            motion_score, is_global = self._compute_motion_score(frame)

            if is_global:
                # Global change (lighting, camera movement) - reset motion count
                self._motion_frame_count = 0
                self._update_sampling_rate(has_motion=False, now=now)
                return

            threshold = runtime_settings.detection_threshold

            if motion_score >= threshold:
                # Motion detected - increment consecutive frame counter
                self._motion_frame_count += 1
                self._update_sampling_rate(has_motion=True, now=now)

                # Only trigger detection after N consecutive frames with motion
                if self._motion_frame_count >= self.consecutive_frames_required:
                    # Step 2: Run object detection (expensive but motion-confirmed)
                    detections = await self._detect_objects(frame)

                    if detections:
                        # Found relevant objects
                        await self._handle_detection(frame, motion_score, detections)
                        self._last_motion_time = now
                    elif motion_score >= 70:
                        # High motion but no objects - still log
                        await self._handle_detection(frame, motion_score, [])
                        self._last_motion_time = now
            else:
                # No significant motion - reset counter
                self._motion_frame_count = 0
                self._update_sampling_rate(has_motion=False, now=now)

        except Exception as e:
            logger.error(f"Frame processing error: {e}")

    def _update_sampling_rate(self, has_motion: bool, now: datetime):
        """Adjust sampling rate based on motion activity."""
        if has_motion:
            # Motion detected - sample faster
            self._current_interval = self.FAST_INTERVAL
            self._last_motion_time = now
        elif self._last_motion_time:
            # No motion - check how long since last motion
            idle_seconds = (now - self._last_motion_time).total_seconds()
            if idle_seconds > 30:
                # Idle for 30+ seconds - slow down to save CPU
                self._current_interval = self.IDLE_INTERVAL
            elif idle_seconds > 5:
                # Idle for 5-30 seconds - normal rate
                self._current_interval = self.NORMAL_INTERVAL
            else:
                # Recently had motion - stay fast
                self._current_interval = self.FAST_INTERVAL
        else:
            self._current_interval = self.NORMAL_INTERVAL

    def _compute_motion_score(self, frame: np.ndarray) -> tuple[float, bool]:
        """Compute motion score using MOG2 background subtraction.

        MOG2 advantages over simple frame differencing:
        - Adapts to gradual lighting changes
        - Handles shadows separately (marked as gray, not white)
        - Builds a statistical model of the background
        - More robust to noise
        """
        if self._bg_subtractor is None:
            return 0.0, False

        # Downscale frame for faster motion detection (optimization)
        height, width = frame.shape[:2]
        scale = 0.5 if width > 640 else 1.0
        if scale < 1.0:
            small_frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            small_frame = frame

        # Apply MOG2 background subtraction
        # Returns: 255 = foreground, 127 = shadow, 0 = background
        fg_mask = self._bg_subtractor.apply(small_frame)

        # Remove shadows (keep only definite foreground)
        # Shadows are marked as 127, foreground as 255
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Noise removal with morphological operations (using cached kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._morph_kernel)   # Remove small noise
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self._morph_kernel)  # Fill small holes
        fg_mask = cv2.dilate(fg_mask, self._morph_kernel, iterations=2)           # Expand regions

        height, width = fg_mask.shape[:2]
        frame_area = float(height * width)

        if frame_area <= 0:
            return 0.0, False

        # Find contours in the foreground mask
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter small contours (noise) - minimum 0.1% of frame
        min_area = frame_area * 0.001
        total_area = 0.0
        max_area = 0.0
        max_rect = None
        valid_contours = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            valid_contours += 1
            total_area += area
            if area > max_area:
                max_area = area
                max_rect = cv2.boundingRect(contour)

        area_ratio = total_area / frame_area

        # Detect global changes (camera movement, major lighting shift)
        # These cause the entire frame to change, not just local motion
        band_like = False
        if max_rect is not None:
            rect_width = max_rect[2]
            rect_height = max_rect[3]
            # Large horizontal or vertical bands suggest camera movement
            band_like = (rect_width > width * 0.85 and rect_height > height * 0.25) or \
                        (rect_height > height * 0.85 and rect_width > width * 0.25)

        global_change = (
            area_ratio > 0.5 or                    # More than 50% of frame changed
            max_area > frame_area * 0.4 or         # Single huge change region
            band_like or                           # Band-like pattern
            valid_contours > 50                    # Too many separate regions (noise/shake)
        )

        if global_change:
            return 0.0, True

        # Convert area ratio to 0-100 score
        # More sensitive than before: 10% coverage = 100 score
        motion_score = min(100.0, area_ratio * 1000.0)
        return motion_score, False

    async def _detect_objects(self, frame: np.ndarray) -> list[dict]:
        """Run MobileNet-SSD object detection."""
        if self._net is None:
            return []

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._run_detection, frame)
        except Exception as e:
            logger.error(f"Object detection error: {e}")
            return []

    def _run_detection(self, frame: np.ndarray) -> list[dict]:
        """Synchronous detection using MobileNet-SSD."""
        height, width = frame.shape[:2]

        # Prepare input blob (300x300 for MobileNet-SSD)
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)),
            0.007843,  # scale factor
            (300, 300),
            127.5  # mean subtraction
        )

        self._net.setInput(blob)
        detections_raw = self._net.forward()

        detections = []
        for i in range(detections_raw.shape[2]):
            confidence = detections_raw[0, 0, i, 2]

            if confidence < 0.25:  # Minimum confidence threshold (lowered for better detection)
                continue

            class_id = int(detections_raw[0, 0, i, 1])
            if class_id >= len(self.VOC_CLASSES):
                continue

            class_name = self.VOC_CLASSES[class_id]

            # Only alert on relevant classes
            if class_name not in self.VOC_ALERT_CLASSES:
                continue

            # Get bounding box
            box = detections_raw[0, 0, i, 3:7] * np.array([width, height, width, height])
            (x1, y1, x2, y2) = box.astype("int")

            detections.append({
                "class": class_name,
                "confidence": float(confidence) * 100,
                "box": (x1, y1, x2, y2)
            })

        return detections

    async def _handle_detection(self, frame: np.ndarray, motion_score: float, detections: list[dict]):
        """Handle a detection event."""
        now = datetime.now()

        # Build detection summary
        if detections:
            classes = [d["class"] for d in detections]
            max_conf = max(d["confidence"] for d in detections)
            summary = f"Detected: {', '.join(set(classes))}"
            confidence = max_conf
            has_person = any(d["class"] == "person" for d in detections)
            has_animal = any(d["class"] in ("cat", "dog", "bird") for d in detections)
        else:
            summary = f"Motion detected ({motion_score:.0f}%)"
            confidence = motion_score
            has_person = False
            has_animal = False

        # Importance scoring (5 = critical, 4 = high, 3 = medium, 2 = low, 1 = minimal)
        if has_person and confidence >= 70:
            importance = 5  # High-confidence person detection
        elif has_person:
            importance = 4  # Person detected
        elif has_animal:
            importance = 2
        else:
            importance = 1

        # GIF should only be sent for importance >= 4
        should_send_gif = importance >= 4

        # Save thumbnail
        thumbnail_path = await self._save_thumbnail(frame, now, detections)
        thumbnail_relative = thumbnail_path.name if thumbnail_path else None

        # Store event
        await self.event_store.add_event(
            timestamp=now,
            confidence=confidence,
            thumbnail_path=thumbnail_relative,
            analysis=summary,
            analysis_confidence=confidence,
            analysis_model="MobileNet-SSD",
            analysis_importance=importance,
            analysis_send_gif=should_send_gif
        )

        # Broadcast via WebSocket
        await self.ws_manager.send_detection_event(
            timestamp=now.isoformat(),
            confidence=confidence,
            thumbnail_path=f"/thumbnails/{thumbnail_relative}" if thumbnail_relative else None
        )

        logger.info(f"Detection: {summary} | Confidence: {confidence:.1f}% | Importance: {importance}")

        # Send notification (with cooldown)
        if runtime_settings.telegram_enabled:
            cooldown = runtime_settings.notification_cooldown_seconds
            if self._last_detection_time is None or \
               (now - self._last_detection_time).total_seconds() >= cooldown:

                # Only notify for person or high-importance events
                if has_person or importance >= 3:
                    self._last_detection_time = now
                    asyncio.create_task(
                        self.notification_service.send_detection_alert(
                            frame=frame,
                            confidence=confidence,
                            timestamp=now,
                            analysis_text=summary,
                            analysis_confidence=confidence,
                            send_gif=should_send_gif  # Only send GIF for importance >= 4
                        )
                    )

    async def _save_thumbnail(self, frame: np.ndarray, timestamp: datetime, detections: list[dict]) -> Optional[Path]:
        """Save detection frame as thumbnail with bounding boxes."""
        try:
            # Draw bounding boxes on frame
            annotated = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = det["box"]
                color = (0, 255, 0) if det["class"] == "person" else (255, 165, 0)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                label = f"{det['class']}: {det['confidence']:.0f}%"
                cv2.putText(annotated, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = self.thumbnails_dir / filename

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: Image.fromarray(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)).save(
                    filepath, "JPEG", quality=85
                )
            )

            return filepath

        except Exception as e:
            logger.error(f"Failed to save thumbnail: {e}")
            return None

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get a single frame from the stream."""
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
