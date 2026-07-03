"""MQTT client for IoT integration and smart home interoperability.

# IMP-008 — MQTT IoT Integration

Publishes sensor data and system status to MQTT topics.
Subscribes to remote commands (arm, disarm, config updates).
Supports Home Assistant MQTT discovery format.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
DEFAULT_TOPIC_PREFIX = "fire-suppression"


@dataclass
class MQTTConfig:
    broker: str
    port: int
    username: str | None = None
    password: str | None = None
    client_id: str = "fire-suppression-pi5"
    topic_prefix: str = DEFAULT_TOPIC_PREFIX
    home_assistant_discovery: bool = True
    ha_discovery_prefix: str = "homeassistant"


class MQTTClient:
    """MQTT client for IoT integration.

    Usage::

        client = MQTTClient(mqtt_config)
        await client.connect()
        await client.publish_sensor("mq2", {"smoke_ppm": 150})
        await client.publish_status({"state": "armed", "fire_state": "clear"})

    Commands received on ``fire-suppression/command/#`` trigger callbacks.
    """

    def __init__(
        self,
        config: MQTTConfig | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.config = config or MQTTConfig(broker=DEFAULT_BROKER, port=DEFAULT_PORT)
        self.mock = mock
        self._client = None
        self._connected = False
        self._callbacks: dict[str, list[callable]] = {}
        self._running = False
        self._publish_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        """Connect to MQTT broker and subscribe to command topics."""
        if self.mock:
            logger.info("[MOCK] MQTT connected to %s:%d", self.config.broker, self.config.port)
            self._connected = True
            return

        try:
            import paho.mqtt.client as mqtt
            import paho.mqtt.enums as mqtt_enums
        except ImportError:
            logger.warning("paho-mqtt not installed; MQTT disabled")
            return

        self._client = mqtt.Client(
            callback_api_version=mqtt_enums.CallbackAPIVersion.VERSION2,
            client_id=self.config.client_id,
        )
        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        try:
            self._client.connect(self.config.broker, self.config.port, 60)
            self._client.loop_start()
            # Wait a moment for connection
            await asyncio.sleep(1.0)
            logger.info("MQTT connected to %s:%d", self.config.broker, self.config.port)
        except Exception as exc:
            logger.error("MQTT connection failed: %s", exc)
            self._client = None

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self._running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        self._connected = False
        logger.info("MQTT disconnected")

    # ── Publish ──

    async def publish_sensor(self, sensor_name: str, values: dict) -> None:
        """Publish sensor readings to MQTT."""
        topic = f"{self.config.topic_prefix}/sensors/{sensor_name}/values"
        payload = json.dumps({
            "sensor": sensor_name,
            "values": values,
            "timestamp": time.time(),
        })
        await self._publish(topic, payload)

    async def publish_status(self, status: dict) -> None:
        """Publish overall system status."""
        topic = f"{self.config.topic_prefix}/status"
        payload = json.dumps({
            **status,
            "timestamp": time.time(),
        })
        await self._publish(topic, payload)

    async def publish_event(self, event_type: str, details: dict) -> None:
        """Publish an event (fire alert, suppression activated, etc.)."""
        topic = f"{self.config.topic_prefix}/events/{event_type}"
        payload = json.dumps({
            "event": event_type,
            "details": details,
            "timestamp": time.time(),
        })
        await self._publish(topic, payload)

    async def _publish(self, topic: str, payload: str) -> None:
        if self.mock:
            logger.debug("[MOCK MQTT] %s: %s", topic, payload[:100])
            return
        if not self._client or not self._connected:
            return
        try:
            self._client.publish(topic, payload, qos=1)
        except Exception as exc:
            logger.warning("MQTT publish failed: %s", exc)

    # ── Home Assistant Discovery ──

    async def publish_ha_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery configurations."""
        if not self.config.home_assistant_discovery:
            return

        device_info = {
            "identifiers": [self.config.client_id],
            "name": "Fire Suppression System",
            "model": "open-fire-suppression",
            "manufacturer": "Open Source",
        }

        # Fire state sensor
        await self._publish_ha_sensor(
            "fire_state", "Fire State", "", device_info, "enum",
            options=["clear", "warning", "alert", "confirmed"],
        )

        # Temperature sensor
        await self._publish_ha_sensor(
            "temperature", "Ambient Temperature", "°C", device_info, "temperature",
        )

        # Smoke sensor
        await self._publish_ha_sensor(
            "smoke_level", "Smoke Level", "ppm", device_info, None,
        )

        # Battery sensor
        await self._publish_ha_sensor(
            "battery", "Battery Level", "%", device_info, "battery",
        )

        # Binary sensor: armed
        await self._publish_ha_binary_sensor(
            "armed", "System Armed", device_info,
        )

    async def _publish_ha_sensor(
        self,
        entity_id: str,
        name: str,
        unit: str,
        device_info: dict,
        device_class: str | None,
        options: list[str] | None = None,
    ) -> None:
        config_topic = f"{self.config.ha_discovery_prefix}/sensor/{self.config.client_id}/{entity_id}/config"
        payload = {
            "name": name,
            "state_topic": f"{self.config.topic_prefix}/status",
            "value_template": "{{ value_json.%s }}" % entity_id,
            "unique_id": f"{self.config.client_id}_{entity_id}",
            "device": device_info,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if options:
            payload["options"] = options
        await self._publish(config_topic, json.dumps(payload))

    async def _publish_ha_binary_sensor(
        self,
        entity_id: str,
        name: str,
        device_info: dict,
    ) -> None:
        config_topic = f"{self.config.ha_discovery_prefix}/binary_sensor/{self.config.client_id}/{entity_id}/config"
        payload = {
            "name": name,
            "state_topic": f"{self.config.topic_prefix}/status",
            "value_template": "{{ value_json.%s }}" % entity_id,
            "payload_on": "true",
            "payload_off": "false",
            "unique_id": f"{self.config.client_id}_{entity_id}",
            "device": device_info,
        }
        await self._publish(config_topic, json.dumps(payload))

    # ── Callbacks ──

    def on_command(self, command: str, callback: callable) -> None:
        """Register a callback for a specific command type.

        Commands: ``arm``, ``disarm``, ``activate``, ``deactivate``, ``config``
        """
        if command not in self._callbacks:
            self._callbacks[command] = []
        self._callbacks[command].append(callback)

    # ── MQTT Handlers ──

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            self._connected = True
            # Subscribe to command topics
            command_topic = f"{self.config.topic_prefix}/command/#"
            client.subscribe(command_topic, qos=1)
            logger.info("MQTT subscribed to %s", command_topic)
        else:
            logger.error("MQTT connection failed with code %d", rc)

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        self._connected = False
        logger.warning("MQTT disconnected (code %d)", rc)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            logger.info("MQTT command received: %s → %s", topic, payload)

            # Extract command from topic: fire-suppression/command/arm
            command = topic.split("/")[-1]
            for cb in self._callbacks.get(command, []):
                try:
                    asyncio.create_task(cb(payload) if asyncio.iscoroutinefunction(cb) else cb(payload))
                except Exception as exc:
                    logger.error("Command callback error: %s", exc)

        except json.JSONDecodeError:
            logger.warning("Invalid JSON in MQTT message on %s", msg.topic)
        except Exception as exc:
            logger.error("MQTT message handling error: %s", exc)
