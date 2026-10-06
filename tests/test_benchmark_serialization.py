import time
import json
import pytest

SAMPLE_TELEMETRY = {
    "status": "ok",
    "rpm": 3450.0,
    "hours": 498.4,
    "engine_temp_c": 42.8,
    "oil_pressure_kpa": 347.4,
    "map_kpa": 51.21,
    "current_fuel_liters": 142.5,
    "tank_capacity_liters": 170.0,
    "trip_consumed_liters": 27.5,
    "fuel_percent": 83.8,
    "gps": {
        "speed_knots": 24.5,
        "speed_kmh": 45.37,
        "track_deg": 182.5,
        "cardinal_heading": "S",
        "satellites": 9,
        "has_fix": True,
        "latitude": 25.7617,
        "longitude": -80.1918
    },
    "gps_speed_kts": 24.5,
    "gps_speed_kmh": 45.37,
    "gps_heading_deg": 182.5,
    "gps_cardinal": "S",
    "gps_satellites": 9,
    "gps_has_fix": True,
    "gps_latitude": 25.7617,
    "gps_longitude": -80.1918,
    "fuel_economy_l_nm": 0.82
}


def benchmark_uncached_serialization(iterations=100000):
    start = time.perf_counter()
    for _ in range(iterations):
        # Uncached: serialization happens when broadcasting and whenever new clients connect
        _payload = json.dumps(SAMPLE_TELEMETRY)
        # Simulate new client connecting or broadcasting snapshot
        _snapshot = json.dumps(SAMPLE_TELEMETRY)
    duration = time.perf_counter() - start
    return duration


def benchmark_cached_serialization(iterations=100000):
    start = time.perf_counter()
    for _ in range(iterations):
        # Cached: serialized once when telemetry dict is updated
        cached_json = json.dumps(SAMPLE_TELEMETRY)
        _payload = cached_json
        _snapshot = cached_json
    duration = time.perf_counter() - start
    return duration


def test_serialization_benchmark():
    iterations = 100000
    uncached_time = benchmark_uncached_serialization(iterations)
    cached_time = benchmark_cached_serialization(iterations)

    print(f"\n--- Benchmark Results ({iterations} iterations) ---")
    print(f"Uncached Serialization Time: {uncached_time:.4f}s")
    print(f"Cached Serialization Time:   {cached_time:.4f}s")
    speedup = ((uncached_time - cached_time) / uncached_time) * 100
    print(f"Performance Improvement:    {speedup:.2f}% faster")

    assert cached_time <= uncached_time


if __name__ == "__main__":
    test_serialization_benchmark()
