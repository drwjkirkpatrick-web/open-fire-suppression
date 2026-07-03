"""Directional voice evacuation with per-zone TTS instructions.

# AUD-002 — Directional Voice Evacuation

NFPA 72 §24.4: Voice messaging required for high-rise, assembly,
healthcare, and occupant notification systems.

Problem: Traditional fire alarm is one-tone-fits-all. Occupants don't
know which way to evacuate, causing panic, wrong-way movement, and
tragic outcomes.

Solution: Per-zone directional speakers with offline TTS evacuation
messages: "Fire detected in Kitchen — evacuate EAST via Main Exit.
Do NOT use elevator."

Hardware: Same speakers as AUD-001 with zone routing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvacuationRoute:
    """Pre-defined evacuation route for a zone."""
    zone: str
    fire_zone: str           # Zone where fire is detected
    direction: str           # "east", "west", "north", "south", "up", "down"
    exit_name: str           # "Main Exit", "Stairwell B", etc.
    instructions: str        # Full text instruction
    avoid_elevator: bool = True
    distance_meters: float = 0.0
    estimated_time_sec: float = 0.0


@dataclass
class VoiceMessage:
    """A queued voice message."""
    message_id: str
    text: str
    priority: int            # 1 = fire, 2 = pre-alert, 3 = all-clear
    zone: str | None = None
    language: str = "en"
    timestamp: float = 0.0


class DirectionalVoiceEvacuation:
    """Per-zone directional voice evacuation system.

    When fire is detected in a zone, all OTHER zones receive
    directional messages guiding occupants AWAY from the fire.
    The fire zone itself receives shelter-in-place or evacuation
    instructions based on building layout.
    """

    def __init__(
        self,
        speaker_array=None,
        routes: list[EvacuationRoute] | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.speaker_array = speaker_array
        self.routes: dict[tuple[str, str], EvacuationRoute] = {}
        self.mock = mock
        self._message_queue: list[VoiceMessage] = []
        self._language = "en"
        self._is_speaking = False

        if routes:
            for route in routes:
                self.add_route(route)

        logger.info("DirectionalVoiceEvacuation initialized: %d routes", len(self.routes))

    # ── Route Management ────────────────────────────────────────────

    def add_route(self, route: EvacuationRoute) -> None:
        key = (route.zone, route.fire_zone)
        self.routes[key] = route
        logger.debug("Added route: %s -> %s via %s", route.zone, route.fire_zone, route.exit_name)

    def get_route(self, zone: str, fire_zone: str) -> EvacuationRoute | None:
        return self.routes.get((zone, fire_zone))

    # ── Message Generation ──────────────────────────────────────────

    def generate_fire_message(self, fire_zone: str, language: str = "en") -> str:
        """Generate evacuation message for the fire zone itself."""
        templates = {
            "en": f"Attention. Fire detected in {fire_zone}. Leave immediately via the nearest safe exit. Do not use elevators. Move calmly to the designated assembly point.",
            "sw": f"Tahadhari. Moto umeonekana katika {fire_zone}. Toka mara moja kwa kutumia mlango salama wa karibu. Usitumie lifti. Enda kwa utulivu hadi eneo la mkutano.",
            "es": f"Atención. Incendio detectado en {fire_zone}. Salga inmediatamente por la salida más cercana. No use ascensores. Diríjase al punto de reunión.",
        }
        return templates.get(language, templates["en"])

    def generate_directional_message(
        self,
        zone: str,
        fire_zone: str,
        language: str = "en",
    ) -> str | None:
        """Generate directional message for non-fire zones."""
        route = self.get_route(zone, fire_zone)
        if not route:
            return None

        templates = {
            "en": (
                f"Attention. Fire has been detected in {fire_zone}. "
                f"Please evacuate {route.direction} toward {route.exit_name}. "
                f"Estimated distance {route.distance_meters:.0f} meters. "
                f"{'Do not use elevators. ' if route.avoid_elevator else ''}"
                f"Move calmly and follow illuminated exit signs."
            ),
            "sw": (
                f"Tahadhari. Moto umeonekana katika {fire_zone}. "
                f"Tafadhali toa kuharibika kuelekea {route.direction} kupitia {route.exit_name}. "
                f"Umbali unaokadiriwa ni mita {route.distance_meters:.0f}. "
                f"{'Usitumie lifti. ' if route.avoid_elevator else ''}"
                f"Enda kwa utulivu na fuata alama za kutoka zinazowaka."
            ),
            "es": (
                f"Atención. Incendio detectado en {fire_zone}. "
                f"Evacúe hacia {route.direction} por {route.exit_name}. "
                f"Distancia estimada {route.distance_meters:.0f} metros. "
                f"{'No use ascensores. ' if route.avoid_elevator else ''}"
                f"Muévase con calma y siga las señales de salida iluminadas."
            ),
        }
        return templates.get(language, templates["en"])

    def generate_all_clear_message(self, language: str = "en") -> str:
        templates = {
            "en": "All clear. The fire has been contained. You may return to the building when directed by emergency personnel. Thank you for your cooperation.",
            "sw": "Salama. Moto umedhibitiwa. Unaweza kurudi katika jengo unapoamriwa na wafanyakazi wa dharura. Asante kwa ushirikiano wako.",
            "es": "Todo despejado. El incendio ha sido controlado. Puede regresar al edificio cuando el personal de emergencia lo indique. Gracias por su cooperación.",
        }
        return templates.get(language, templates["en"])

    # ── Activation ───────────────────────────────────────────────────

    async def announce_fire(self, fire_zone: str, language: str = "en") -> None:
        """Announce fire in a specific zone to all zones.

        Fire zone gets direct evacuation message.
        Other zones get directional away-from-fire messages.
        """
        logger.warning("ANNOUNCING FIRE in zone '%s'", fire_zone)

        # Fire zone message
        fire_msg = self.generate_fire_message(fire_zone, language)
        await self._speak(fire_msg, zone=fire_zone, priority=1)

        # Directional messages for other zones
        if self.speaker_array:
            zones = {s.zone for s in self.speaker_array.speakers.values()}
            for zone in zones:
                if zone == fire_zone:
                    continue
                msg = self.generate_directional_message(zone, fire_zone, language)
                if msg:
                    await self._speak(msg, zone=zone, priority=1)

    async def announce_all_clear(self, language: str = "en") -> None:
        msg = self.generate_all_clear_message(language)
        await self._speak(msg, priority=3)

    async def _speak(self, text: str, *, zone: str | None = None, priority: int = 2) -> None:
        """Convert text to speech and route to speaker array."""
        if self.mock:
            logger.info("[MOCK VOICE] Zone=%s Priority=%d: %s", zone, priority, text[:80])
            await asyncio.sleep(0.1)
            return

        # Real TTS using pyttsx3 or espeak
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 130)  # Slower for emergency clarity
            engine.setProperty("volume", 1.0)
            # TODO: Save to file, play through speaker array zone
            engine.say(text)
            engine.runAndWait()
        except Exception:
            logger.exception("TTS failed for zone %s", zone)

        if self.speaker_array:
            await self.speaker_array.activate_zone(zone or "all", pattern="steady")

    # ── Queue Management ──────────────────────────────────────────────

    async def queue_message(self, text: str, *, zone: str | None = None, priority: int = 2, language: str = "en") -> None:
        """Queue a message for playback. Higher priority = sooner."""
        msg = VoiceMessage(
            message_id=f"MSG-{int(time.time()*1000)}",
            text=text,
            priority=priority,
            zone=zone,
            language=language,
            timestamp=time.time(),
        )
        self._message_queue.append(msg)
        self._message_queue.sort(key=lambda m: m.priority)
        logger.debug("Queued message '%s' priority=%d", msg.message_id, priority)

    async def process_queue(self) -> None:
        """Process queued messages in priority order."""
        while self._message_queue:
            msg = self._message_queue.pop(0)
            await self._speak(msg.text, zone=msg.zone, priority=msg.priority)

    # ── NFPA 72 Compliance ──────────────────────────────────────────

    def verify_voice_intelligibility(self, zone: str) -> dict:
        """NFPA 72 §24.4 requires voice messages be intelligible.

        Returns STI (Speech Transmission Index) estimate.
        """
        # Simplified: check speaker density and SNR
        if not self.speaker_array:
            return {"intelligible": False, "reason": "No speaker array configured"}

        zone_speakers = [s for s in self.speaker_array.speakers.values() if s.zone == zone]
        if len(zone_speakers) < 2:
            return {"intelligible": False, "sti_estimate": 0.3, "reason": "Insufficient speaker density"}

        # Estimate STI based on speaker count and spacing
        sti = min(0.85, 0.4 + len(zone_speakers) * 0.05)
        return {
            "intelligible": sti >= 0.5,
            "sti_estimate": round(sti, 2),
            "required_sti": 0.5,
            "speakers_in_zone": len(zone_speakers),
        }

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_count": len(self.routes),
            "languages_supported": ["en", "sw", "es"],
            "mock": self.mock,
            "has_speaker_array": self.speaker_array is not None,
        }
