"""Tests for database.py CRUD operations."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

from src import database


@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test_reports.db"
    with patch.object(database, "DB_PATH", db_path):
        yield db_path


@pytest.mark.asyncio
async def test_init_db_creates_table(_temp_db):
    await database.init_db()
    assert _temp_db.exists()


@pytest.mark.asyncio
async def test_save_and_get_report(_temp_db):
    await database.init_db()

    tasks = [{"task_id": 1, "title": "T1", "summary": "S1", "sources": [], "status": "completed"}]
    report_id = await database.save_report("test topic", "# Report", tasks)

    assert report_id is not None
    assert len(report_id) > 0

    report = await database.get_report(report_id)
    assert report is not None
    assert report["topic"] == "test topic"
    assert report["report_markdown"] == "# Report"
    assert len(report["tasks"]) == 1
    assert report["tasks"][0]["title"] == "T1"


@pytest.mark.asyncio
async def test_get_nonexistent_report(_temp_db):
    await database.init_db()
    report = await database.get_report("nonexistent-id")
    assert report is None


@pytest.mark.asyncio
async def test_get_reports_ordering(_temp_db):
    await database.init_db()

    await database.save_report("topic A", "report A", [])
    await database.save_report("topic B", "report B", [])
    await database.save_report("topic C", "report C", [])

    reports = await database.get_reports()
    assert len(reports) == 3
    # Most recent first
    assert reports[0]["topic"] == "topic C"
    assert reports[2]["topic"] == "topic A"


@pytest.mark.asyncio
async def test_get_reports_limit_offset(_temp_db):
    await database.init_db()

    for i in range(5):
        await database.save_report(f"topic {i}", f"report {i}", [])

    reports = await database.get_reports(limit=2, offset=0)
    assert len(reports) == 2

    reports = await database.get_reports(limit=2, offset=3)
    assert len(reports) == 2


@pytest.mark.asyncio
async def test_delete_report(_temp_db):
    await database.init_db()
    report_id = await database.save_report("to delete", "content", [])

    success = await database.delete_report(report_id)
    assert success is True

    report = await database.get_report(report_id)
    assert report is None


@pytest.mark.asyncio
async def test_delete_nonexistent_report(_temp_db):
    await database.init_db()
    success = await database.delete_report("nonexistent")
    assert success is False
