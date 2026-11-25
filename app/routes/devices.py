from fastapi import APIRouter, HTTPException, status

from app.dependencies import device_service
from app.models import DeviceCreate, DeviceResponse, StatusUpdate
from app.services.device_service import (
    DeviceAlreadyExistsError,
    DeviceNotFoundError,
)


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
def list_devices() -> list[DeviceResponse]:
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
def create_device(data: DeviceCreate) -> DeviceResponse:
    try:
        return device_service.create_device(data)
    except DeviceAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Device not found"}},
)
def get_device(device_id: str) -> DeviceResponse:
    try:
        return device_service.get(device_id)
    except DeviceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.patch(
    "/{device_id}/status",
    response_model=DeviceResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Device not found"}},
)
def update_device_status(device_id: str, data: StatusUpdate) -> DeviceResponse:
    try:
        return device_service.update_status(device_id, data.status)
    except DeviceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error