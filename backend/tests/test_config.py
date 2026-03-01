"""Tests for config.py."""

import os

import pytest

from src.config import get_config, reset_config, Configuration


class TestConfiguration:
    """Tests for Configuration defaults and get_config."""

    def test_default_values(self):
        cfg = Configuration()
        assert cfg.llm_model_id == "gpt-4.1-mini"
        assert cfg.search_api == "duckduckgo"
        assert cfg.max_search_results == 5
        assert cfg.max_retry_count == 1
        assert cfg.port == 8000

    def test_get_config_reads_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_ID", "test-model")
        monkeypatch.setenv("SEARCH_API", "tavily")
        monkeypatch.setenv("MAX_SEARCH_RESULTS", "10")
        monkeypatch.setenv("MAX_RETRY_COUNT", "3")
        monkeypatch.setenv("PORT", "9000")

        cfg = get_config()
        assert cfg.llm_model_id == "test-model"
        assert cfg.search_api == "tavily"
        assert cfg.max_search_results == 10
        assert cfg.max_retry_count == 3
        assert cfg.port == 9000

    def test_get_config_singleton(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_reset_config_clears_singleton(self):
        cfg1 = get_config()
        reset_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2

    def test_mcp_args_parsing(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_ARGS", "-y,tavily-mcp,--verbose")
        cfg = get_config()
        assert cfg.mcp_server_args == ["-y", "tavily-mcp", "--verbose"]

    def test_mcp_args_empty(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_ARGS", "")
        cfg = get_config()
        assert cfg.mcp_server_args == []

    def test_tavily_key_propagated_to_mcp_env(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key-123")
        cfg = get_config()
        assert cfg.tavily_api_key == "test-key-123"
        assert cfg.mcp_server_env.get("TAVILY_API_KEY") == "test-key-123"

    def test_invalid_port_raises(self, monkeypatch):
        monkeypatch.setenv("PORT", "not_a_number")
        with pytest.raises(ValueError):
            get_config()
