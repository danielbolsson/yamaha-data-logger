#!/usr/bin/env python3
"""
SQLite Database Manager for Yamaha YDS Telemetry System.
Handles persistent fuel level tracking, tank capacity configuration, trip fuel logging,
and historical telemetry data storage.
"""

import os
import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("yds_database")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "yamaha_telemetry.db")
DB_PATH = os.getenv("YDS_DB_PATH", DEFAULT_DB_PATH)


def get_db_connection():
    """Establishes connection to SQLite database with WAL mode for fast concurrent access."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """Initializes SQLite database tables and seeds default fuel state if missing."""
    logger.info(f"Initializing SQLite database at {os.path.abspath(DB_PATH)}...")
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Fuel State & Tank Config Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fuel_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_fuel_liters REAL NOT NULL DEFAULT 170.0,
                tank_capacity_liters REAL NOT NULL DEFAULT 170.0,
                trip_consumed_liters REAL NOT NULL DEFAULT 0.0,
                updated_at REAL NOT NULL
            );
        """)

        # 2. Historical Telemetry Storage Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                rpm REAL,
                engine_hours REAL,
                tps_percent REAL,
                map_kpa REAL,
                baro_hpa REAL,
                engine_temp_c REAL,
                intake_temp_c REAL,
                oil_pressure_kpa REAL,
                battery_voltage REAL,
                fuel_rate_lh REAL,
                injector_ms REAL,
                warnings_json TEXT
            );
        """)

        # Seed initial fuel row if empty
        cursor.execute("SELECT COUNT(*) FROM fuel_state WHERE id = 1;")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO fuel_state (id, current_fuel_liters, tank_capacity_liters, trip_consumed_liters, updated_at)
                VALUES (1, 170.0, 170.0, 0.0, ?);
            """, (time.time(),))

        conn.commit()
    logger.info("SQLite database initialization complete.")


def get_fuel_state() -> Dict[str, Any]:
    """Retrieves current fuel tank state and trip consumption from SQLite."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_fuel_liters, tank_capacity_liters, trip_consumed_liters, updated_at FROM fuel_state WHERE id = 1;")
            row = cursor.fetchone()
            if row:
                cap = float(row["tank_capacity_liters"])
                rem = float(row["current_fuel_liters"])
                trip = float(row["trip_consumed_liters"])
                pct = round(max(0.0, min(100.0, (rem / cap) * 100.0)), 1) if cap > 0 else 0.0
                return {
                    "current_fuel_liters": round(rem, 2),
                    "tank_capacity_liters": round(cap, 1),
                    "trip_consumed_liters": round(trip, 2),
                    "fuel_percent": pct,
                    "updated_at": row["updated_at"]
                }
    except Exception as e:
        logger.error(f"Error reading fuel state from SQLite: {e}")

    return {
        "current_fuel_liters": 170.0,
        "tank_capacity_liters": 170.0,
        "trip_consumed_liters": 0.0,
        "fuel_percent": 100.0,
        "updated_at": time.time()
    }


def update_fuel_state(current_fuel: float, trip_consumed: Optional[float] = None, capacity: float = 170.0) -> Dict[str, Any]:
    """Updates current fuel level and trip consumption in SQLite."""
    clamped_fuel = max(0.0, min(capacity, current_fuel))
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if trip_consumed is not None:
                cursor.execute("""
                    UPDATE fuel_state
                    SET current_fuel_liters = ?, trip_consumed_liters = ?, updated_at = ?
                    WHERE id = 1;
                """, (clamped_fuel, max(0.0, trip_consumed), time.time()))
            else:
                cursor.execute("""
                    UPDATE fuel_state
                    SET current_fuel_liters = ?, updated_at = ?
                    WHERE id = 1;
                """, (clamped_fuel, time.time()))
            conn.commit()
    except Exception as e:
        logger.error(f"Error updating fuel state in SQLite: {e}")

    return get_fuel_state()


def adjust_fuel_level(delta_liters: float) -> Dict[str, Any]:
    """Adjusts current fuel level by delta liters (+1, -1, +20, -20) in SQLite."""
    current_state = get_fuel_state()
    new_level = current_state["current_fuel_liters"] + delta_liters
    return update_fuel_state(new_level, capacity=current_state["tank_capacity_liters"])


def fill_tank_full(capacity: float = 170.0) -> Dict[str, Any]:
    """Resets fuel tank level to 170L full capacity in SQLite."""
    return update_fuel_state(capacity, capacity=capacity)


def reset_trip_consumed() -> Dict[str, Any]:
    """Resets trip consumed fuel counter to 0.0 in SQLite."""
    current_state = get_fuel_state()
    return update_fuel_state(current_state["current_fuel_liters"], trip_consumed=0.0, capacity=current_state["tank_capacity_liters"])


def log_telemetry_frame(data: Dict[str, Any]):
    """Logs a single telemetry snapshot frame to SQLite history table."""
    if not data or data.get("status") != "ok":
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_history (
                    timestamp, rpm, engine_hours, tps_percent, map_kpa, baro_hpa,
                    engine_temp_c, intake_temp_c, oil_pressure_kpa, battery_voltage,
                    fuel_rate_lh, injector_ms, warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                data.get("timestamp", time.time()),
                data.get("rpm", 0.0),
                data.get("engine_hours", 0.0),
                data.get("tps_percent", 0.0),
                data.get("map_kpa", 0.0),
                data.get("baro_hpa", 0.0),
                data.get("engine_temp_c", 0.0),
                data.get("intake_temp_c", 0.0),
                data.get("oil_pressure_kpa", 0.0),
                data.get("battery_voltage", 0.0),
                data.get("fuel_rate_lh", 0.0),
                data.get("injector_ms", 0.0),
                json.dumps(data.get("warnings", {}))
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging telemetry frame to SQLite: {e}")


def get_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves recent telemetry history frames from SQLite."""
    records = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, rpm, engine_hours, tps_percent, map_kpa, baro_hpa,
                       engine_temp_c, intake_temp_c, oil_pressure_kpa, battery_voltage,
                       fuel_rate_lh, injector_ms, warnings_json
                FROM telemetry_history
                ORDER BY id DESC LIMIT ?;
            """, (limit,))
            rows = cursor.fetchall()
            for r in reversed(rows):
                rec = dict(r)
                if rec.get("warnings_json"):
                    try:
                        rec["warnings"] = json.loads(rec["warnings_json"])
                    except Exception:
                        rec["warnings"] = {}
                records.append(rec)
    except Exception as e:
        logger.error(f"Error reading telemetry history from SQLite: {e}")

    return records
