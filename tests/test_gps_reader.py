#!/usr/bin/env python3
"""
Unit tests for GPSReader deg_to_cardinal compass heading conversion.
"""

import os
import sys
import pytest

# Ensure app directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from gps_reader import GPSReader


@pytest.mark.parametrize(
    "deg, expected",
    [
        (0.0, "N"),
        (22.5, "NNE"),
        (45.0, "NE"),
        (67.5, "ENE"),
        (90.0, "E"),
        (112.5, "ESE"),
        (135.0, "SE"),
        (157.5, "SSE"),
        (180.0, "S"),
        (202.5, "SSW"),
        (225.0, "SW"),
        (247.5, "WSW"),
        (270.0, "W"),
        (292.5, "WNW"),
        (315.0, "NW"),
        (337.5, "NNW"),
    ],
)
def test_deg_to_cardinal_midpoints(deg, expected):
    """Verify that all 16 cardinal direction midpoints convert to their expected strings."""
    assert GPSReader.deg_to_cardinal(deg) == expected


@pytest.mark.parametrize(
    "deg, expected",
    [
        # Sector 0 (N): [-11.25, 11.25)
        (0.0, "N"),
        (11.24, "N"),
        # Transition to NNE at 11.25
        (11.25, "NNE"),
        (33.74, "NNE"),
        # Transition to NE at 33.75
        (33.75, "NE"),
        (56.24, "NE"),
        # Transition to ENE at 56.25
        (56.25, "ENE"),
        # Transition to NNW at 326.25
        (326.25, "NNW"),
        (348.74, "NNW"),
        # Transition to N at 348.75
        (348.75, "N"),
        (359.99, "N"),
    ],
)
def test_deg_to_cardinal_boundaries(deg, expected):
    """Verify boundary values around direction sector transitions."""
    assert GPSReader.deg_to_cardinal(deg) == expected


def test_deg_to_cardinal_wraparound_and_full_circle():
    """Verify behavior for 360 degrees and degree values beyond 360."""
    assert GPSReader.deg_to_cardinal(360.0) == "N"
    assert GPSReader.deg_to_cardinal(382.5) == "NNE"
    assert GPSReader.deg_to_cardinal(405.0) == "NE"
    assert GPSReader.deg_to_cardinal(720.0) == "N"


def test_deg_to_cardinal_types():
    """Verify deg_to_cardinal handles integer and float inputs."""
    assert GPSReader.deg_to_cardinal(0) == "N"
    assert GPSReader.deg_to_cardinal(90) == "E"
    assert GPSReader.deg_to_cardinal(180) == "S"
    assert GPSReader.deg_to_cardinal(270) == "W"
