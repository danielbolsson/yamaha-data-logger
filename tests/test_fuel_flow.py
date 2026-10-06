#!/usr/bin/env python3
"""
Unit tests for Yamaha YDS calculate_fuel_flow logic in app/yds_reader.py.
"""

import os
import sys
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from yds_reader import YDSReader


@pytest.fixture
def yds_reader():
    """Provides a YDSReader instance in mock mode."""
    return YDSReader(mock_mode=True)


def test_calculate_fuel_flow_idle(yds_reader):
    """
    Verify fuel flow calculation under normal idle conditions.
    Formula: round(rpm * (injector_ms - 0.95) * 0.00142, 2)
    For 650 RPM and 2.58 ms injector pulse:
    650 * 1.63 * 0.00142 = 1.50449 -> 1.5 L/h.
    """
    result = yds_reader.calculate_fuel_flow(rpm=650.0, injector_ms=2.58)
    assert result == 1.5


def test_calculate_fuel_flow_cruise(yds_reader):
    """
    Verify fuel flow calculation at higher RPM and injector pulse width.
    For 3000 RPM and 4.50 ms injector pulse:
    3000 * 3.55 * 0.00142 = 15.123 -> 15.12 L/h.
    """
    result = yds_reader.calculate_fuel_flow(rpm=3000.0, injector_ms=4.50)
    expected = round(3000.0 * (4.50 - 0.95) * 0.00142, 2)
    assert result == expected
    assert result == 15.12


def test_calculate_fuel_flow_at_rpm_threshold(yds_reader):
    """
    Verify that if RPM <= 50.0, calculate_fuel_flow returns 0.0.
    """
    assert yds_reader.calculate_fuel_flow(rpm=50.0, injector_ms=2.58) == 0.0
    assert yds_reader.calculate_fuel_flow(rpm=0.0, injector_ms=2.58) == 0.0


def test_calculate_fuel_flow_at_injector_threshold(yds_reader):
    """
    Verify that if injector_ms <= 0.95, calculate_fuel_flow returns 0.0.
    """
    assert yds_reader.calculate_fuel_flow(rpm=650.0, injector_ms=0.95) == 0.0
    assert yds_reader.calculate_fuel_flow(rpm=650.0, injector_ms=0.0) == 0.0


def test_calculate_fuel_flow_just_above_thresholds(yds_reader):
    """
    Verify behavior when inputs are strictly above the threshold values.
    For RPM = 50.1 and injector_ms = 0.96:
    50.1 * (0.96 - 0.95) * 0.00142 = 0.00071142 -> 0.0 L/h after rounding.
    """
    result = yds_reader.calculate_fuel_flow(rpm=50.1, injector_ms=0.96)
    expected = round(50.1 * (0.96 - 0.95) * 0.00142, 2)
    assert result == expected
    assert result == 0.0


def test_calculate_fuel_flow_negative_inputs(yds_reader):
    """
    Verify that negative RPM or injector pulse values return 0.0.
    """
    assert yds_reader.calculate_fuel_flow(rpm=-500.0, injector_ms=2.58) == 0.0
    assert yds_reader.calculate_fuel_flow(rpm=650.0, injector_ms=-1.0) == 0.0
    assert yds_reader.calculate_fuel_flow(rpm=-100.0, injector_ms=-0.5) == 0.0


def test_decode_raw_frame_fuel_flow_integration():
    """
    Verify that decode_raw_frame correctly computes fuel_rate_lh using RPM and injector_ms.
    """
    # Raw RPM = 650 (0x028A -> High 0x02, Low 0x8A)
    # Raw Injector = 2580 us (0x0A14 -> High 0x0A, Low 0x14) -> 2.58 ms
    raw_frame = {
        0x00: 0x02,
        0x01: 0x8A,
        0x0E: 0x0A,
        0x0F: 0x14
    }
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["rpm"] == 650.0
    assert decoded["injector_ms"] == 2.58
    assert decoded["fuel_rate_lh"] == 1.5
