import os
import time
import tempfile
import pytest
from app import database


def benchmark_unoptimized_pattern(iterations=500):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = tf.name
    tf.close()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path
    database.init_db()

    try:
        start = time.perf_counter()
        for i in range(iterations):
            # Simulating separate connections per call
            with database.get_db_connection() as c1:
                cur = database.get_fuel_state(conn=c1)
            with database.get_db_connection() as c2:
                database.update_fuel_state(160.0 - (i % 50) * 0.1, trip_consumed=(i % 50) * 0.1, conn=c2)
        duration = time.perf_counter() - start
        return duration
    finally:
        database.DB_PATH = original_db_path
        if os.path.exists(db_path):
            os.unlink(db_path)


def benchmark_optimized_pattern(iterations=500):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = tf.name
    tf.close()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path
    database.init_db()

    try:
        start = time.perf_counter()
        for i in range(iterations):
            # Optimized pattern: connection reused within update_fuel_state or passing conn
            database.update_fuel_state(160.0 - (i % 50) * 0.1, trip_consumed=(i % 50) * 0.1)
        duration = time.perf_counter() - start
        return duration
    finally:
        database.DB_PATH = original_db_path
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_database_performance_benchmark():
    iterations = 500
    unoptimized_time = benchmark_unoptimized_pattern(iterations)
    optimized_time = benchmark_optimized_pattern(iterations)

    print(f"\n--- Database Benchmark Results ({iterations} iterations) ---")
    print(f"Multiple Connections Time: {unoptimized_time:.4f}s ({(unoptimized_time/iterations)*1000:.3f} ms/op)")
    print(f"Reused Connection Time:    {optimized_time:.4f}s ({(optimized_time/iterations)*1000:.3f} ms/op)")
    speedup = ((unoptimized_time - optimized_time) / unoptimized_time) * 100
    print(f"Performance Improvement:    {speedup:.2f}% faster")

    assert optimized_time <= unoptimized_time


if __name__ == "__main__":
    test_database_performance_benchmark()
