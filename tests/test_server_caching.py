import json
from fastapi.testclient import TestClient
import app.server as server

def test_server_latest_telemetry_json_caching():
    # Simulate telemetry update
    sample_data = {"rpm": 2500, "status": "ok", "engine_temp_c": 40.0}
    server.latest_telemetry = sample_data
    server.latest_telemetry_json = json.dumps(sample_data)

    client = TestClient(server.app)

    # Test /api/status endpoint
    response = client.get("/api/status")
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["latest_telemetry"] == sample_data
    assert json.loads(server.latest_telemetry_json) == sample_data
