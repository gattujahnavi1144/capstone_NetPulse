import ipaddress
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


DeviceType = Literal["router", "switch", "server"]
DeviceStatus = Literal["online", "offline"]


def _validate_ipv4(value: str) -> str:
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise ValueError("ip_address must be a valid IPv4 address") from error
    return value


class DeviceCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_id": "RTR-101",
                    "name": "Core Router",
                    "device_type": "router",
                    "ip_address": "192.0.2.10",
                    "status": "online",
                }
            ]
        }
    )

    device_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    name: str = Field(min_length=1, max_length=100)
    device_type: DeviceType
    ip_address: str
    status: DeviceStatus = "online"

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        return _validate_ipv4(value)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    device_type: DeviceType | None = None
    ip_address: str | None = None
    status: DeviceStatus | None = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str | None) -> str | None:
        return _validate_ipv4(value) if value is not None else None


class StatusUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "offline"}]})

    status: DeviceStatus


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    name: str
    device_type: DeviceType
    ip_address: str
    status: DeviceStatus = "online"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        return _validate_ipv4(value)


class DeviceSummary(BaseModel):
    total_devices: int
    online_count: int
    offline_count: int
    device_types: list[DeviceType]


class AlertResponse(BaseModel):
    device_id: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"