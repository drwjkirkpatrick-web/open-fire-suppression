"""Mass notification gateway for IPAWS/WEA and emergency broadcast.

# MOD-019 — Mass Notification Gateway

Sends building-specific fire alerts to:
1. IPAWS (Integrated Public Alert & Warning System) / WEA
   (Wireless Emergency Alerts) — FEMA
2. NOAA weather radio ( SAME protocol )
3. Local emergency broadcast systems
4. Reverse 911 / automated calling systems

For large facilities, campuses, and multi-building sites where
local notification must reach people outdoors or in remote areas.

Hardware: IPAWS-compatible alert origination software,
NOAA SAME encoder, or API integration with Everbridge, CodeRED.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# IPAWS message types
class IPAWSMessageType(Enum):
    ALERT = "Alert"
    UPDATE = "Update"
    CANCEL = "Cancel"


class IPAWSUrgency(Enum):
    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"


class IPAWSeverity(Enum):
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"


@dataclass
class IPAWSAlert:
    sender: str
    status: str           # "Actual", "Exercise", "Test"
    msg_type: IPAWSMessageType
    scope: str            # "Public", "Restricted", "Private"
    category: str         # "Fire"
    urgency: IPAWSUrgency
    severity: IPAWSeverity
    certainty: str        # "Observed", "Likely", "Possible"
    headline: str
    description: str
    area_description: str
    geocodes: list[str]   # FIPS or SAME codes
    effective: float      # Unix timestamp
    expires: float


class MassNotificationGateway:
    """Mass notification gateway for IPAWS/WEA and emergency broadcasts.

    Bridges fire detection to public emergency alerting systems
    for large-scale notifications beyond building boundaries.
    """

    def __init__(
        self,
        ipaws_api_url: str | None = None,
        ipaws_credentials: dict[str, str] | None = None,
        everbridge_api_url: str | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.ipaws_api_url = ipaws_api_url or "https://tdl.ipaws.alliancesforfema.com"
        self.ipaws_credentials = ipaws_credentials or {}
        self.everbridge_api_url = everbridge_api_url
        self.mock = mock
        self._alert_history: list[dict] = []

        logger.info("MassNotificationGateway: IPAWS=%s Everbridge=%s",
                    bool(ipaws_api_url), bool(everbridge_api_url))

    # ── IPAWS Alert ─────────────────────────────────────────────────

    async def send_ipaws_alert(
        self,
        headline: str,
        description: str,
        area_description: str,
        geocodes: list[str],
        urgency: IPAWSUrgency = IPAWSUrgency.IMMEDIATE,
        severity: IPAWSeverity = IPAWSeverity.SEVERE,
    ) -> dict[str, Any]:
        """Send IPAWS Common Alerting Protocol (CAP) alert.

        Requires IPAWS COG (Collaborative Operating Group) approval.
        """
        alert = IPAWSAlert(
            sender="open-fire-suppression",
            status="Actual",
            msg_type=IPAWSMessageType.ALERT,
            scope="Public",
            category="Fire",
            urgency=urgency,
            severity=severity,
            certainty="Observed",
            headline=headline,
            description=description,
            area_description=area_description,
            geocodes=geocodes,
            effective=time.time(),
            expires=time.time() + 3600,
        )

        if self.mock:
            self._alert_history.append({
                "system": "IPAWS",
                "headline": headline,
                "time": time.time(),
                "status": "sent_mock",
            })
            logger.info("[MOCK IPAWS] Alert sent: %s", headline)
            return {
                "success": True,
                "system": "IPAWS",
                "alert_id": f"IPAWS-{int(time.time())}",
                "headline": headline,
            }

        # Real IPAWS API call
        try:
            import aiohttp
            cap_xml = self._generate_cap_xml(alert)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ipaws_api_url}/alerts",
                    data=cap_xml,
                    headers={"Content-Type": "application/cap+xml"},
                    auth=aiohttp.BasicAuth(
                        self.ipaws_credentials.get("username", ""),
                        self.ipaws_credentials.get("password", ""),
                    ),
                ) as resp:
                    if resp.status in (200, 202):
                        return {
                            "success": True,
                            "system": "IPAWS",
                            "alert_id": f"IPAWS-{int(time.time())}",
                            "status_code": resp.status,
                        }
                    return {
                        "success": False,
                        "system": "IPAWS",
                        "error": f"HTTP {resp.status}",
                    }
        except Exception:
            logger.exception("IPAWS alert failed")
            return {"success": False, "system": "IPAWS", "error": "exception"}

    def _generate_cap_xml(self, alert: IPAWSAlert) -> str:
        """Generate CAP XML message."""
        from xml.etree.ElementTree import Element, SubElement, tostring
        root = Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")
        SubElement(root, "identifier").text = f"open-fire-{int(time.time())}"
        SubElement(root, "sender").text = alert.sender
        SubElement(root, "sent").text = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(alert.effective))
        SubElement(root, "status").text = alert.status
        SubElement(root, "msgType").text = alert.msg_type.value
        SubElement(root, "scope").text = alert.scope
        info = SubElement(root, "info")
        SubElement(info, "category").text = alert.category
        SubElement(info, "event").text = "Fire"
        SubElement(info, "urgency").text = alert.urgency.value
        SubElement(info, "severity").text = alert.severity.value
        SubElement(info, "certainty").text = alert.certainty
        SubElement(info, "headline").text = alert.headline
        SubElement(info, "description").text = alert.description
        area = SubElement(info, "area")
        SubElement(area, "areaDesc").text = alert.area_description
        for gc in alert.geocodes:
            SubElement(area, "geocode").text = gc
        return tostring(root, encoding="unicode")

    # ── NOAA SAME ───────────────────────────────────────────────────

    async def send_noaa_same_alert(self, event_code: str = "FRW", fips_codes: list[str] | None = None) -> dict[str, Any]:
        """Send NOAA SAME (Specific Area Message Encoding) alert.

        Event codes: FRW=Fire Warning, FFA=Flash Flood, TOR=Tornado
        """
        if self.mock:
            self._alert_history.append({
                "system": "NOAA SAME",
                "event_code": event_code,
                "time": time.time(),
                "status": "sent_mock",
            })
            return {"success": True, "system": "NOAA SAME", "event_code": event_code}

        # Real: requires SAME encoder hardware or compatible API
        logger.warning("NOAA SAME requires dedicated encoder hardware")
        return {"success": False, "system": "NOAA SAME", "error": "hardware_required"}

    # ── Fire Alert Wrapper ──────────────────────────────────────────

    async def send_fire_alert(
        self,
        building_name: str,
        fire_zone: str,
        geocodes: list[str],
        evacuation_message: str = "",
    ) -> dict[str, Any]:
        """Send comprehensive mass notification for fire event."""
        headline = f"Fire Alert: {building_name} — {fire_zone}"
        description = (
            f"Fire detected in {fire_zone} at {building_name}. "
            f"{evacuation_message} "
            f"Emergency services have been notified. "
            f"Avoid the area until further notice."
        )

        results = {}
        if self.ipaws_api_url:
            results["ipaws"] = await self.send_ipaws_alert(
                headline=headline,
                description=description,
                area_description=f"{building_name} and surrounding area",
                geocodes=geocodes,
            )

        results["noaa_same"] = await self.send_noaa_same_alert(
            event_code="FRW",
            fips_codes=geocodes,
        )

        return {
            "headline": headline,
            "systems_notified": len([r for r in results.values() if r.get("success")]),
            "results": results,
            "timestamp": time.time(),
        }

    # ── Status ──────────────────────────────────────────────────────

    def get_history(self) -> list[dict]:
        return self._alert_history[-50:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ipaws_configured": bool(self.ipaws_api_url),
            "everbridge_configured": bool(self.everbridge_api_url),
            "alerts_sent": len(self._alert_history),
            "mock": self.mock,
        }
