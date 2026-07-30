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
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "db", "yamaha_telemetry.db")
DB_PATH = os.getenv("YDS_DB_PATH", DEFAULT_DB_PATH)


def ensure_db_dir():
    """Ensures the database directory exists before accessing SQLite database."""
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def get_db_connection():
    """Establishes connection to SQLite database with WAL mode for fast concurrent access."""
    ensure_db_dir()
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
                warnings_json TEXT,
                gps_speed_kts REAL,
                gps_heading_deg REAL,
                gps_cardinal TEXT,
                gps_satellites INTEGER,
                gps_has_fix INTEGER,
                gps_latitude REAL,
                gps_longitude REAL,
                fuel_economy_l_nm REAL
            );
        """)

        # Migration check: Add GPS columns to telemetry_history if missing in existing DB
        cursor.execute("PRAGMA table_info(telemetry_history);")
        existing_cols = {col["name"] for col in cursor.fetchall()}

        gps_columns = [
            ("gps_speed_kts", "REAL"),
            ("gps_heading_deg", "REAL"),
            ("gps_cardinal", "TEXT"),
            ("gps_satellites", "INTEGER"),
            ("gps_has_fix", "INTEGER"),
            ("gps_latitude", "REAL"),
            ("gps_longitude", "REAL"),
            ("fuel_economy_l_nm", "REAL")
        ]

        for col_name, col_type in gps_columns:
            if col_name not in existing_cols:
                logger.info(f"Migrating SQLite schema: Adding column {col_name} ({col_type}) to telemetry_history...")
                cursor.execute(f"ALTER TABLE telemetry_history ADD COLUMN {col_name} {col_type};")

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


def update_fuel_state(current_liters: float, trip_consumed: Optional[float] = None, capacity: Optional[float] = None) -> Dict[str, Any]:
    """Updates fuel level and trip consumption in SQLite."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cur_state = get_fuel_state()
            new_rem = round(max(0.0, min(capacity or cur_state["tank_capacity_liters"], current_liters)), 2)
            new_cap = round(capacity or cur_state["tank_capacity_liters"], 1)
            new_trip = round(trip_consumed if trip_consumed is not None else cur_state["trip_consumed_liters"], 2)
            now = time.time()

            cursor.execute("""
                UPDATE fuel_state
                SET current_fuel_liters = ?, tank_capacity_liters = ?, trip_consumed_liters = ?, updated_at = ?
                WHERE id = 1;
            """, (new_rem, new_cap, new_trip, now))
            conn.commit()

            pct = round(max(0.0, min(100.0, (new_rem / new_cap) * 100.0)), 1) if new_cap > 0 else 0.0
            return {
                "current_fuel_liters": new_rem,
                "tank_capacity_liters": new_cap,
                "trip_consumed_liters": new_trip,
                "fuel_percent": pct,
                "updated_at": now
            }
    except Exception as e:
        logger.error(f"Error updating fuel state in SQLite: {e}")
        return get_fuel_state()


def adjust_fuel_level(delta_liters: float) -> Dict[str, Any]:
    """Adjusts current fuel level by delta (+/- liters) in SQLite."""
    current_state = get_fuel_state()
    new_level = current_state["current_fuel_liters"] + delta_liters
    return update_fuel_state(new_level)


def fill_tank_full(capacity: float = 170.0) -> Dict[str, Any]:
    """Fills fuel tank to full capacity in SQLite."""
    return update_fuel_state(capacity, capacity=capacity)


def reset_trip_consumed() -> Dict[str, Any]:
    """Resets trip consumed fuel counter to 0.0 in SQLite."""
    current_state = get_fuel_state()
    return update_fuel_state(current_state["current_fuel_liters"], trip_consumed=0.0, capacity=current_state["tank_capacity_liters"])


def log_telemetry_frame(data: Dict[str, Any]):
    """Logs a single telemetry snapshot frame (ECU + GPS metrics) to SQLite history table."""
    if not data or data.get("status") != "ok":
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_history (
                    timestamp, rpm, engine_hours, tps_percent, map_kpa, baro_hpa,
                    engine_temp_c, intake_temp_c, oil_pressure_kpa, battery_voltage,
                    fuel_rate_lh, injector_ms, warnings_json,
                    gps_speed_kts, gps_heading_deg, gps_cardinal, gps_satellites,
                    gps_has_fix, gps_latitude, gps_longitude, fuel_economy_l_nm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                json.dumps(data.get("warnings", {})),
                data.get("gps_speed_kts", 0.0),
                data.get("gps_heading_deg", 0.0),
                data.get("gps_cardinal", "N"),
                data.get("gps_satellites", 0),
                1 if data.get("gps_has_fix") else 0,
                data.get("gps_latitude", 0.0),
                data.get("gps_longitude", 0.0),
                data.get("fuel_economy_l_nm", 0.0)
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
                       fuel_rate_lh, injector_ms, warnings_json,
                       gps_speed_kts, gps_heading_deg, gps_cardinal, gps_satellites,
                       gps_has_fix, gps_latitude, gps_longitude, fuel_economy_l_nm
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
                rec["gps_has_fix"] = bool(rec.get("gps_has_fix", 0))
                records.append(rec)
    except Exception as e:
        logger.error(f"Error reading telemetry history from SQLite: {e}")

    return records
