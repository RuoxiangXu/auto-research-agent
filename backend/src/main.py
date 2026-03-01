import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from .config import get_config
from .database import delete_report, get_report, get_reports, init_db, save_report
from .graph import build_graph
from .search import close_mcp_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    cfg = get_config()
    logger.info(f"AutoResearch started | LLM={cfg.llm_model_id} | Search={cfg.search_api}")
    yield
    await close_mcp_session()
    logger.info("AutoResearch stopped")


app = FastAPI(title="AutoResearch", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    topic: str
    search_api: Optional[str] = None


# ── Research endpoints ───────────────────────────────────────────────────────


@app.post("/research/stream")
async def research_stream(request: ResearchRequest):
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    if len(topic) > 500:
        raise HTTPException(status_code=400, detail="Topic must be 500 characters or less")

    cfg = get_config()
    search_api = request.search_api or cfg.search_api
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    graph = build_graph()

    async def run_graph():
        try:
            result = await graph.ainvoke(
                {
                    "topic": topic,
                    "search_api": search_api,
                    "tasks": [],
                    "completed_tasks": [],
                    "report": "",
                },
                config={"configurable": {"event_queue": queue}},
            )

            report = result.get("report", "")
            completed = result.get("completed_tasks", [])

            report_id = None
            if report:
                report_id = await save_report(topic, report, completed)

            await queue.put({
                "type": "final_report",
                "report": report,
                "report_id": report_id,
            })
        except Exception as e:
            logger.error(f"Research failed: {e}")
            await queue.put({"type": "error", "detail": str(e)})
        finally:
            await queue.put({"type": "done"})

    async def event_generator():
        task = asyncio.create_task(run_graph())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Report history endpoints ─────────────────────────────────────────────────


@app.get("/reports")
async def list_reports(limit: int = 50, offset: int = 0):
    reports = await get_reports(limit, offset)
    return {"reports": reports}


@app.get("/reports/{report_id}")
async def get_report_by_id(report_id: str):
    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.delete("/reports/{report_id}")
async def delete_report_by_id(report_id: str):
    success = await delete_report(report_id)
    if not success:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "deleted"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    cfg = get_config()
    uvicorn.run("src.main:app", host=cfg.host, port=cfg.port, reload=True)
