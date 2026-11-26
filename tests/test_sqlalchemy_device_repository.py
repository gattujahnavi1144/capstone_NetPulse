from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.models import AlertResponse, DeviceResponse, DeviceUpdate
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository
from app.services.device_service import DeviceAlreadyExistsError, DeviceService


def build_device(device_id: str = "RTR-101") -> DeviceResponse:
    return DeviceResponse(
        device_id=device_id,
        name="Core Router",
        device_type="router",
        ip_address="192.0.2.10",
        status="online",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_repository_methods_and_transaction_persistence(session_factory) -> None:
    device = build_device()
    alert = AlertResponse(
        device_id=device.device_id,
        message="Device RTR-101 went offline.",
        timestamp=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    with session_factory() as session:
        session.commit = Mock(wraps=session.commit)
        repository = SQLAlchemyDeviceRepository(session)
        assert repository.get_device("missing") is None
        assert repository.update_status("missing", "offline") is None
        assert repository.delete_device("missing") is False
        assert repository.add_device(device) == device
        assert repository.get_device(device.device_id) == device
        assert repository.list_devices() == [device]
        assert repository.update_status(device.device_id, "offline").status == "offline"
        updated = device.model_copy(update={"name": "Updated", "status": "offline"})
        assert repository.update_device(updated) == updated
        assert repository.save_alert(alert) == alert
        assert repository.list_alerts() == [alert]
        session.commit.assert_not_called()
        session.commit()

    with session_factory() as session:
        repository = SQLAlchemyDeviceRepository(session)
        assert repository.get_device(device.device_id) == updated
        assert repository.list_alerts() == [alert]
        assert repository.delete_device(device.device_id) is True
        assert repository.get_device(device.device_id) is None
        session.rollback()

    with session_factory() as session:
        assert SQLAlchemyDeviceRepository(session).get_device(device.device_id) == updated


def test_service_status_transitions_and_duplicate_registration(session_factory) -> None:
    with session_factory() as session:
        repository = SQLAlchemyDeviceRepository(session)
        service = DeviceService(repository)
        device = build_device()
        service.register(device)
        with pytest.raises(DeviceAlreadyExistsError):
            service.register(device)
        service.update_device(device.device_id, DeviceUpdate(name="Updated", status="offline"))
        service.update_status(device.device_id, "offline")
        assert service.get(device.device_id).name == "Updated"
        assert len(repository.list_alerts()) == 1
        assert repository.list_alerts()[0].device_id == device.device_id
        session.rollback()

    with session_factory() as session:
        repository = SQLAlchemyDeviceRepository(session)
        assert repository.list_devices() == []
        assert repository.list_alerts() == []


def test_update_device_inserts_missing_device(session_factory) -> None:
    with session_factory() as session:
        repository = SQLAlchemyDeviceRepository(session)
        device = build_device()
        assert repository.update_device(device) == device
        assert repository.get_device(device.device_id) == device