import os
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class SearchAPI(str, Enum):
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    MCP = "mcp"


class Configuration(BaseModel):
    # LLM
    llm_provider: str = "custom"
    llm_model_id: str = "gpt-4.1-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""

    # Search
    search_api: str = SearchAPI.DUCKDUCKGO
    tavily_api_key: str = ""
    max_search_results: int = 5
    max_retry_count: int = 1

    # MCP
    mcp_server_command: str = ""
    mcp_server_args: list[str] = []
    mcp_tool_name: str = "tavily_search"
    mcp_server_env: dict[str, str] = {}

    # Server
    host: str = "0.0.0.0"
    port: int = 8000


_config: Optional[Configuration] = None


def get_config() -> Configuration:
    global _config
    if _config is None:
        mcp_args_raw = os.getenv("MCP_SERVER_ARGS", "")
        mcp_args = [a.strip() for a in mcp_args_raw.split(",") if a.strip()] if mcp_args_raw else []

        mcp_env = {}
        tavily_key = os.getenv("TAVILY_API_KEY", "")
        if tavily_key:
            mcp_env["TAVILY_API_KEY"] = tavily_key

        _config = Configuration(
            llm_provider=os.getenv("LLM_PROVIDER", "custom"),
            llm_model_id=os.getenv("LLM_MODEL_ID", "gpt-4.1-mini"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            search_api=os.getenv("SEARCH_API", "duckduckgo"),
            tavily_api_key=tavily_key,
            max_search_results=int(os.getenv("MAX_SEARCH_RESULTS", "5")),
            max_retry_count=int(os.getenv("MAX_RETRY_COUNT", "1")),
            mcp_server_command=os.getenv("MCP_SERVER_COMMAND", ""),
            mcp_server_args=mcp_args,
            mcp_tool_name=os.getenv("MCP_TOOL_NAME", "tavily_search"),
            mcp_server_env=mcp_env,
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
        )
    return _config


def reset_config():
    global _config
    _config = None
