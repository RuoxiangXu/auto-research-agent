"""Tests for main.py API endpoints (non-streaming)."""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport

from src import database
from src.main import app


@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    db_path = tmp_path / "test_reports.db"
    with patch.object(database, "DB_PATH", db_path):
        yield db_path


@pytest_asyncio.fixture
async def client(_temp_db):
    await database.init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_reports_empty(client):
    resp = await client.get("/reports")
    assert resp.status_code == 200
    assert resp.json() == {"reports": []}


@pytest.mark.asyncio
async def test_report_crud(client):
    # Save a report directly
    report_id = await database.save_report("test topic", "# Report content", [])

    # List
    resp = await client.get("/reports")
    assert resp.status_code == 200
    reports = resp.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["topic"] == "test topic"

    # Get by ID
    resp = await client.get(f"/reports/{report_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_markdown"] == "# Report content"

    # Delete
    resp = await client.delete(f"/reports/{report_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = await client.get(f"/reports/{report_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_report_not_found(client):
    resp = await client.get("/reports/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_report_not_found(client):
    resp = await client.delete("/reports/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_research_stream_empty_topic(client):
    resp = await client.post("/research/stream", json={"topic": "  "})
    assert resp.status_code == 400
