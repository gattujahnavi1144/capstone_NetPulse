from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from app.logging_config import safe_device_id
from app.models import AlertResponse
from app.repositories.contracts import DeviceRepository


logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeviceCreated:
    device_id: str
    name: str


def publish(event: DeviceCreated) -> None:
    """Publish a domain event to the application's configured event sink."""
    logger.info("device_registered", device_id=safe_device_id(event.device_id))


def create_offline_alert(
    repository: DeviceRepository, device_id: str
) -> None:
    alert = AlertResponse(
        device_id=device_id,
        message=f"Device {device_id} went offline.",
        timestamp=datetime.now(timezone.utc),
    )
    repository.save_alert(alert)