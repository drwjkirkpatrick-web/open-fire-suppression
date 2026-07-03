"""Companion mobile app REST API endpoints.

# ADD-016 — Mobile App API

Provides endpoints for a companion mobile app:
- arm/disarm
- view status
- receive push notifications
- acknowledge alerts
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobile", tags=["mobile"])

# Simple token auth for mobile app
MOBILE_TOKENS: set[str] = set()


def verify_mobile_token(token: str) -> bool:
    return token in MOBILE_TOKENS


class ArmRequest(BaseModel):
    token: str


class StatusResponse(BaseModel):
    armed: bool
    fire_state: str
    active_sensors: int
    failed_sensors: list[str]
    battery_percent: float | None
    aqi: int
    timestamp: float


class AcknowledgeRequest(BaseModel):
    token: str
    alert_id: str


@router.post("/register")
async def register_device(token: str) -> dict:
    """Register a mobile device token for push notifications."""
    MOBILE_TOKENS.add(token)
    logger.info("Mobile device registered: %s...", token[:8])
    return {"success": True, "token": token[:8] + "..."}


@router.post("/arm")
async def mobile_arm(req: ArmRequest) -> dict:
    """Arm the system from mobile app."""
    if not verify_mobile_token(req.token):
        raise HTTPException(status_code=403, detail="Invalid token")
    # TODO: integrate with safety interlock
    logger.info("Mobile arm requested")
    return {"success": True, "state": "armed", "timestamp": time.time()}


@router.post("/disarm")
async def mobile_disarm(req: ArmRequest) -> dict:
    """Disarm the system from mobile app."""
    if not verify_mobile_token(req.token):
        raise HTTPException(status_code=403, detail="Invalid token")
    logger.info("Mobile disarm requested")
    return {"success": True, "state": "disarmed", "timestamp": time.time()}


@router.get("/status")
async def mobile_status(token: str) -> StatusResponse:
    """Get current system status for mobile app."""
    if not verify_mobile_token(token):
        raise HTTPException(status_code=403, detail="Invalid token")

    # TODO: integrate with actual system state
    return StatusResponse(
        armed=False,
        fire_state="clear",
        active_sensors=5,
        failed_sensors=[],
        battery_percent=85.0,
        aqi=42,
        timestamp=time.time(),
    )


@router.post("/acknowledge")
async def mobile_acknowledge(req: AcknowledgeRequest) -> dict:
    """Acknowledge an alert from mobile app."""
    if not verify_mobile_token(req.token):
        raise HTTPException(status_code=403, detail="Invalid token")
    logger.info("Alert %s acknowledged from mobile", req.alert_id)
    return {"success": True, "acknowledged": req.alert_id}
