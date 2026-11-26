from typing import Annotated

from fastapi import Depends

from app.db.database import SessionDep
from app.repositories.contracts import DeviceRepository
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository
from app.services.device_service import DeviceService


def get_repository(session: SessionDep) -> DeviceRepository:
	return SQLAlchemyDeviceRepository(session)


RepositoryDep = Annotated[DeviceRepository, Depends(get_repository)]


def get_device_service(repository: RepositoryDep) -> DeviceService:
	return DeviceService(repository)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]