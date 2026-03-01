"""Tests for graph.py helper functions."""

import pytest

from src.graph import _parse_tasks, _parse_evaluation, _build_source_maps, _remap_citations


class TestParseTasks:
    """Tests for _parse_tasks — extracting planned tasks from LLM JSON."""

    def test_standard_json_object(self):
        content = '{"tasks": [{"title": "T1", "intent": "I1", "query": "Q1"}]}'
        result = _parse_tasks(content)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["title"] == "T1"
        assert result[0]["intent"] == "I1"
        assert result[0]["query"] == "Q1"

    def test_multiple_tasks(self):
        content = '''{
            "tasks": [
                {"title": "A", "intent": "IA", "query": "QA"},
                {"title": "B", "intent": "IB", "query": "QB"},
                {"title": "C", "intent": "IC", "query": "QC"}
            ]
        }'''
        result = _parse_tasks(content)
        assert len(result) == 3
        assert [t["id"] for t in result] == [1, 2, 3]

    def test_json_with_surrounding_text(self):
        content = 'Here is my plan:\n{"tasks": [{"title": "T1", "intent": "I1", "query": "Q1"}]}\nDone.'
        result = _parse_tasks(content)
        assert len(result) == 1
        assert result[0]["title"] == "T1"

    def test_bare_array_fallback(self):
        content = '[{"title": "T1", "intent": "I1", "query": "Q1"}]'
        result = _parse_tasks(content)
        assert len(result) == 1
        assert result[0]["title"] == "T1"

    def test_missing_fields_use_defaults(self):
        content = '{"tasks": [{"title": "Only Title"}]}'
        result = _parse_tasks(content)
        assert result[0]["intent"] == ""
        assert result[0]["query"] == "Only Title"  # falls back to title

    def test_ids_are_reassigned_sequentially(self):
        content = '{"tasks": [{"id": 99, "title": "A"}, {"id": 100, "title": "B"}]}'
        result = _parse_tasks(content)
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_invalid_json_returns_fallback_task(self):
        content = "This is not JSON at all"
        result = _parse_tasks(content)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["title"] == "基础背景研究"

    def test_empty_content_returns_fallback(self):
        result = _parse_tasks("")
        assert len(result) == 1
        assert result[0]["query"] == "基础研究"

    def test_json_in_markdown_code_block(self):
        content = '```json\n{"tasks": [{"title": "T1", "intent": "I1", "query": "Q1"}]}\n```'
        result = _parse_tasks(content)
        assert len(result) == 1
        assert result[0]["title"] == "T1"


class TestParseEvaluation:
    """Tests for _parse_evaluation — extracting evaluation results."""

    def test_no_retry_needed(self):
        content = '{"quality_score": 8, "needs_retry": false, "reason": "Good", "refined_query": ""}'
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is False
        assert query is None

    def test_retry_needed(self):
        content = '{"quality_score": 4, "needs_retry": true, "reason": "Bad", "refined_query": "better query"}'
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is True
        assert query == "better query"

    def test_retry_with_empty_query_returns_none(self):
        content = '{"quality_score": 3, "needs_retry": true, "refined_query": ""}'
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is True
        assert query is None

    def test_invalid_json_returns_no_retry(self):
        content = "I think the quality is fine."
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is False
        assert query is None

    def test_json_with_surrounding_text(self):
        content = 'Evaluation:\n{"quality_score": 5, "needs_retry": true, "refined_query": "new query"}\nEnd.'
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is True
        assert query == "new query"

    def test_missing_needs_retry_defaults_false(self):
        content = '{"quality_score": 7}'
        needs_retry, query = _parse_evaluation(content)
        assert needs_retry is False


class TestBuildSourceMaps:
    """Tests for _build_source_maps — deduplication and index mapping."""

    def test_basic_dedup(self):
        tasks = [
            {"task_id": 1, "sources": [
                {"title": "A", "url": "https://a.com"},
                {"title": "B", "url": "https://b.com"},
            ]},
            {"task_id": 2, "sources": [
                {"title": "A", "url": "https://a.com"},  # duplicate URL
                {"title": "C", "url": "https://c.com"},
            ]},
        ]
        sources, maps = _build_source_maps(tasks)
        assert len(sources) == 3  # a, b, c
        # task 1: local 1->global 1, local 2->global 2
        assert maps[1] == {1: 1, 2: 2}
        # task 2: local 1->global 1 (deduped), local 2->global 3
        assert maps[2] == {1: 1, 2: 3}

    def test_dedup_prefers_url_over_title(self):
        """Same title, different URLs should NOT be deduped."""
        tasks = [{"task_id": 1, "sources": [
            {"title": "Same Title", "url": "https://a.com"},
            {"title": "Same Title", "url": "https://b.com"},
        ]}]
        sources, maps = _build_source_maps(tasks)
        assert len(sources) == 2

    def test_dedup_same_url_different_titles(self):
        """Same URL, different titles should be deduped."""
        tasks = [{"task_id": 1, "sources": [
            {"title": "Title A", "url": "https://same.com"},
            {"title": "Title B", "url": "https://same.com"},
        ]}]
        sources, maps = _build_source_maps(tasks)
        assert len(sources) == 1

    def test_empty_title_and_url_skipped(self):
        tasks = [{"task_id": 1, "sources": [
            {"title": "", "url": ""},
            {"title": "Valid", "url": "https://valid.com"},
        ]}]
        sources, maps = _build_source_maps(tasks)
        assert len(sources) == 1
        assert maps[1] == {2: 1}  # first source skipped, second is local idx 2

    def test_no_sources(self):
        tasks = [{"task_id": 1, "sources": []}]
        sources, maps = _build_source_maps(tasks)
        assert sources == []
        assert maps[1] == {}


class TestRemapCitations:
    """Tests for _remap_citations."""

    def test_basic_remap(self):
        result = _remap_citations("See [1] and [2].", {1: 5, 2: 10})
        assert result == "See [5] and [10]."

    def test_unmapped_ids_preserved(self):
        result = _remap_citations("See [1] and [99].", {1: 5})
        assert result == "See [5] and [99]."

    def test_empty_map_returns_unchanged(self):
        text = "No citations [1] here [2]."
        assert _remap_citations(text, {}) == text
