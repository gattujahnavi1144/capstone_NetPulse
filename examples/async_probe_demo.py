import asyncio
from time import perf_counter

from app.services.probe import simulate_device_probe


DEVICE_IDS = ("RTR-101", "SWT-201", "SRV-301")


async def main() -> None:
    sequential_start = perf_counter()
    sequential_results = []
    for device_id in DEVICE_IDS:
        sequential_results.append(await simulate_device_probe(device_id))
    sequential_elapsed = perf_counter() - sequential_start

    concurrent_start = perf_counter()
    concurrent_results = await asyncio.gather(
        *(simulate_device_probe(device_id) for device_id in DEVICE_IDS)
    )
    concurrent_elapsed = perf_counter() - concurrent_start

    print("Sequential results:", sequential_results)
    print(f"Sequential elapsed: {sequential_elapsed:.3f} seconds")
    print("Concurrent results:", concurrent_results)
    print(f"Concurrent elapsed: {concurrent_elapsed:.3f} seconds")


if __name__ == "__main__":
    asyncio.run(main())