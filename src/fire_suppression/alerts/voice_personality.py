"""V9-007 — Voice Alert Personality Registry

Maps remedy personalities to alert/evacuation tone modifiers and sample phrases.
Operators can select which personality drives fire alerts and which guides
evacuation.

Default pairing:
- Alerts: *Aconitum Napellus* (panic responder) — urgent, commanding.
- Evacuation guidance: *Phosphorus* (charismatic communicator) — warm, clear.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VoicePersonality:
    """A remedy-inspired voice persona."""

    name: str
    tone: str
    rate_modifier: float  # Multiplier on base TTS rate
    volume_modifier: float  # Multiplier on base volume
    alert_prefix: str
    evacuation_prefix: str
    sample_phrases: dict[str, str]


class VoicePersonalityRegistry:
    """Register and select voice personalities for fire alerts."""

    PERSONALITIES: dict[str, VoicePersonality] = {
        "Aconitum Napellus": VoicePersonality(
            name="Aconitum Napellus",
            tone="urgent_commanding",
            rate_modifier=1.3,
            volume_modifier=1.0,
            alert_prefix="EMERGENCY!",
            evacuation_prefix="GO NOW!",
            sample_phrases={
                "en": "Fire confirmed. Leave the building immediately by the nearest exit.",
                "sw": "Moto imethibitishwa. Toka jengoni mara moja kupitia mlango wa karibu.",
            },
        ),
        "Phosphorus": VoicePersonality(
            name="Phosphorus",
            tone="warm_clear",
            rate_modifier=1.0,
            volume_modifier=0.95,
            alert_prefix="Attention please",
            evacuation_prefix="Please move calmly",
            sample_phrases={
                "en": "A fire has been detected. Please evacuate calmly and use the nearest exit.",
                "sw": "Moto umebainishwa. Tafadhali toka kwa utulivu na utumie mlango wa karibu.",
            },
        ),
        "Pulsatilla Pratensis": VoicePersonality(
            name="Pulsatilla Pratensis",
            tone="gentle_reassuring",
            rate_modifier=0.9,
            volume_modifier=0.9,
            alert_prefix="Please listen",
            evacuation_prefix="Let’s go together",
            sample_phrases={
                "en": "We need to leave now. Hold hands and use the nearest safe exit.",
                "sw": "Tunahitaji kutoka sasa. Shikana mikono na utumie mlango salama wa karibu.",
            },
        ),
        "Ignatia Amara": VoicePersonality(
            name="Ignatia Amara",
            tone="expressive_emphatic",
            rate_modifier=1.1,
            volume_modifier=1.0,
            alert_prefix="This is important",
            evacuation_prefix="Please, with care",
            sample_phrases={
                "en": "Fire alert. Take a breath and walk quickly to the nearest exit.",
                "sw": "Tahadhari ya moto. Vuta pumzi na tembea kwa haraka kuelekea mlango wa karibu.",
            },
        ),
    }

    DEFAULT_ALERT = "Aconitum Napellus"
    DEFAULT_EVACUATION = "Phosphorus"

    def __init__(
        self,
        alert_personality: str | None = None,
        evacuation_personality: str | None = None,
    ) -> None:
        self.alert_personality = self._validate(alert_personality or self.DEFAULT_ALERT)
        self.evacuation_personality = self._validate(evacuation_personality or self.DEFAULT_EVACUATION)

    def _validate(self, name: str) -> str:
        if name in self.PERSONALITIES:
            return name
        logger.warning("Unknown voice personality %r; falling back to %s", name, self.DEFAULT_ALERT)
        return self.DEFAULT_ALERT

    def set_alert_personality(self, name: str) -> None:
        self.alert_personality = self._validate(name)
        logger.info("Alert voice personality set to %s", self.alert_personality)

    def set_evacuation_personality(self, name: str) -> None:
        self.evacuation_personality = self._validate(name)
        logger.info("Evacuation voice personality set to %s", self.evacuation_personality)

    def get_personality(self, name: str) -> VoicePersonality:
        return self.PERSONALITIES[self._validate(name)]

    def render_alert(self, message: str, language: str = "en") -> str:
        """Render a fire alert in the selected alert personality."""
        p = self.PERSONALITIES[self.alert_personality]
        return f"{p.alert_prefix}. {message}"

    def render_evacuation(self, message: str, language: str = "en") -> str:
        """Render evacuation guidance in the selected evacuation personality."""
        p = self.PERSONALITIES[self.evacuation_personality]
        return f"{p.evacuation_prefix}. {message}"

    def tts_settings(self, name: str, base_rate: int = 150, base_volume: float = 1.0) -> dict[str, Any]:
        """Return adjusted rate/volume for pyttsx3."""
        p = self.PERSONALITIES[self._validate(name)]
        return {
            "rate": int(base_rate * p.rate_modifier),
            "volume": min(1.0, base_volume * p.volume_modifier),
            "tone": p.tone,
        }

    def sample(self, role: str = "alert", language: str = "en") -> str:
        """Return a sample phrase for the selected personality and role."""
        name = self.alert_personality if role == "alert" else self.evacuation_personality
        p = self.PERSONALITIES[name]
        return p.sample_phrases.get(language, p.sample_phrases["en"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_personality": self.alert_personality,
            "evacuation_personality": self.evacuation_personality,
            "available": list(self.PERSONALITIES.keys()),
            "defaults": {
                "alert": self.DEFAULT_ALERT,
                "evacuation": self.DEFAULT_EVACUATION,
            },
            "samples": {
                "alert": self.sample("alert"),
                "evacuation": self.sample("evacuation"),
            },
        }
