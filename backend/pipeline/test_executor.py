"""
Tests for BatchExecutor domain logic and _process_record control flow.

Orchestration:
  ExecutorManager (manager.py) owns asyncio.Tasks — one per job.
  BatchExecutor.run_job sequences batches and polls for pause between each.
  BatchExecutor._process_record is the per-contact pipeline:
    fetch → get/find LinkedIn URL → scrape → analyze → validate → write CSV

These tests verify the observable outcomes of that pipeline:
  what status is returned, what gets written to the CSV, which external
  calls are made or skipped, under each branch condition.
"""

import asyncio
import csv
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.pipeline.executor import (
    BatchExecutor,
    _build_contact,
    _extract_twitter_handle,
    _find_linkedin_field,
    _read_processed_stats,
    _sanitize_for_airtable,
    _write_csv_row,
)


# ─────────────────────────────────────────────────────────────────────────────
# Domain rules: _sanitize_for_airtable
# These rules decide what data actually lands in Airtable.
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_multipleselects_wraps_string_in_list():
    result = _sanitize_for_airtable({"Tags": "Tech"}, {"Tags": "multipleSelects"})
    assert result["Tags"] == ["Tech"]

def test_sanitize_multipleselects_keeps_list():
    result = _sanitize_for_airtable({"Tags": ["Tech", "Finance"]}, {"Tags": "multipleSelects"})
    assert result["Tags"] == ["Tech", "Finance"]

def test_sanitize_singleselect_stringifies():
    result = _sanitize_for_airtable({"Industry": "Technology"}, {"Industry": "singleSelect"})
    assert result["Industry"] == "Technology"

def test_sanitize_singleselect_list_of_one_unwraps():
    result = _sanitize_for_airtable({"Industry": ["Technology"]}, {"Industry": "singleSelect"})
    assert result["Industry"] == "Technology"

def test_sanitize_singleselect_list_of_dict_serializes_to_json():
    result = _sanitize_for_airtable(
        {"Notes": [{"key": "val"}]}, {"Notes": "multilineText"}
    )
    assert result["Notes"] == '[{"key": "val"}]'

def test_sanitize_number_coerces_string():
    result = _sanitize_for_airtable({"Score": "42.5"}, {"Score": "number"})
    assert result["Score"] == 42.5

def test_sanitize_number_bad_value_dropped():
    result = _sanitize_for_airtable({"Score": "n/a"}, {"Score": "number"})
    assert "Score" not in result

def test_sanitize_checkbox_bool_passthrough():
    result = _sanitize_for_airtable({"Active": True}, {"Active": "checkbox"})
    assert result["Active"] is True

def test_sanitize_checkbox_string_true():
    result = _sanitize_for_airtable({"Active": "yes"}, {"Active": "checkbox"})
    assert result["Active"] is True

def test_sanitize_checkbox_string_false():
    result = _sanitize_for_airtable({"Active": "false"}, {"Active": "checkbox"})
    assert result["Active"] is False

def test_sanitize_none_values_dropped():
    result = _sanitize_for_airtable({"Name": None, "Score": 0.5}, {"Name": "singleLineText", "Score": "number"})
    assert "Name" not in result
    assert result["Score"] == 0.5

def test_sanitize_unknown_type_falls_through_as_string():
    result = _sanitize_for_airtable({"X": "hello"}, {"X": "richText"})
    assert result["X"] == "hello"


# ─────────────────────────────────────────────────────────────────────────────
# Crash recovery: _read_processed_stats
# On restart, the executor reads the existing CSV to skip completed records
# and retry failed ones without double-counting.
# ─────────────────────────────────────────────────────────────────────────────

_CSV_HEADERS = ["record_id", "linkedin_url", "status", "error"]

def _write_test_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_read_processed_stats_no_csv(tmp_path):
    skip_ids, failed_ids, hits, misses, failed = _read_processed_stats(tmp_path / "missing.csv")
    assert skip_ids == set() and failed_ids == set()
    assert hits == 0 and misses == 0 and failed == 0

