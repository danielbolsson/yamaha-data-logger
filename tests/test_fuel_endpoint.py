import sys
import os
import math
import pytest
from fastapi.testclient import TestClient

# Ensure app directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import database
from server import app


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Set up isolated SQLite DB for testing."""
    test_db = tmp_path / "test_telemetry.db"
    monkeypatch.setattr(database, "DB_PATH", str(test_db))
    database.init_db()
    yield


def test_adjust_fuel_valid():
    client = TestClient(app)
    response = client.post("/api/fuel/adjust", json={"delta": 10.0})
    assert response.status_code == 200
    data = response.json()
    assert "current_fuel_liters" in data
    assert data["current_fuel_liters"] == 170.0  # Max capacity capped at 170.0

    # Decrease by 20 L
    response = client.post("/api/fuel/adjust", json={"delta": -20.0})
    assert response.status_code == 200
    data = response.json()
    assert data["current_fuel_liters"] == 150.0


def test_adjust_fuel_invalid_string():
    client = TestClient(app)
    response = client.post("/api/fuel/adjust", json={"delta": "not_a_number"})
    assert response.status_code == 400
    assert "error" in response.json()


def test_adjust_fuel_null_value():
    client = TestClient(app)
    response = client.post("/api/fuel/adjust", json={"delta": None})
    assert response.status_code == 400
    assert "error" in response.json()


def test_adjust_fuel_nan_and_inf():
    client = TestClient(app)

    response = client.post("/api/fuel/adjust", json={"delta": "NaN"})
    assert response.status_code == 400
    assert "error" in response.json()

    response = client.post("/api/fuel/adjust", json={"delta": "Infinity"})
    assert response.status_code == 400
    assert "error" in response.json()


def test_adjust_fuel_complex_type():
    client = TestClient(app)
    response = client.post("/api/fuel/adjust", json={"delta": [1, 2, 3]})
    assert response.status_code == 400
    assert "error" in response.json()


def test_database_adjust_fuel_defensive():
    # Test direct database function with invalid inputs
    state = database.adjust_fuel_level("invalid")
    assert state["current_fuel_liters"] == 170.0

    state = database.adjust_fuel_level(float("nan"))
    assert state["current_fuel_liters"] == 170.0

    state = database.adjust_fuel_level(float("inf"))
    assert state["current_fuel_liters"] == 170.0
