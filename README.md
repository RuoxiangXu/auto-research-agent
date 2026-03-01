# Auto Research Agent

AI-powered deep research assistant built with LangGraph. Given a research topic, it automatically plans sub-tasks, searches the web in parallel, summarizes findings with self-correction, and generates a structured report with proper citations.

## Architecture

```
START → Planner → Execute All Tasks (parallel) → Reporter → END
```

### Agents

| Agent | Role | Node |
|-------|------|------|
| **Planner** | Decomposes topic into 3-5 complementary research sub-tasks | `plan` |
| **Summarizer** | Summarizes search results for each sub-task with source citations | `execute_all_tasks` |
| **Evaluator** | Assesses summary quality, triggers retry with refined queries if needed | `execute_all_tasks` |
| **Reporter** | Synthesizes all summaries into a final report with unified numbered references | `report` |

### Per-Task Flow (inside `execute_all_tasks`)

```
Search (perform_search) → Summarizer → Evaluator
                                          │
                              needs_retry? ├── No → done
                                          └── Yes → Search (refined) → Summarizer → done
```

All sub-tasks run **in parallel** via `asyncio.gather`. The Reporter only starts after every task completes.

### Search Providers

- **Tavily** — via API or MCP server
- **DuckDuckGo** — free, no API key needed

## Tech Stack

- **Backend**: Python, FastAPI, LangGraph, LangChain, SSE streaming
- **Frontend**: Vue 3, TypeScript, Vite, Marked (markdown rendering)
- **LLM**: Any OpenAI-compatible API
- **Database**: SQLite (aiosqlite) for report history

## Quick Start

### Backend

```bash
cd backend
pip install -e .
cp .env.example .env   # Edit with your API keys
python -m uvicorn src.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5174` in your browser.

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL_ID` | Model name for OpenAI-compatible API | `gpt-4.1-mini` |
| `LLM_API_KEY` | API key | - |
| `LLM_BASE_URL` | Base URL for the API | - |
| `SEARCH_API` | Search provider: `tavily`, `duckduckgo`, or `mcp` | `duckduckgo` |
| `TAVILY_API_KEY` | Tavily API key (if using tavily/mcp) | - |
| `MAX_RETRY_COUNT` | Self-correction retries per task (0 to disable) | `1` |

## License

MIT