def test_read_processed_stats_all_success(tmp_path):
    p = tmp_path / "batch.csv"
    _write_test_csv(p, [
        {"record_id": "r1", "status": "success"},
        {"record_id": "r2", "status": "success"},
    ])
    skip_ids, failed_ids, hits, misses, failed = _read_processed_stats(p)
    assert skip_ids == {"r1", "r2"}
    assert hits == 2 and misses == 0 and failed == 0

def test_read_processed_stats_mixed(tmp_path):
    p = tmp_path / "batch.csv"
    _write_test_csv(p, [
        {"record_id": "r1", "status": "success"},
        {"record_id": "r2", "status": "skipped"},
        {"record_id": "r3", "status": "failed"},
    ])
    skip_ids, failed_ids, hits, misses, failed = _read_processed_stats(p)
    assert "r1" in skip_ids and "r2" in skip_ids
    assert "r3" not in skip_ids and "r3" in failed_ids
    assert hits == 1 and misses == 1 and failed == 1

def test_read_processed_stats_last_write_wins(tmp_path):
    # r1 fails then succeeds on retry — should count as success, not in failed
    p = tmp_path / "batch.csv"
    _write_test_csv(p, [
        {"record_id": "r1", "status": "failed"},
        {"record_id": "r1", "status": "success"},
    ])
    skip_ids, failed_ids, hits, misses, failed = _read_processed_stats(p)
    assert "r1" in skip_ids
    assert "r1" not in failed_ids
    assert hits == 1 and failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Field extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_build_contact_standard_fields():
    fields = {"Name": "Alice Wong", "Company": "NGO Health", "Job Title": "Director"}
    c = _build_contact(fields)
    assert c["name"] == "Alice Wong"
    assert c["company"] == "NGO Health"
    assert c["job_title"] == "Director"

def test_build_contact_alternative_field_names():
    fields = {"Full Name": "Bob Kim", "Company Name": "TechCo", "Title": "VP Eng"}
    c = _build_contact(fields)
    assert c["name"] == "Bob Kim"
    assert c["company"] == "TechCo"
    assert c["job_title"] == "VP Eng"

def test_build_contact_empty_record():
    c = _build_contact({})
    assert c["name"] == ""
    assert c["company"] == ""

def test_find_linkedin_field_present():
    mapping = {
        "f1": {"airtable_name": "Industry", "canonical_key": "company_industry"},
        "f2": {"airtable_name": "LinkedIn Profile", "canonical_key": "linkedin_url"},
    }
    assert _find_linkedin_field(mapping) == "LinkedIn Profile"

def test_find_linkedin_field_absent():
    mapping = {"f1": {"airtable_name": "Industry", "canonical_key": "company_industry"}}
    assert _find_linkedin_field(mapping) is None

def test_extract_twitter_handle_from_apify():
    data = {"twitter": "https://twitter.com/johndoe"}
    assert _extract_twitter_handle(data, {}, {}) == "johndoe"

def test_extract_twitter_handle_strips_at():
    data = {"twitter": "@janedoe"}
    assert _extract_twitter_handle(data, {}, {}) == "janedoe"

def test_extract_twitter_handle_from_field_mapping():
    data = {}
    fields = {"Twitter Handle": "alice_ngo"}
    mapping = {"f1": {"canonical_key": "twitter_handle", "airtable_name": "Twitter Handle"}}
    assert _extract_twitter_handle(data, fields, mapping) == "alice_ngo"

def test_extract_twitter_handle_none_when_absent():
    assert _extract_twitter_handle({}, {}, {}) is None


# ─────────────────────────────────────────────────────────────────────────────
# _process_record flow tests
# Each test asserts the return value AND the CSV row written, which is the
# observable outcome of the enrichment pipeline for one contact.
# ─────────────────────────────────────────────────────────────────────────────

_FIELD_MAPPING = {
    "f1": {"airtable_name": "LinkedIn Profile", "canonical_key": "linkedin_url",
           "airtable_type": "url", "choices": []},
    "f2": {"airtable_name": "Industry", "canonical_key": "company_industry",
           "airtable_type": "singleSelect", "choices": ["Tech", "Healthcare"]},
}

