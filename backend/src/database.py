import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite
from loguru import logger

DB_PATH = Path(__file__).parent.parent / "data" / "reports.db"


async def init_db():
    """Initialize the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                report_markdown TEXT NOT NULL,
                tasks_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")


async def save_report(topic: str, report_markdown: str, tasks: list[dict]) -> str:
    """Save a research report and return its ID."""
    report_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()

    serializable_tasks = []
    for t in tasks:
        serializable_tasks.append({
            "task_id": t.get("task_id"),
            "title": t.get("title", ""),
            "intent": t.get("intent", ""),
            "query": t.get("query", ""),
            "summary": t.get("summary", ""),
            "sources": t.get("sources", []),
            "status": t.get("status", ""),
        })

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO reports (id, topic, report_markdown, tasks_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (report_id, topic, report_markdown, json.dumps(serializable_tasks, ensure_ascii=False), created_at),
        )
        await db.commit()

    logger.info(f"Report saved: {report_id}")
    return report_id


async def get_reports(limit: int = 50, offset: int = 0) -> list[dict]:
    """List reports ordered by creation time."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT id, topic, created_at FROM reports ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_report(report_id: str) -> dict | None:
    """Get a single report by ID."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        async with db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                data["tasks"] = json.loads(data.pop("tasks_json") or "[]")
                return data
            return None


async def delete_report(report_id: str) -> bool:
    """Delete a report by ID."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        await db.commit()
        return cursor.rowcount > 0
