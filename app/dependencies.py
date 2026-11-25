from app.repositories.device_repository import InMemoryDeviceRepository
from app.services.device_service import DeviceService


repository = InMemoryDeviceRepository()
device_service = DeviceService(repository)