_APIFY_PROFILE = {
    "full_name": "Alice Wong",
    "headline": "Director at NGO",
    "raw_data": {"experience": [
        {"position": "Director", "companyName": "NGO Health",
         "startDate": {"year": 2018}, "endDate": None}
    ]},
    "posts": [],
}


def _make_airtable_mock(fields: dict) -> MagicMock:
    mock = MagicMock()
    mock.get_record.return_value = {"id": "recXXX", "fields": fields}
    return mock


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.anyio
async def test_process_record_success_with_linkedin_url(tmp_path):
    """Record already has a LinkedIn URL → scrape, analyze, write success row."""
    csv_path = tmp_path / "batch.csv"
    headers = ["record_id", "linkedin_url", "status", "error",
               "LinkedIn Profile", "Industry", "last_three_roles", "career_json",
               "trajectory_tag", "trajectory_signal",
               "post_wealth_signal", "post_giving_signal", "post_topic_themes",
               "post_engagement_tier", "post_personality_type",
               "post_last_active", "post_analyzed_links",
               "press_mentions", "press_count", "press_last_date",
               "tweet_wealth_signal", "tweet_giving_signal", "tweet_topic_themes",
               "tweet_engagement_tier", "tweet_personality_type",
               "tweet_last_active", "tweet_analyzed_links"]

    airtable_fields = {"LinkedIn Profile": "https://linkedin.com/in/alice"}

    with (
        patch("backend.pipeline.executor._get_airtable", return_value=_make_airtable_mock(airtable_fields)),
        patch("backend.pipeline.executor._pool_scrape", new_callable=AsyncMock, return_value=dict(_APIFY_PROFILE)),
        patch("backend.pipeline.executor._get_analyzer") as mock_analyzer_fn,
        patch("backend.pipeline.executor._get_validator") as mock_validator_fn,
        patch("backend.pipeline.executor.extract_post_signals", new_callable=AsyncMock, return_value={}),
        patch("backend.pipeline.executor.extract_tweet_signals", new_callable=AsyncMock, return_value={}),
        patch("backend.pipeline.executor.extract_career_progression", return_value={}),
        patch("backend.pipeline.executor.db") as mock_db,
        patch("backend.pipeline.executor.Config") as mock_cfg,
    ):
        mock_cfg.SKIP_ALREADY_ENRICHED = False
        mock_cfg.ENRICH_NEWS = False
        mock_cfg.ENRICH_TWITTER = False

        mock_analyzer = MagicMock()
        mock_analyzer.analyze = AsyncMock(return_value={"Industry": "Tech"})
        mock_analyzer_fn.return_value = mock_analyzer

        from backend.intelligence.linkedin.analyzer import BatchOutputValidator
        mock_validator_fn.return_value = BatchOutputValidator()

        executor = BatchExecutor()
        result = await executor._process_record(
            "recXXX", "appBASE", "tblTABLE", _FIELD_MAPPING, csv_path, headers
        )

    assert result == "success"
    rows = _read_csv_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["record_id"] == "recXXX"
    assert "linkedin.com/in/alice" in rows[0]["linkedin_url"]


@pytest.mark.anyio
async def test_process_record_skip_already_enriched(tmp_path):
    """Contact already has trajectory_tag and SKIP_ALREADY_ENRICHED=True → skipped without scraping."""
    csv_path = tmp_path / "batch.csv"
    headers = ["record_id", "linkedin_url", "status", "error"]

    airtable_fields = {
        "LinkedIn Profile": "https://linkedin.com/in/alice",
        "trajectory_tag": "EXITED_FOUNDER",
    }

    with (
        patch("backend.pipeline.executor._get_airtable", return_value=_make_airtable_mock(airtable_fields)),
        patch("backend.pipeline.executor._pool_scrape", new_callable=AsyncMock) as mock_scrape,
        patch("backend.pipeline.executor.Config") as mock_cfg,
    ):
        mock_cfg.SKIP_ALREADY_ENRICHED = True

        executor = BatchExecutor()
        result = await executor._process_record(
            "recXXX", "appBASE", "tblTABLE", _FIELD_MAPPING, csv_path, headers
        )

    assert result == "skipped"
    mock_scrape.assert_not_called()
    rows = _read_csv_rows(csv_path)
    assert rows[0]["status"] == "skipped"


