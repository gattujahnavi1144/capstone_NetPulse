import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import Base
from app.db.models import DeviceRow


def main() -> None:
    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "crud_demo.db"
        engine = create_engine(f"sqlite:///{database_path}")
        try:
            Base.metadata.create_all(bind=engine)
            with Session(engine) as session:
                device = DeviceRow(
                    device_id="DEMO-101",
                    name="Demo Router",
                    device_type="router",
                    ip_address="192.0.2.10",
                    status="online",
                )
                session.add(device)
                session.commit()
                print(f"Create: inserted {device.device_id} with status {device.status}.")

                device = session.scalars(
                    select(DeviceRow).where(DeviceRow.device_id == "DEMO-101")
                ).one()
                print(f"Read: found {device.device_id} ({device.name}).")

                device.status = "offline"
                session.commit()
                print(f"Update: changed {device.device_id} to {device.status}.")

                session.delete(device)
                session.commit()
                print(f"Delete: removed DEMO-101; found afterward: {session.get(DeviceRow, 'DEMO-101') is not None}.")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()