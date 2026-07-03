"""Cloud backup of telemetry events.

# ADD-007 — Cloud Backup of Telemetry

Uploads critical fire events and audit logs to S3-compatible storage
(AWS S3, Backblaze B2, MinIO). Encrypted at rest. Only uploads on
fire events and daily summaries to minimize bandwidth.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CloudBackup:
    """Cloud telemetry backup uploader.

    Usage::

        backup = CloudBackup(
            endpoint="https://s3.us-west-2.amazonaws.com",
            bucket="fire-telemetry-backup",
            access_key="...",
            secret_key="...",
        )
        await backup.upload_event(fire_event_dict)
    """

    def __init__(
        self,
        endpoint: str | None = None,
        bucket: str = "fire-telemetry",
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.mock = mock
        self._client = None

        if not mock and access_key and secret_key:
            try:
                import boto3
                self._client = boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                )
            except ImportError:
                logger.warning("boto3 not installed — cloud backup disabled")
                self.mock = True
            except Exception as exc:
                logger.warning("S3 client init failed: %s", exc)
                self.mock = True

    async def upload_event(self, event: dict) -> bool:
        """Upload a single critical event."""
        if self.mock:
            logger.info("[MOCK CLOUD] Would upload event: %s", event.get("event_type", "unknown"))
            return True

        if not self._client:
            return False

        try:
            timestamp = event.get("timestamp", time.time())
            key = f"events/{time.strftime('%Y/%m/%d', time.gmtime(timestamp))}/{int(timestamp)}_{event.get('event_type', 'unknown')}.json.gz"
            data = gzip.compress(json.dumps(event).encode())

            # boto3 is sync — run in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentEncoding="gzip",
                    ServerSideEncryption="AES256",
                ),
            )
            logger.info("Cloud backup uploaded: %s", key)
            return True
        except Exception as exc:
            logger.error("Cloud backup upload failed: %s", exc)
            return False

    async def upload_audit_report(self, html_path: str | Path) -> bool:
        """Upload an HTML audit report."""
        if self.mock:
            logger.info("[MOCK CLOUD] Would upload report: %s", html_path)
            return True
        if not self._client:
            return False

        try:
            path = Path(html_path)
            key = f"reports/{path.name}"
            data = path.read_bytes()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentType="text/html",
                    ServerSideEncryption="AES256",
                ),
            )
            return True
        except Exception as exc:
            logger.error("Audit report upload failed: %s", exc)
            return False
