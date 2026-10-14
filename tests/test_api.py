"""
AirLink - API & Health Endpoint Tests
Tests health endpoint, network information, and page routes.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["app"] == "AirDrop"
        assert "local_ip" in data
        assert "uptime_seconds" in data
        assert data["transfers_dir_exists"] is True


@pytest.mark.asyncio
async def test_network_info_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/network/info")
        assert response.status_code == 200
        data = response.json()
        assert "primary_ip" in data
        assert "access_url" in data
        assert "qr_code_svg" in data
        assert "qr_code_png" in data
        assert data["access_url"].startswith("http://")
        assert "<svg" in data["qr_code_svg"]


@pytest.mark.asyncio
async def test_page_routes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Index dashboard
        resp_index = await client.get("/")
        assert resp_index.status_code == 200
        assert "AirDrop" in resp_index.text

        # Terms of Service
        resp_terms = await client.get("/terms")
        assert resp_terms.status_code == 200
        assert "Terms of Service" in resp_terms.text

        # Privacy Policy
        resp_privacy = await client.get("/privacy")
        assert resp_privacy.status_code == 200
        assert "Privacy Policy" in resp_privacy.text
