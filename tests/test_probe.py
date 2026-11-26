import asyncio

from app.services.probe import simulate_device_probe


def test_simulate_device_probe_returns_deterministic_result() -> None:
    result = asyncio.run(simulate_device_probe("RTR-101"))

    assert result == {
        "device_id": "RTR-101",
        "reachable": True,
        "simulated": True,
    }