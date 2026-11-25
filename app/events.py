import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import AlertResponse
from app.repositories.device_repository import InMemoryDeviceRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceCreated:
    device_id: str
    name: str


def publish(event: DeviceCreated) -> None:
    """Publish a domain event to the application's configured event sink."""
    logger.info("Device created: id=%s name=%s", event.device_id, event.name)


def create_offline_alert(
    repository: InMemoryDeviceRepository, device_id: str
) -> None:
    alert = AlertResponse(
        device_id=device_id,
        message=f"Device {device_id} went offline.",
        timestamp=datetime.now(timezone.utc),
    )
    repository.save_alert(alert)