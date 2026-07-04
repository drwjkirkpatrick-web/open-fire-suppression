"""V7-006 — Voice Command Interface

Offline wake-word detection and command parsing for hands-free system control.
Supports "status", "test", "arm", "disarm", "evacuate", and "all clear" in
English and Swahili. Mock mode returns deterministic parses for CI.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class VoiceCommand(Enum):
    STATUS = "status"
    TEST = "test"
    ARM = "arm"
    DISARM = "disarm"
    EVACUATE = "evacuate"
    ALL_CLEAR = "all_clear"
    SILENCE = "silence"
    UNKNOWN = "unknown"


_WAKEWORDS = ["firebot", "kijiboti", "system", "mfumo"]

_COMMAND_MAP: dict[str, VoiceCommand] = {
    # English
    "status": VoiceCommand.STATUS,
    "state": VoiceCommand.STATUS,
    "test": VoiceCommand.TEST,
    "arm": VoiceCommand.ARM,
    "activate": VoiceCommand.ARM,
    "disarm": VoiceCommand.DISARM,
    "deactivate": VoiceCommand.DISARM,
    "evacuate": VoiceCommand.EVACUATE,
    "evac": VoiceCommand.EVACUATE,
    "all clear": VoiceCommand.ALL_CLEAR,
    "clear": VoiceCommand.ALL_CLEAR,
    "silence": VoiceCommand.SILENCE,
    "quiet": VoiceCommand.SILENCE,
    # Swahili
    "hali": VoiceCommand.STATUS,
    "jaribio": VoiceCommand.TEST,
    "amsha": VoiceCommand.ARM,
    "zima": VoiceCommand.DISARM,
    "ondoka": VoiceCommand.EVACUATE,
    "salama": VoiceCommand.ALL_CLEAR,
    "nyamaza": VoiceCommand.SILENCE,
}


@dataclass
class VoiceCommandResult:
    command: VoiceCommand
    confidence: float
    lang: str
    raw: str
    timestamp: float
    requires_auth: bool = False


class VoiceCommandInterface:
    """Offline voice command parser with wake-word support."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("voice_command")
        self.confidence_threshold = float(cfg.get("confidence_threshold", 0.6))
        self.auth_commands = set(cfg.get("auth_commands", ["arm", "disarm", "evacuate", "all_clear"]))

    def has_wake_word(self, transcript: str) -> bool:
        lowered = transcript.lower()
        return any(w in lowered for w in _WAKEWORDS)

    def parse(self, transcript: str, lang: str = "en") -> VoiceCommandResult:
        lowered = transcript.lower()
        # Strip wake word if present
        for w in _WAKEWORDS:
            lowered = re.sub(rf"\b{w}\b", "", lowered)
        lowered = lowered.strip(",.!? ")

        # Direct command match
        for phrase, cmd in _COMMAND_MAP.items():
            if phrase in lowered:
                confidence = 0.95 if phrase in lowered.split() else 0.75
                if self.mock:
                    confidence = 0.99
                return VoiceCommandResult(
                    command=cmd,
                    confidence=confidence,
                    lang=lang,
                    raw=transcript,
                    timestamp=time.time(),
                    requires_auth=cmd.value in self.auth_commands,
                )

        return VoiceCommandResult(
            command=VoiceCommand.UNKNOWN,
            confidence=0.0,
            lang=lang,
            raw=transcript,
            timestamp=time.time(),
        )

    def process(self, transcript: str, lang: str = "en") -> dict[str, Any]:
        if not self.has_wake_word(transcript):
            return {"recognized": False, "reason": "no_wake_word", "raw": transcript}
        result = self.parse(transcript, lang)
        if result.confidence < self.confidence_threshold:
            return {"recognized": False, "reason": "low_confidence", "raw": transcript}
        return {
            "recognized": True,
            "command": result.command.value,
            "lang": result.lang,
            "confidence": result.confidence,
            "requires_auth": result.requires_auth,
            "raw": result.raw,
            "timestamp": result.timestamp,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-006",
            "healthy": True,
            "confidence_threshold": self.confidence_threshold,
            "auth_commands": list(self.auth_commands),
            "mock": self.mock,
        }
