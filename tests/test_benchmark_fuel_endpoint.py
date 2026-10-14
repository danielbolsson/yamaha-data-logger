import time
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
import app.database as database
from app.server import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up isolated SQLite DB for testing."""
    test_db = tmp_path / "test_telemetry.db"
    monkeypatch.setattr(database, "DB_PATH", str(test_db))
    database.init_db()
    yield


@pytest.mark.anyio
async def test_fuel_endpoint_concurrent_benchmark():
    num_requests = 200
    transport = ASGITransport(app=app)

    # Background heartbeat task on event loop to measure delay/blocking
    heartbeat_ticks = 0
    heartbeat_running = True

    async def heartbeat():
        nonlocal heartbeat_ticks
        while heartbeat_running:
            heartbeat_ticks += 1
            await asyncio.sleep(0.001)

    hb_task = asyncio.create_task(heartbeat())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        start_time = time.perf_counter()

        async def fetch():
            res = await client.get("/api/fuel")
            assert res.status_code == 200
            return res.json()

        results = await asyncio.gather(*[fetch() for _ in range(num_requests)])
        duration = time.perf_counter() - start_time

    heartbeat_running = False
    await hb_task

    print(f"\n--- Concurrent /api/fuel Benchmark ({num_requests} requests) ---")
    print(f"Total Duration: {duration:.4f}s")
    print(f"Throughput:     {num_requests / duration:.2f} req/s")
    print(f"Heartbeat Ticks: {heartbeat_ticks}")

    assert len(results) == num_requests
