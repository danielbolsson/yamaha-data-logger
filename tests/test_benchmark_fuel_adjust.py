import asyncio
import time
import pytest
import httpx
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import database
from server import app


@pytest.mark.anyio
async def test_benchmark_fuel_adjust():
    # Setup temp database
    test_db = "/tmp/test_benchmark_fuel.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    database.DB_PATH = test_db
    database.init_db()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Measure total time for concurrent requests and max loop lag
        num_requests = 100
        lags = []
        stop_ticker = False

        async def ticker():
            while not stop_ticker:
                t0 = time.perf_counter()
                await asyncio.sleep(0.001)
                t1 = time.perf_counter()
                lags.append((t1 - t0) - 0.001)

        ticker_task = asyncio.create_task(ticker())

        start_time = time.perf_counter()
        tasks = [client.post("/api/fuel/adjust", json={"delta": -0.1}) for _ in range(num_requests)]
        responses = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

        stop_ticker = True
        await ticker_task

        max_lag_ms = max(lags) * 1000 if lags else 0
        avg_lag_ms = (sum(lags) / len(lags)) * 1000 if lags else 0

        assert all(r.status_code == 200 for r in responses)
        print(f"\n--- Benchmark Results ({num_requests} concurrent requests) ---")
        print(f"Total time taken: {total_time * 1000:.2f} ms")
        print(f"Average request latency: {(total_time / num_requests) * 1000:.2f} ms")
        print(f"Max event loop lag: {max_lag_ms:.2f} ms")
        print(f"Avg event loop lag: {avg_lag_ms:.2f} ms")


if __name__ == "__main__":
    asyncio.run(test_benchmark_fuel_adjust())
