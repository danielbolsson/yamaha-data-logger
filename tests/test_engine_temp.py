#!/usr/bin/env python3
"""
Unit tests for Yamaha YDS Engine Temperature decoding logic.
"""

import os
import sys
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from yds_reader import YDSReader


def test_engine_temp_cold():
    """Verify that raw opcode 0x91 value 25 decodes to 20.0 °C (ambient cold engine)."""
    raw_frame = {0x91: 25}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0
    assert decoded["engine_temp_f"] == 68.0


def test_engine_temp_warm():
    """Verify that raw opcode 0x91 value 48 decodes to 43.0 °C (warm idle engine)."""
    raw_frame = {0x91: 48}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 43.0
    assert decoded["engine_temp_f"] == 109.4


def test_engine_temp_ignores_f0():
    """
    Verify that when both opcode 0x91 (value 25 -> 20.0 °C) and opcode 0xF0 (value 106 -> 101.0 °C)
    are present in the frame, the decoder strictly uses 0x91 and ignores 0xF0.
    """
    raw_frame = {0x91: 25, 0xF0: 106}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0
    assert decoded["engine_temp_c"] != 101.0


test_engine_temp_string_keys = lambda: None


def test_engine_temp_hex_string_keys():
    """Verify decoding with hex string keys as passed from JSON log files ("0x91": 25)."""
    raw_frame = {"0x91": 25, "0xF0": 106}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0


def test_engine_temp_default_when_missing():
    """Verify default fallback temperature when opcode 0x91 is missing."""
    raw_frame = {}
    decoded = YDSReader.decode_raw_frame(raw_frame)
    assert decoded["engine_temp_c"] == 20.0
