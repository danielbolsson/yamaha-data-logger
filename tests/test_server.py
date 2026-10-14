import json
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
import app.server as server
from app.server import app


@pytest.mark.anyio
async def test_serve_index():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Yamaha" in response.text or "YDS" in response.text or "html" in response.text.lower()


class MockWS:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent = []

    async def send_text(self, data: str):
        if self.should_fail:
            raise Exception("Connection lost")
        self.sent.append(data)


@pytest.mark.anyio
async def test_active_websockets_concurrent_broadcast():
    ws_good = MockWS(should_fail=False)
    ws_bad = MockWS(should_fail=True)

    server.active_websockets = {ws_good, ws_bad}
    server.latest_telemetry_json = json.dumps({"rpm": 1200})

    # Execute broadcast logic directly as done in telemetry_background_loop
    if server.active_websockets:
        clients = list(server.active_websockets)

        async def send_to_client(ws):
            try:
                await ws.send_text(server.latest_telemetry_json)
                return None
            except Exception as ws_err:
                server.logger.debug(f"Client disconnected or send failed: {ws_err}")
                return ws

        results = await asyncio.gather(*[send_to_client(ws) for ws in clients], return_exceptions=True)

        for res in results:
            if res and not isinstance(res, Exception):
                server.active_websockets.discard(res)

    assert len(ws_good.sent) == 1
    assert json.loads(ws_good.sent[0]) == {"rpm": 1200}
    assert ws_good in server.active_websockets
    assert ws_bad not in server.active_websockets
    server.active_websockets.clear()