@pytest.mark.anyio
async def test_process_record_apify_403_returns_special_status(tmp_path):
    """Apify credits exhausted → returns 'apify_403', writes failed row."""
    from backend.pipeline.executor import ApifyCreditsError

    csv_path = tmp_path / "batch.csv"
    headers = ["record_id", "linkedin_url", "status", "error"]
    airtable_fields = {"LinkedIn Profile": "https://linkedin.com/in/alice"}

    with (
        patch("backend.pipeline.executor._get_airtable", return_value=_make_airtable_mock(airtable_fields)),
        patch("backend.pipeline.executor._pool_scrape", new_callable=AsyncMock,
              side_effect=ApifyCreditsError("Credits exhausted")),
        patch("backend.pipeline.executor.Config") as mock_cfg,
    ):
        mock_cfg.SKIP_ALREADY_ENRICHED = False
        mock_cfg.ENRICH_NEWS = False

        executor = BatchExecutor()
        result = await executor._process_record(
            "recXXX", "appBASE", "tblTABLE", _FIELD_MAPPING, csv_path, headers
        )

    assert result == "apify_403"
    rows = _read_csv_rows(csv_path)
    assert rows[0]["status"] == "failed"
    assert "apify_403" in rows[0]["error"]


@pytest.mark.anyio
async def test_process_record_no_linkedin_no_serp_results_skipped(tmp_path):
    """No LinkedIn URL in record, SERP search returns empty → skipped."""
    csv_path = tmp_path / "batch.csv"
    headers = ["record_id", "linkedin_url", "status", "error"]
    airtable_fields = {"Name": "Bob Kim", "Company": "NGO"}

    with (
        patch("backend.pipeline.executor._get_airtable", return_value=_make_airtable_mock(airtable_fields)),
        patch("backend.pipeline.executor._serp_semaphore"),
        patch("backend.pipeline.executor._search_sync", return_value=[]),
        patch("backend.pipeline.executor.Config") as mock_cfg,
    ):
        mock_cfg.SKIP_ALREADY_ENRICHED = False

        executor = BatchExecutor()
        result = await executor._process_record(
            "recXXX", "appBASE", "tblTABLE", _FIELD_MAPPING, csv_path, headers
        )

    assert result == "skipped"
    rows = _read_csv_rows(csv_path)
    assert rows[0]["status"] == "skipped"
    assert "no_linkedin_found" in rows[0]["error"]


@pytest.mark.anyio
async def test_process_record_analysis_failure_returns_failed(tmp_path):
    """LLM analysis raises → returns 'failed', writes error row."""
    csv_path = tmp_path / "batch.csv"
    headers = ["record_id", "linkedin_url", "status", "error"]
    airtable_fields = {"LinkedIn Profile": "https://linkedin.com/in/alice"}

    with (
        patch("backend.pipeline.executor._get_airtable", return_value=_make_airtable_mock(airtable_fields)),
        patch("backend.pipeline.executor._pool_scrape", new_callable=AsyncMock,
              return_value=dict(_APIFY_PROFILE)),
        patch("backend.pipeline.executor._get_analyzer") as mock_analyzer_fn,
        patch("backend.pipeline.executor.extract_post_signals", new_callable=AsyncMock,
              side_effect=RuntimeError("OpenAI timeout")),
        patch("backend.pipeline.executor.extract_tweet_signals", new_callable=AsyncMock, return_value={}),
        patch("backend.pipeline.executor.Config") as mock_cfg,
    ):
        mock_cfg.SKIP_ALREADY_ENRICHED = False
        mock_cfg.ENRICH_NEWS = False
        mock_cfg.ENRICH_TWITTER = False

        mock_analyzer = MagicMock()
        mock_analyzer.analyze = AsyncMock(return_value={})
        mock_analyzer_fn.return_value = mock_analyzer

        executor = BatchExecutor()
        result = await executor._process_record(
            "recXXX", "appBASE", "tblTABLE", _FIELD_MAPPING, csv_path, headers
        )

    assert result == "failed"
    rows = _read_csv_rows(csv_path)
    assert rows[0]["status"] == "failed"
    assert "analysis_error" in rows[0]["error"]
