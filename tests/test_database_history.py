import os
import time
import pytest
import tempfile
from app import database


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_telemetry.db"
    os.environ["YDS_DB_PATH"] = str(db_file)
    database.DB_PATH = str(db_file)
    database.init_db()

    # Populate dummy telemetry data
    for i in range(500):
        frame = {
            "status": "ok",
            "timestamp": 1000.0 + i,
            "rpm": 1000.0 + i,
            "engine_hours": 100.0 + (i * 0.1),
            "tps_percent": 15.0,
            "map_kpa": 100.0,
            "baro_hpa": 1013.0,
            "engine_temp_c": 50.0 + (i * 0.05),
            "intake_temp_c": 25.0,
            "oil_pressure_kpa": 300.0,
            "battery_voltage": 12.6,
            "fuel_rate_lh": 5.0,
            "injector_ms": 2.5,
            "warnings": {"overheat": False} if i % 2 == 0 else {"overheat": True},
            "gps_speed_kts": 10.0,
            "gps_heading_deg": 180.0,
            "gps_cardinal": "S",
            "gps_satellites": 8,
            "gps_has_fix": True,
            "gps_latitude": 25.0,
            "gps_longitude": -80.0,
            "fuel_economy_l_nm": 0.5
        }
        database.log_telemetry_frame(frame)

    yield str(db_file)


def test_get_history_ordering_and_fields(temp_db):
    history = database.get_history(limit=10)
    assert len(history) == 10

    # Ensure records are ordered chronologically ascending (oldest to newest among the latest 10)
    timestamps = [r["timestamp"] for r in history]
    assert timestamps == sorted(timestamps)

    # The latest record logged was i=499 (timestamp 1499.0)
    assert history[-1]["timestamp"] == 1499.0
    # The 10th latest record was i=490 (timestamp 1490.0)
    assert history[0]["timestamp"] == 1490.0

    # Verify field values and conversions
    rec = history[-1]
    assert "id" not in rec  # Original get_history didn't include id key
    assert rec["gps_has_fix"] is True
    assert isinstance(rec["warnings"], dict)


def test_benchmark_get_history(temp_db):
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        res = database.get_history(limit=100)
        assert len(res) == 100
    duration = time.perf_counter() - start
    print(f"\nget_history(limit=100) x {iterations} duration: {duration:.4f}s ({duration/iterations*1000:.3f}ms per call)")
