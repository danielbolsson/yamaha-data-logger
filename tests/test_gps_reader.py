#!/usr/bin/env python3
"""
Unit tests for NMEA coordinate parsing in GPSReader (_parse_nmea_coord).
"""

import os
import sys
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from gps_reader import GPSReader


@pytest.fixture
def gps_reader():
    """Returns a mock-mode GPSReader instance for testing helper methods."""
    return GPSReader(mock_mode=True)


def test_parse_nmea_coord_north_latitude(gps_reader):
    """Verify parsing standard North latitude string (ddmm.mmmm, 'N')."""
    # 57 deg 42.5322 min N => 57 + (42.5322 / 60) = 57.70887
    lat = gps_reader._parse_nmea_coord("5742.5322", "N")
    assert lat == 57.70887


def test_parse_nmea_coord_south_latitude(gps_reader):
    """Verify parsing South latitude string returns negative decimal degrees."""
    # 33 deg 51.8833 min S => 33 + (51.8833 / 60) = 33.8647216... => -33.86472
    lat = gps_reader._parse_nmea_coord("3351.8833", "S")
    assert lat == -33.86472


def test_parse_nmea_coord_east_longitude(gps_reader):
    """Verify parsing East longitude string (dddmm.mmmm, 'E')."""
    # 011 deg 58.4736 min E => 11 + (58.4736 / 60) = 11.97456
    lon = gps_reader._parse_nmea_coord("01158.4736", "E")
    assert lon == 11.97456


def test_parse_nmea_coord_west_longitude(gps_reader):
    """Verify parsing West longitude string returns negative decimal degrees."""
    # 118 deg 14.5000 min W => 118 + (14.5 / 60) = 118.241666... => -118.24167
    lon = gps_reader._parse_nmea_coord("11814.5000", "W")
    assert lon == -118.24167


def test_parse_nmea_coord_case_insensitive_hemisphere(gps_reader):
    """Verify hemisphere parameter handles lowercase characters 's' and 'w'."""
    lat = gps_reader._parse_nmea_coord("3351.8833", "s")
    assert lat == -33.86472

    lon = gps_reader._parse_nmea_coord("11814.5000", "w")
    assert lon == -118.24167


def test_parse_nmea_coord_zero_value(gps_reader):
    """Verify parsing 0000.0000 string returns 0.0."""
    coord = gps_reader._parse_nmea_coord("0000.0000", "N")
    assert coord == 0.0


def test_parse_nmea_coord_invalid_strings(gps_reader):
    """Verify handling of invalid, empty, or malformed coordinate strings gracefully returns 0.0."""
    assert gps_reader._parse_nmea_coord("", "N") == 0.0
    assert gps_reader._parse_nmea_coord("invalid", "N") == 0.0
    assert gps_reader._parse_nmea_coord("5742.5322.11", "N") == 0.0


def test_parse_nmea_coord_invalid_types(gps_reader):
    """Verify handling of None or non-string inputs returns 0.0 without throwing exceptions."""
    assert gps_reader._parse_nmea_coord(None, "N") == 0.0
    assert gps_reader._parse_nmea_coord("5742.5322", None) == 0.0
