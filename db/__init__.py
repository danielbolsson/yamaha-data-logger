"""
Database package for Yamaha Data Logger.
"""
from .database import (
    init_db,
    get_db_connection,
    get_fuel_state,
    update_fuel_state,
    adjust_fuel_level,
    fill_tank_full,
    reset_trip_consumed,
    log_telemetry_frame,
    get_history
)
