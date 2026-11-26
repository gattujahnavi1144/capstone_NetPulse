from fastapi import APIRouter, status

from app.dependencies import DeviceServiceDep
from app.models import DeviceCreate, DeviceResponse, DeviceSummary, StatusUpdate
from app.services.probe import simulate_device_probe


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
def list_devices(device_service: DeviceServiceDep) -> list[DeviceResponse]:
    return device_service.list()


@router.post(
    "",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "A device with this device_id is already registered"
        }
    },
)
def create_device(data: DeviceCreate, device_service: DeviceServiceDep) -> DeviceResponse:
    return device_service.create_device(data)


@router.get("/summary", response_model=DeviceSummary)
def get_device_summary(device_service: DeviceServiceDep) -> DeviceSummary:
    return device_service.get_device_summary()


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Device not found"}},
)
def get_device(device_id: str, device_service: DeviceServiceDep) -> DeviceResponse:
    return device_service.get(device_id)


@router.get("/{device_id}/probe")
async def probe_device(
    device_id: str, device_service: DeviceServiceDep
) -> dict[str, str | bool]:
    device_service.get_device(device_id)
    return await simulate_device_probe(device_id)


@router.patch(
    "/{device_id}/status",
    response_model=DeviceResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Device not found"}},
)
def update_device_status(
    device_id: str, data: StatusUpdate, device_service: DeviceServiceDep
) -> DeviceResponse:
    return device_service.update_status(device_id, data.status)