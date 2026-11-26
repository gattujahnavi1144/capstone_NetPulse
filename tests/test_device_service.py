from datetime import timedelta
import json
import logging

import pytest

from app.models import DeviceCreate, DeviceResponse, DeviceStatus, DeviceType
from app.logging_config import configure_logging
from app.repositories.device_repository import InMemoryDeviceRepository
from app.services.device_service import (
    DeviceAlreadyExistsError,
    DeviceNotFoundError,
    DeviceService,
)


@pytest.fixture
def device_context() -> tuple[InMemoryDeviceRepository, DeviceService]:
    repository = InMemoryDeviceRepository()
    return repository, DeviceService(repository)


def build_device(
    device_id: str = "RTR-101",
    status: DeviceStatus = "online",
    device_type: DeviceType = "router",
) -> DeviceResponse:
    return DeviceResponse(
        device_id=device_id,
        name="Core Router",
        device_type=device_type,
        ip_address="192.0.2.10",
        status=status,
    )


def test_registration(device_context: tuple[InMemoryDeviceRepository, DeviceService]) -> None:
    _, service = device_context
    created = service.create_device(
        DeviceCreate(
            device_id="RTR-101",
            name="Core Router",
            device_type="router",
            ip_address="192.0.2.10",
        )
    )

    assert created.device_id == "RTR-101"
    assert service.get("RTR-101") == created
    assert service.list() == [created]


def test_device_logging(
    device_context: tuple[InMemoryDeviceRepository, DeviceService], caplog, monkeypatch
) -> None:
    _, service = device_context
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [caplog.handler])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    configure_logging()
    with caplog.at_level(logging.INFO, logger="app"):
        service.register(build_device())
        service.register(build_device("token=secret"))
        with pytest.raises(DeviceNotFoundError):
            service.get("RTR-404")
        with pytest.raises(DeviceNotFoundError):
            service.get("password=secret\ntoken=secret")

    events = [json.loads(record.getMessage()) for record in caplog.records]
    assert [(event["event"], event["level"], event["device_id"]) for event in events] == [
        ("device_registered", "info", "RTR-101"),
        ("device_registered", "info", "[redacted]"),
    ]
    assert all(set(event) == {"event", "level", "timestamp", "device_id"} for event in events)


def test_device_summary_counts_and_sorts_unique_types(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    _, service = device_context
    service.register(build_device("SWT-101", "offline", "switch"))
    service.register(build_device("RTR-101", "online", "router"))
    service.register(build_device("SWT-102", "offline", "switch"))

    summary = service.get_device_summary()

    assert summary.total_devices == 3
    assert summary.online_count == 1
    assert summary.offline_count == 2
    assert summary.device_types == ["router", "switch"]


def test_empty_device_summary(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    _, service = device_context

    summary = service.get_device_summary()

    assert summary.total_devices == 0
    assert summary.online_count == 0
    assert summary.offline_count == 0
    assert summary.device_types == []


def test_duplicate_registration_raises(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    _, service = device_context
    device = build_device()
    service.register(device)

    with pytest.raises(DeviceAlreadyExistsError):
        service.register(device)


def test_missing_device_raises(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    _, service = device_context

    with pytest.raises(DeviceNotFoundError):
        service.get("RTR-404")
    with pytest.raises(DeviceNotFoundError):
        service.update_status("RTR-404", "offline")


def test_initial_offline_registration_does_not_create_alert(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    repository, service = device_context
    service.register(build_device(status="offline"))

    assert repository.list_alerts() == []


def test_online_to_offline_creates_one_alert(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    repository, service = device_context
    device = build_device()
    service.register(device)
    service.update_status(device.device_id, "offline")

    alerts = repository.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].device_id == device.device_id
    assert alerts[0].message == f"Device {device.device_id} went offline."
    assert alerts[0].timestamp.utcoffset() == timedelta(0)


def test_repeated_offline_update_does_not_create_another_alert(
    device_context: tuple[InMemoryDeviceRepository, DeviceService],
) -> None:
    repository, service = device_context
    device = build_device()
    service.register(device)
    service.update_status(device.device_id, "offline")
    service.update_status(device.device_id, "offline")

    alerts = repository.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].device_id == device.device_id