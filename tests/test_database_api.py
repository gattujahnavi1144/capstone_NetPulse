import asyncio
import json

from app.db import database
from app.main import app
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository


def test_database_api_workflow(session_factory, monkeypatch) -> None:
    sessions = []

    def create_session():
        session = session_factory()
        sessions.append(session)
        return session

    monkeypatch.setattr(database, "SessionLocal", create_session)

    async def request(method, path, data=None, expected_error=None):
        session_count = len(sessions)
        body = json.dumps(data).encode() if data is not None else b""
        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        try:
            await app(scope, receive, send)
        except Exception as error:
            if expected_error is None or not isinstance(error, expected_error):
                raise
        else:
            assert expected_error is None
        assert len(sessions) == session_count + 1
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        )
        return status, json.loads(response_body) if response_body.startswith((b"{", b"[")) else None

    async def workflow():
        async with app.router.lifespan_context(app):
            device = {
                "device_id": "RTR-101",
                "name": "Core Router",
                "device_type": "router",
                "ip_address": "192.0.2.10",
            }
            status, created = await request("POST", "/devices", device)
            assert status == 201
            assert created["status"] == "online"
            assert (await request("POST", "/devices", device))[0] == 409
            assert (await request("GET", "/devices/missing"))[0] == 404
            assert (await request("PATCH", "/devices/missing/status", {"status": "offline"}))[0] == 404
            assert (await request("POST", "/devices", {**device, "ip_address": "invalid"}))[0] == 422

            offline = {**device, "device_id": "SWT-101", "device_type": "switch", "status": "offline"}
            assert (await request("POST", "/devices", offline))[0] == 201
            assert (await request("GET", "/alerts"))[1] == []
            status, summary = await request("GET", "/devices/summary")
            assert status == 200
            assert summary == {"total_devices": 2, "online_count": 1, "offline_count": 1, "device_types": ["router", "switch"]}
            status, probe = await request("GET", "/devices/RTR-101/probe")
            assert status == 200
            assert probe == {"device_id": "RTR-101", "reachable": True, "simulated": True}

            def fail_alert(self, alert):
                raise RuntimeError("alert persistence failed")

            with monkeypatch.context() as patch:
                patch.setattr(SQLAlchemyDeviceRepository, "save_alert", fail_alert)
                status, _ = await request(
                    "PATCH", "/devices/RTR-101/status", {"status": "offline"}, RuntimeError
                )
                assert status == 500
            assert (await request("GET", "/devices/RTR-101"))[1]["status"] == "online"

            assert (await request("PATCH", "/devices/RTR-101/status", {"status": "offline"}))[0] == 200
            assert (await request("PATCH", "/devices/RTR-101/status", {"status": "offline"}))[0] == 200
            status, alerts = await request("GET", "/alerts")
            assert status == 200
            assert len(alerts) == 1
            assert alerts[0]["device_id"] == "RTR-101"
            assert alerts[0]["message"] == "Device RTR-101 went offline."
            assert alerts[0]["timestamp"].endswith("Z")

        async with app.router.lifespan_context(app):
            assert (await request("GET", "/devices/RTR-101"))[1]["status"] == "offline"
            assert len((await request("GET", "/alerts"))[1]) == 1
            assert (await request("GET", "/devices/summary"))[1] == {
                "total_devices": 2,
                "online_count": 0,
                "offline_count": 2,
                "device_types": ["router", "switch"],
            }

    asyncio.run(workflow())