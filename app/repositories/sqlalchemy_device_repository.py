from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertRow, DeviceRow
from app.models import AlertResponse, DeviceResponse, DeviceStatus


class SQLAlchemyDeviceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_device(self, device: DeviceResponse) -> DeviceResponse:
        row = DeviceRow(**device.model_dump())
        self._session.add(row)
        self._session.flush()
        return DeviceResponse.model_validate(row)

    def list_devices(self) -> list[DeviceResponse]:
        rows = self._session.scalars(select(DeviceRow)).all()
        return [DeviceResponse.model_validate(row) for row in rows]

    def get_device(self, device_id: str) -> DeviceResponse | None:
        row = self._get_device_row(device_id)
        return DeviceResponse.model_validate(row) if row is not None else None

    def update_status(
        self, device_id: str, status: DeviceStatus
    ) -> DeviceResponse | None:
        row = self._get_device_row(device_id)
        if row is None:
            return None
        row.status = status
        self._session.flush()
        return DeviceResponse.model_validate(row)

    def save_alert(self, alert: AlertResponse) -> AlertResponse:
        row = AlertRow(**alert.model_dump())
        self._session.add(row)
        self._session.flush()
        return self._alert_response(row)

    def list_alerts(self) -> list[AlertResponse]:
        rows = self._session.scalars(select(AlertRow).order_by(AlertRow.id)).all()
        return [self._alert_response(row) for row in rows]

    def update_device(self, device: DeviceResponse) -> DeviceResponse:
        row = self._get_device_row(device.device_id)
        if row is None:
            return self.add_device(device)
        for field, value in device.model_dump().items():
            setattr(row, field, value)
        self._session.flush()
        return DeviceResponse.model_validate(row)

    def delete_device(self, device_id: str) -> bool:
        row = self._get_device_row(device_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def _get_device_row(self, device_id: str) -> DeviceRow | None:
        return self._session.scalars(
            select(DeviceRow).where(DeviceRow.device_id == device_id)
        ).one_or_none()

    @staticmethod
    def _alert_response(row: AlertRow) -> AlertResponse:
        return AlertResponse(
            device_id=row.device_id, message=row.message, timestamp=row.timestamp
        )