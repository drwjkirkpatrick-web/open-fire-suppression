"""Pi Camera Module 3 video capture driver.

# S010 — Pi Camera Module 3 Capture
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PiCameraSensor(BaseSensor):
    """Raspberry Pi Camera Module 3 via picamera2.

    Captures frames for video-based fire and smoke detection.
    Uses OpenCV-compatible NumPy arrays for downstream processing.
    """

    def __init__(
        self,
        name: str = "picamera",
        *,
        resolution: tuple[int, int] = (1920, 1080),
        fps: int = 10,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.resolution = resolution
        self.fps = fps
        self._camera = None
        self._frame_count = 0
        self._last_frame = None

        if not mock:
            try:
                from picamera2 import Picamera2
                self._camera = Picamera2()
                config = self._camera.create_video_configuration(
                    main={"size": resolution, "format": "RGB888"}
                )
                self._camera.configure(config)
                self._camera.start()
                logger.info("Pi Camera started at %s @ %d fps", resolution, fps)
            except Exception as exc:
                logger.error("Pi Camera init failed: %s", exc)
                self._camera = None

    async def read(self) -> SensorReading:
        if self.mock:
            import numpy as np

            # Generate a synthetic frame with a flame-colored region
            frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
            # Gray background (room)
            frame[:, :] = [128, 128, 128]
            # Orange/red flame region
            cy, cx = self.resolution[1] // 2, self.resolution[0] // 2
            frame[cy - 50 : cy + 50, cx - 50 : cx + 50] = [50, 100, 255]
            self._last_frame = frame
            self._frame_count += 1
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "frame_number": self._frame_count,
                    "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
                    "fps_target": self.fps,
                },
                raw=frame,
                unit="frame",
            )

        if self._camera is None:
            raise RuntimeError("Pi Camera not initialized")

        try:
            import numpy as np

            frame = self._camera.capture_array()
            self._last_frame = frame
            self._frame_count += 1

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "frame_number": self._frame_count,
                    "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
                    "fps_target": self.fps,
                },
                raw=frame,
                unit="frame",
            )

        except Exception as exc:
            logger.error("Pi Camera read error: %s", exc)
            raise

    async def capture_jpeg(self) -> bytes | None:
        """Capture a single JPEG image (for event logging)."""
        if self.mock:
            return b"\xff\xd8\xff\xe0mock_jpeg\xff\xd9"
        if self._camera is None:
            return None
        try:
            from picamera2 import Picamera2
            return self._camera.capture_buffer({"format": "JPEG"})
        except Exception as exc:
            logger.error("Pi Camera JPEG capture error: %s", exc)
            return None

    async def close(self) -> None:
        if self._camera is not None:
            try:
                self._camera.stop()
                self._camera.close()
            except Exception:
                pass
            self._camera = None
        self._closed = True
