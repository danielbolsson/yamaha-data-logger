#!/usr/bin/env python3
"""
Unit tests for Yamaha YDS Engine Temperature decoding logic (Fahrenheit to Celsius).
"""

import os
import sys
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from yds_reader import YDSReader


def test_engine_temp_cold():
    """Verify that raw opcode 0x91 value 68 °F decodes to 20.0 °C (ambient cold engine)."""
    raw_frame = {0x91: 68}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0
    assert decoded["engine_temp_f"] == 68.0


def test_engine_temp_warm():
    """Verify that raw opcode 0x91 value 109 °F decodes to 42.8 °C (warm operating engine)."""
    raw_frame = {0x91: 109}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 42.8
    assert decoded["engine_temp_f"] == 109.0


def test_engine_temp_ignores_f0():
    """
    Verify that when both opcode 0x91 (value 68 °F -> 20.0 °C) and opcode 0xF0 (value 106)
    are present in the frame, the decoder strictly uses 0x91 and ignores 0xF0.
    """
    raw_frame = {0x91: 68, 0xF0: 106}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0


def test_engine_temp_hex_string_keys():
    """Verify decoding with hex string keys as passed from JSON log files ("0x91": 68)."""
    raw_frame = {"0x91": 68, "0xF0": 106}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0


def test_engine_temp_default_when_missing():
    """Verify default fallback temperature when opcode 0x91 is missing."""
    raw_frame = {}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0
    assert decoded["engine_temp_f"] == 68.0
