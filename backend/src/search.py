import asyncio
import json
import os
import re

from loguru import logger

from .config import get_config


# ── MCP session cache ────────────────────────────────────────────────────────

_mcp_session = None
_mcp_streams = None
_mcp_cm = None
_mcp_session_cm = None
_mcp_lock = asyncio.Lock()


async def _get_mcp_session():
    """Get or create a cached MCP client session."""
    global _mcp_session, _mcp_streams, _mcp_cm, _mcp_session_cm

    if _mcp_session is not None:
        return _mcp_session

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    config = get_config()
    full_env = {**os.environ, **config.mcp_server_env}

    server_params = StdioServerParameters(
        command=config.mcp_server_command,
        args=config.mcp_server_args,
        env=full_env,
    )

    _mcp_cm = stdio_client(server_params)
    _mcp_streams = await _mcp_cm.__aenter__()
    _mcp_session_cm = ClientSession(*_mcp_streams)
    _mcp_session = await _mcp_session_cm.__aenter__()
    await _mcp_session.initialize()

    return _mcp_session


async def close_mcp_session():
    """Close the cached MCP session if open."""
    global _mcp_session, _mcp_streams, _mcp_cm, _mcp_session_cm

    if _mcp_session_cm is not None:
        try:
            await _mcp_session_cm.__aexit__(None, None, None)
        except Exception:
            pass
    if _mcp_cm is not None:
        try:
            await _mcp_cm.__aexit__(None, None, None)
        except Exception:
            pass

    _mcp_session = None
    _mcp_streams = None
    _mcp_cm = None
    _mcp_session_cm = None


# ── Public API ───────────────────────────────────────────────────────────────


async def perform_search(
    query: str, search_api: str = "tavily"
) -> tuple[list[dict], str]:
    """Perform web search using the configured provider.

    Returns (results, actual_provider) where actual_provider may differ
    from search_api if a fallback occurred.
    """
    config = get_config()
    max_results = config.max_search_results
    actual_provider = search_api

    if search_api == "tavily":
        results = await _search_tavily(query, config.tavily_api_key, max_results)
    elif search_api == "mcp":
        results, actual_provider = await _search_mcp(query)
    else:
        results = await _search_duckduckgo(query, max_results)
        actual_provider = "duckduckgo"

    if results:
        titles = [r.get("title", "N/A")[:40] for r in results]
        logger.info(f"[Search] query={query!r} → {len(results)} results via {actual_provider}: {titles}")
    else:
        logger.warning(f"[Search] query={query!r} → no results via {actual_provider}")

    return results, actual_provider


async def _search_tavily(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily API."""
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=api_key)
        response = await client.search(
            query=query,
            max_results=max_results,
            include_raw_content=True,
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "raw_content": (r.get("raw_content") or "")[:8000],
            })
        return results
    except Exception as e:
        logger.error(f"[Search] Tavily failed: {e}")
        return []


async def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """Search using DuckDuckGo."""
    try:
        from ddgs import DDGS

        def _sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        raw_results = await asyncio.to_thread(_sync_search)
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "content": r.get("body", ""),
                "raw_content": "",
            })
        return results
    except Exception as e:
        logger.error(f"[Search] DuckDuckGo failed: {e}")
        return []


async def _search_mcp(query: str) -> tuple[list[dict], str]:
    """Search using an MCP server. Returns (results, actual_provider)."""
    config = get_config()

    if not config.mcp_server_command:
        logger.warning("[Search] MCP not configured, falling back to DuckDuckGo")
        results = await _search_duckduckgo(query)
        return results, "duckduckgo"

    try:
        async with _mcp_lock:
            session = await _get_mcp_session()

        tools = await session.list_tools()
        tool_names = [t.name for t in tools.tools]

        tool_name = config.mcp_tool_name
        if tool_name not in tool_names and tool_names:
            logger.warning(
                f"[Search] MCP tool '{tool_name}' not found, "
                f"using '{tool_names[0]}' instead"
            )
            tool_name = tool_names[0]

        result = await session.call_tool(
            tool_name,
            {"query": query},
        )

        if result.content:
            for block in result.content:
                text = getattr(block, "text", None)
                if not text:
                    continue

                try:
                    data = json.loads(text)
                    if isinstance(data, list):
                        return _normalize_mcp_results(data), "mcp"
                    if isinstance(data, dict) and "results" in data:
                        return _normalize_mcp_results(data["results"]), "mcp"
                    if isinstance(data, dict):
                        return _normalize_mcp_results([data]), "mcp"
                except json.JSONDecodeError:
                    urls = re.findall(r'https?://[^\s\)\]\"\']+', text)
                    if urls:
                        return _parse_text_with_urls(text, urls, query), "mcp"
                    return [{
                        "title": query,
                        "url": "",
                        "content": text[:4000],
                        "raw_content": text[:8000],
                    }], "mcp"
        return [], "mcp"
    except Exception as e:
        logger.error(f"[Search] MCP failed: {e}, falling back to DuckDuckGo")
        # Reset broken session so next call creates a new one
        await close_mcp_session()
        results = await _search_duckduckgo(query)
        return results, "duckduckgo"


def _parse_text_with_urls(text: str, urls: list[str], query: str) -> list[dict]:
    """Parse structured plain-text results (Title:/URL:/Content: blocks) from MCP."""
    blocks = re.split(r'\n(?=Title:\s)', text)
    results = []
    seen_urls = set()

    for block in blocks:
        title_m = re.search(r'Title:\s*(.+?)(?:\n|$)', block)
        url_m = re.search(r'URL:\s*(https?://\S+)', block)
        content_m = re.search(r'Content:\s*(.+)', block, re.DOTALL)

        if not url_m:
            continue

        url = url_m.group(1).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = title_m.group(1).strip() if title_m else ""
        content = content_m.group(1).strip() if content_m else ""

        if not title:
            title = url.split('/')[2] if len(url.split('/')) > 2 else query

        results.append({
            "title": title,
            "url": url,
            "content": content[:4000],
            "raw_content": content[:8000],
        })

    if results:
        return results

    return [{"title": query, "url": "", "content": text[:4000], "raw_content": text[:8000]}]


def _normalize_mcp_results(raw: list) -> list[dict]:
    """Normalize MCP search results to the standard format."""
    results = []
    for r in raw:
        if isinstance(r, dict):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", r.get("href", r.get("link", ""))),
                "content": r.get("content", r.get("snippet", r.get("body", r.get("description", "")))),
                "raw_content": r.get("raw_content", r.get("rawContent", ""))[:8000],
            })
    return results


def format_search_context(results: list[dict]) -> str:
    """Format search results into context string for LLM."""
    if not results:
        return "（未找到搜索结果）"

    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "N/A")
        url = r.get("url", "")
        content = r.get("content", "")
        raw = r.get("raw_content", "")
        text = raw if raw else content
        parts.append(f"[{i}] {title}\nURL: {url}\n{text}\n")
    return "\n---\n".join(parts)
