"""Tests for search.py helper functions."""

import pytest

from src.search import format_search_context, _normalize_mcp_results, _parse_text_with_urls


class TestFormatSearchContext:
    """Tests for format_search_context."""

    def test_empty_results(self):
        assert format_search_context([]) == "（未找到搜索结果）"

    def test_single_result(self):
        results = [{"title": "Page", "url": "https://example.com", "content": "Hello", "raw_content": ""}]
        ctx = format_search_context(results)
        assert "[1]" in ctx
        assert "Page" in ctx
        assert "https://example.com" in ctx
        assert "Hello" in ctx

    def test_raw_content_preferred_over_content(self):
        results = [{"title": "T", "url": "", "content": "short", "raw_content": "detailed raw"}]
        ctx = format_search_context(results)
        assert "detailed raw" in ctx
        assert "short" not in ctx

    def test_content_used_when_raw_empty(self):
        results = [{"title": "T", "url": "", "content": "fallback", "raw_content": ""}]
        ctx = format_search_context(results)
        assert "fallback" in ctx

    def test_multiple_results_numbered(self):
        results = [
            {"title": f"T{i}", "url": f"url{i}", "content": f"C{i}", "raw_content": ""}
            for i in range(3)
        ]
        ctx = format_search_context(results)
        assert "[1]" in ctx
        assert "[2]" in ctx
        assert "[3]" in ctx


class TestNormalizeMcpResults:
    """Tests for _normalize_mcp_results."""

    def test_standard_fields(self):
        raw = [{"title": "T", "url": "U", "content": "C", "raw_content": "R"}]
        result = _normalize_mcp_results(raw)
        assert result[0] == {"title": "T", "url": "U", "content": "C", "raw_content": "R"}

    def test_alternative_field_names(self):
        raw = [{"title": "T", "href": "U", "snippet": "S", "rawContent": "R"}]
        result = _normalize_mcp_results(raw)
        assert result[0]["url"] == "U"
        assert result[0]["content"] == "S"
        assert result[0]["raw_content"] == "R"

    def test_link_field_for_url(self):
        raw = [{"title": "T", "link": "L"}]
        result = _normalize_mcp_results(raw)
        assert result[0]["url"] == "L"

    def test_body_field_for_content(self):
        raw = [{"title": "T", "body": "B"}]
        result = _normalize_mcp_results(raw)
        assert result[0]["content"] == "B"

    def test_raw_content_truncated_to_8000(self):
        raw = [{"title": "T", "raw_content": "x" * 10000}]
        result = _normalize_mcp_results(raw)
        assert len(result[0]["raw_content"]) == 8000

    def test_non_dict_items_skipped(self):
        raw = [{"title": "T"}, "not a dict", 42]
        result = _normalize_mcp_results(raw)
        assert len(result) == 1

    def test_empty_list(self):
        assert _normalize_mcp_results([]) == []


class TestParseTextWithUrls:
    """Tests for _parse_text_with_urls."""

    def test_structured_block_format(self):
        text = "Title: My Page\nURL: https://example.com\nContent: Some content here"
        urls = ["https://example.com"]
        result = _parse_text_with_urls(text, urls, "query")
        assert len(result) == 1
        assert result[0]["title"] == "My Page"
        assert result[0]["url"] == "https://example.com"
        assert result[0]["content"] == "Some content here"

    def test_multiple_blocks(self):
        text = (
            "Title: Page1\nURL: https://a.com\nContent: C1\n"
            "Title: Page2\nURL: https://b.com\nContent: C2"
        )
        urls = ["https://a.com", "https://b.com"]
        result = _parse_text_with_urls(text, urls, "query")
        assert len(result) == 2

    def test_duplicate_urls_deduped(self):
        text = (
            "Title: P1\nURL: https://a.com\nContent: C1\n"
            "Title: P2\nURL: https://a.com\nContent: C2"
        )
        urls = ["https://a.com"]
        result = _parse_text_with_urls(text, urls, "query")
        assert len(result) == 1

    def test_no_blocks_fallback_to_single_result(self):
        text = "Just some plain text without structured blocks"
        urls = []
        result = _parse_text_with_urls(text, urls, "my query")
        assert len(result) == 1
        assert result[0]["title"] == "my query"
