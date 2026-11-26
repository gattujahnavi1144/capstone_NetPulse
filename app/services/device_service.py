from __future__ import annotations

from app.events import DeviceCreated, create_offline_alert, publish
from app.models import (
    DeviceCreate,
    DeviceResponse,
    DeviceStatus,
    DeviceSummary,
    DeviceType,
    DeviceUpdate,
)
from app.repositories.contracts import DeviceRepository


class DeviceAlreadyExistsError(Exception):
    pass


class DeviceNotFoundError(Exception):
    pass


class DeviceService:
    def __init__(self, repository: DeviceRepository) -> None:
        self._repository = repository

    def register(self, device: DeviceResponse) -> DeviceResponse:
        if self._repository.get_device(device.device_id) is not None:
            raise DeviceAlreadyExistsError(
                f"Device {device.device_id} is already registered"
            )

        registered = self._repository.add_device(device)
        publish(DeviceCreated(device_id=registered.device_id, name=registered.name))
        return registered

    def list(self) -> list[DeviceResponse]:
        return self._repository.list_devices()

    def list_devices(self) -> list[DeviceResponse]:
        return self.list()

    def get_device_summary(self) -> DeviceSummary:
        devices = self._repository.list_devices()
        status_counts = {"online": 0, "offline": 0}
        device_types: set[DeviceType] = set()

        for device in devices:
            status_counts[device.status] += 1
            device_types.add(device.device_type)

        return DeviceSummary(
            total_devices=len(devices),
            online_count=status_counts["online"],
            offline_count=status_counts["offline"],
            device_types=sorted(device_types),
        )

    def create_device(self, data: DeviceCreate) -> DeviceResponse:
        return self.register(DeviceResponse(**data.model_dump()))

    def get(self, device_id: str) -> DeviceResponse:
        device = self._repository.get_device(device_id)
        if device is None:
            raise DeviceNotFoundError(f"Device {device_id} was not found")
        return device

    def get_device(self, device_id: str) -> DeviceResponse:
        return self.get(device_id)

    def update_status(
        self, device_id: str, new_status: DeviceStatus
    ) -> DeviceResponse:
        device = self.get(device_id)
        updated = self._repository.update_status(device_id, new_status)
        if updated is None:
            raise DeviceNotFoundError(f"Device {device_id} was not found")

        if device.status == "online" and updated.status == "offline":
            create_offline_alert(self._repository, device_id)
        return updated

    def update_device(self, device_id: str, data: DeviceUpdate) -> DeviceResponse:
        existing = self.get(device_id)
        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        new_status = updates.pop("status", None)
        if new_status is not None:
            existing = self.update_status(device_id, new_status)

        if updates:
            existing = existing.model_copy(update=updates)
            return self._repository.update_device(existing)
        return existing

    def delete_device(self, device_id: str) -> None:
        if not self._repository.delete_device(device_id):
            raise DeviceNotFoundError(f"Device {device_id} was not found")