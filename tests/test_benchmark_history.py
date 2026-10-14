import sys
import os
import asyncio
import time
import pytest
from httpx import AsyncClient, ASGITransport

# Ensure app directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import database
from server import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up isolated SQLite DB with sample history records for benchmark."""
    test_db = tmp_path / "benchmark_history.db"
    monkeypatch.setattr(database, "DB_PATH", str(test_db))
    database.init_db()

    sample_data = {
        "status": "ok",
        "rpm": 3000.0,
        "engine_hours": 120.0,
        "tps_percent": 15.0,
        "map_kpa": 60.0,
        "baro_hpa": 1013.0,
        "engine_temp_c": 50.0,
        "intake_temp_c": 25.0,
        "oil_pressure_kpa": 300.0,
        "battery_voltage": 13.5,
        "fuel_rate_lh": 12.0,
        "injector_ms": 2.5,
        "warnings": {"low_oil": False},
        "gps_speed_kts": 15.0,
        "gps_heading_deg": 180.0,
        "gps_cardinal": "S",
        "gps_satellites": 8,
        "gps_has_fix": True,
        "gps_latitude": 25.0,
        "gps_longitude": -80.0,
        "fuel_economy_l_nm": 0.8
    }

    # Insert 3000 history records to populate DB
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        for _ in range(3000):
            cursor.execute("""
                INSERT INTO telemetry_history (
                    timestamp, rpm, engine_hours, tps_percent, map_kpa, baro_hpa,
                    engine_temp_c, intake_temp_c, oil_pressure_kpa, battery_voltage,
                    fuel_rate_lh, injector_ms, warnings_json,
                    gps_speed_kts, gps_heading_deg, gps_cardinal, gps_satellites,
                    gps_has_fix, gps_latitude, gps_longitude, fuel_economy_l_nm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                time.time(), sample_data["rpm"], sample_data["engine_hours"], sample_data["tps_percent"],
                sample_data["map_kpa"], sample_data["baro_hpa"], sample_data["engine_temp_c"],
                sample_data["intake_temp_c"], sample_data["oil_pressure_kpa"], sample_data["battery_voltage"],
                sample_data["fuel_rate_lh"], sample_data["injector_ms"], "{}",
                sample_data["gps_speed_kts"], sample_data["gps_heading_deg"], sample_data["gps_cardinal"],
                sample_data["gps_satellites"], 1, sample_data["gps_latitude"],
                sample_data["gps_longitude"], sample_data["fuel_economy_l_nm"]
            ))
        conn.commit()
    yield


@pytest.mark.anyio
async def test_get_history_endpoint_functionality():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/history?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 50
        assert len(data["history"]) == 50


@pytest.mark.anyio
async def test_get_history_concurrent_event_loop_latency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        ticker_delays = []
        stop_ticker = False

        async def event_loop_ticker():
            while not stop_ticker:
                t0 = time.perf_counter()
                await asyncio.sleep(0.002)
                t1 = time.perf_counter()
                delay = (t1 - t0) - 0.002
                ticker_delays.append(max(0.0, delay))

        ticker_task = asyncio.create_task(event_loop_ticker())

        start_time = time.perf_counter()
        tasks = [client.get("/api/history?limit=1000") for _ in range(25)]
        responses = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

        stop_ticker = True
        await ticker_task

        for res in responses:
            assert res.status_code == 200
            assert res.json()["count"] == 1000

        max_delay = max(ticker_delays) if ticker_delays else 0.0
        avg_delay = sum(ticker_delays) / len(ticker_delays) if ticker_delays else 0.0

        print(f"\n--- History Endpoint Event Loop Latency Benchmark ---")
        print(f"Total time for 25 requests: {total_time * 1000:.2f} ms")
        print(f"Max Event Loop Ticker Delay: {max_delay * 1000:.2f} ms")
        print(f"Avg Event Loop Ticker Delay: {avg_delay * 1000:.2f} ms")
