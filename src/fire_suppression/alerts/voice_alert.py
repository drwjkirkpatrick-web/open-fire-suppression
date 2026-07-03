"""Text-to-speech voice alert system.

# ADD-005 — Voice Alert System (Local TTS)

Provides spoken fire alerts and evacuation instructions using
the Raspberry Pi audio jack. Uses pyttsx3 for offline TTS.

Messages are prioritized and can be interrupted by higher-priority alerts.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class VoicePriority(Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass(order=True)
class VoiceMessage:
    priority: int
    text: str = dataclasses.field(compare=False)
    timestamp: float = dataclasses.field(default_factory=time.time, compare=False)


class VoiceAlertSystem:
    """Local text-to-speech alert system.

    Usage::

        voice = VoiceAlertSystem()
        await voice.speak("Fire detected in the kitchen. Evacuate immediately.",
                         priority=VoicePriority.CRITICAL)
    """

    def __init__(self, rate: int = 150, volume: float = 1.0, *, mock: bool = False) -> None:
        self.rate = rate
        self.volume = volume
        self.mock = mock
        self._queue: asyncio.Queue[VoiceMessage] = asyncio.Queue()
        self._speaking = False
        self._running = False
        self._task: asyncio.Task | None = None
        self._engine = None

        if not mock:
            try:
                import pyttsx3
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", rate)
                self._engine.setProperty("volume", volume)
            except Exception as exc:
                logger.warning("pyttsx3 init failed: %s", exc)
                self.mock = True

    async def start(self) -> None:
        """Start the speech dispatch loop."""
        self._running = True
        self._task = asyncio.create_task(self._speak_loop())
        logger.info("Voice alert system started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def speak(self, text: str, priority: VoicePriority = VoicePriority.MEDIUM) -> None:
        """Queue a message to be spoken."""
        msg = VoiceMessage(priority=priority.value, text=text)
        await self._queue.put(msg)

    async def _speak_loop(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            self._speaking = True
            try:
                if self.mock:
                    logger.info("[VOICE] %s", msg.text)
                    await asyncio.sleep(len(msg.text) * 0.08)  # Simulate speaking time
                else:
                    # pyttsx3 is synchronous — run in thread
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._speak_sync, msg.text)
            except Exception as exc:
                logger.error("Voice alert failed: %s", exc)
            finally:
                self._speaking = False

    def _speak_sync(self, text: str) -> None:
        if self._engine:
            self._engine.say(text)
            self._engine.runAndWait()

    def is_speaking(self) -> bool:
        return self._speaking

    def stop_current(self) -> None:
        """Interrupt current speech (for emergency override)."""
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
