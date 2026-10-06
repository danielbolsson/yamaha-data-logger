#!/usr/bin/env python3
"""
Unit tests for YDSReader._error_payload in app/yds_reader.py.
Verifies structure, default metric values, error message propagation,
mock flag handling, and offline error snapshots.
"""

import os
import sys
import time
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from yds_reader import YDSReader


def test_error_payload_structure_and_defaults():
    """Verify that _error_payload returns a dictionary with correct default fields and values."""
    reader = YDSReader(mock_mode=True)
    before_time = time.time()
    payload = reader._error_payload("Serial Port Disconnected")
    after_time = time.time()

    assert payload["status"] == "offline"
    assert payload["connected"] is False
    assert payload["error"] == "Serial Port Disconnected"
    assert before_time <= payload["timestamp"] <= after_time

    # Default telemetry metrics
    assert payload["rpm"] == 0.0
    assert payload["engine_temp_c"] == 0.0
    assert payload["engine_temp_f"] == 32.0
    assert payload["intake_temp_c"] == 0.0
    assert payload["intake_temp_f"] == 32.0
    assert payload["tps_percent"] == 0.0
    assert payload["tps_volts"] == 0.0
    assert payload["map_kpa"] == 0.0
    assert payload["baro_hpa"] == 0.0
    assert payload["oil_pressure_kpa"] == 0.0
    assert payload["oil_pressure_psi"] == 0.0
    assert payload["injector_ms"] == 0.0
    assert payload["fuel_rate_lh"] == 0.0
    assert payload["battery_voltage"] == 0.0
    assert payload["engine_hours"] == 0.0
    assert payload["shift_neutral"] is True

    # Default warnings dictionary and flags
    expected_warnings = {
        "overheat": False,
        "low_oil_pressure": False,
        "check_engine": False,
        "low_voltage": False,
        "water_in_fuel": False
    }
    assert payload["warnings"] == expected_warnings
    assert payload["has_warnings"] is False
    assert payload["raw_hex"] == ""


def test_error_payload_custom_error_messages():
    """Verify that _error_payload correctly propagates custom error strings including empty and special strings."""
    reader = YDSReader(mock_mode=True)

    test_messages = [
        "",
        "Ignition OFF / Cable Unplugged",
        "ECU Not Responding (TX Echo Only - Check Key Switch & Wiring)",
        "Read Error: [Timeout 0.15s] on /dev/ttyUSB0",
        "Replay File Empty or Not Found"
    ]

    for msg in test_messages:
        payload = reader._error_payload(msg)
        assert payload["error"] == msg


def test_error_payload_is_mock_flag():
    """Verify that is_mock in _error_payload reflects reader.mock_mode."""
    reader_mock = YDSReader(mock_mode=True)
    payload_mock = reader_mock._error_payload("Test Error")
    assert payload_mock["is_mock"] is True

    reader_real = YDSReader(port="/dev/nonexistent_port_12345", mock_mode=False)
    # Ensure mock_mode matches reader_real.mock_mode setting
    payload_real = reader_real._error_payload("Test Error")
    assert payload_real["is_mock"] == reader_real.mock_mode


def test_read_telemetry_disconnected_returns_error_payload():
    """Verify that read_telemetry returns an error payload when disconnected."""
    reader = YDSReader(port="/dev/nonexistent_port_12345", mock_mode=False)
    reader.is_connected = False

    payload = reader.read_telemetry()
    assert payload["status"] == "offline"
    assert payload["connected"] is False
    assert "Disconnected" in payload["error"] or "Error" in payload["error"]


def test_read_replay_telemetry_empty_file_returns_error_payload(tmp_path):
    """Verify that reading replay telemetry from an empty file returns _error_payload."""
    empty_file = str(tmp_path / "empty_replay.json")
    open(empty_file, "w").close()

    reader = YDSReader(replay_file=empty_file)
    payload = reader.read_telemetry()

    assert payload["status"] == "offline"
    assert payload["connected"] is False
    assert payload["error"] == "Replay File Empty or Not Found"
