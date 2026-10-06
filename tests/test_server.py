import pytest
from httpx import AsyncClient, ASGITransport
from app.server import app

@pytest.mark.anyio
async def test_serve_index():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Yamaha" in response.text or "YDS" in response.text or "html" in response.text.lower()
