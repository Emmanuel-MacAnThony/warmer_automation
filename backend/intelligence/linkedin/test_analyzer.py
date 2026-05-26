"""Unit tests for linkedin/analyzer.py — pure functions only, no LLM."""

import json
import pytest

from backend.intelligence.linkedin.analyzer import (
    _extract_year,
    _parse,
    build_analyzed_links,
    extract_career_progression,
    pre_filter_posts,
    BatchOutputValidator,
)


# ─────────────────────────────────────────────────────────────────────────────
# _extract_year
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_year_int():
    assert _extract_year(2019) == 2019

def test_extract_year_dict():
    assert _extract_year({"year": 2021, "month": 6}) == 2021

def test_extract_year_string():
    assert _extract_year("2018-03") == 2018

def test_extract_year_none():
    assert _extract_year(None) is None

def test_extract_year_bad_string():
    assert _extract_year("not-a-year") is None


# ─────────────────────────────────────────────────────────────────────────────
# extract_career_progression
# ─────────────────────────────────────────────────────────────────────────────

_HARVESTAPI_PROFILE = {
    "raw_data": {
        "experience": [
            {"position": "CTO",         "companyName": "Acme",    "startDate": {"year": 2020}, "endDate": None},
            {"position": "VP Eng",      "companyName": "Beta Inc", "startDate": {"year": 2016}, "endDate": {"year": 2020}},
            {"position": "Sr Engineer", "companyName": "Gamma",   "startDate": {"year": 2012}, "endDate": {"year": 2016}},
            {"position": "Engineer",    "companyName": "Delta",   "startDate": {"year": 2009}, "endDate": {"year": 2012}},
        ]
    }
}

_DEV_FUSION_PROFILE = {
    "raw_data": {
        "experiences": [
            {"title": "CEO", "companyName": "StartupX", "jobStartedOn": "2021", "jobEndedOn": None},
            {"title": "COO", "companyName": "OldCo",    "jobStartedOn": "2017", "jobEndedOn": "2021"},
        ]
    }
}


def test_career_progression_harvestapi_returns_last_three():
    result = extract_career_progression(_HARVESTAPI_PROFILE)
    assert "last_three_roles" in result
    lines = result["last_three_roles"].strip().split("\n")
    assert len(lines) == 3
    assert "CTO" in lines[0]
    assert "VP Eng" in lines[1]
    assert "Sr Engineer" in lines[2]

def test_career_progression_harvestapi_career_json_all_roles():
    result = extract_career_progression(_HARVESTAPI_PROFILE)
    roles = json.loads(result["career_json"])
    assert len(roles) == 4

def test_career_progression_dev_fusion_schema():
    result = extract_career_progression(_DEV_FUSION_PROFILE)
    assert "CEO" in result["last_three_roles"]
    roles = json.loads(result["career_json"])
    assert roles[0]["title"] == "CEO"
    assert roles[0]["company"] == "StartupX"

def test_career_progression_empty_experience():
    result = extract_career_progression({"raw_data": {"experience": []}})
    assert result == {}

def test_career_progression_missing_title_skipped():
    data = {"raw_data": {"experience": [
        {"position": "", "companyName": "Co", "startDate": None, "endDate": None},
    ]}}
    assert extract_career_progression(data) == {}

def test_career_progression_present_marker():
    result = extract_career_progression(_HARVESTAPI_PROFILE)
    # First role has no endDate — should show "present"
    assert "present" in result["last_three_roles"]


# ─────────────────────────────────────────────────────────────────────────────
# pre_filter_posts
# ─────────────────────────────────────────────────────────────────────────────

def _make_post(pid, likes=0, comments=0, shares=0, ts=0, is_share=False):
    return {
        "id": pid,
        "engagement": {"likes": likes, "comments": comments, "shares": shares},
        "postedAt": {"timestamp": ts, "date": f"2024-0{ts}-01"},
        "type": "share" if is_share else "post",
        "linkedinUrl": f"https://linkedin.com/p/{pid}",
    }

def test_pre_filter_returns_at_most_13():
    posts = [_make_post(i, likes=i) for i in range(20)]
    result = pre_filter_posts(posts)
    assert len(result) <= 13

def test_pre_filter_original_beats_share():
    # Original post with 0 engagement outscores a share with the same engagement
    # because original adds +10 to _signal_score
    share    = _make_post("share1", is_share=True, ts=1)
    original = _make_post("orig1",  is_share=False, ts=2)
    result = pre_filter_posts([share, original])
    # Both end up in top-13, but original should have higher score
    ids = [p["id"] for p in result]
    assert "orig1" in ids

def test_pre_filter_deduplicates():
    posts = [_make_post(1, likes=100, ts=5)] * 3
    result = pre_filter_posts(posts)
    assert len(result) == 1

def test_pre_filter_empty():
    assert pre_filter_posts([]) == []

def test_pre_filter_comment_weight_higher_than_like():
    # Both are shares (is_original=0) so the +10 original bonus cancels out.
    # 1 comment (×3=3) > 2 likes (×1=2).
    by_likes    = _make_post("likes",    likes=2, comments=0, is_share=True)
    by_comments = _make_post("comments", likes=0, comments=1, is_share=True)
    result = pre_filter_posts([by_likes, by_comments])
    scores = {p["id"]: p["_signal_score"] for p in result}
    assert scores["comments"] > scores["likes"]


# ─────────────────────────────────────────────────────────────────────────────
# build_analyzed_links
# ─────────────────────────────────────────────────────────────────────────────

def test_build_analyzed_links_format():
    posts = [
        {"linkedinUrl": "https://lnkd.in/abc", "engagement": {"likes": 42, "comments": 7},
         "postedAt": {"date": "2024-03-15"}},
    ]
    result = build_analyzed_links(posts)
    assert "https://lnkd.in/abc" in result
    assert "42 likes" in result
    assert "7 comments" in result
    assert "2024-03-15" in result

def test_build_analyzed_links_empty():
    assert build_analyzed_links([]) == ""

def test_build_analyzed_links_missing_url():
    posts = [{"linkedinUrl": None, "shareLinkedinUrl": "https://lnkd.in/xyz",
              "engagement": {"likes": 0, "comments": 0}, "postedAt": {"date": ""}}]
    result = build_analyzed_links(posts)
    assert "https://lnkd.in/xyz" in result


# ─────────────────────────────────────────────────────────────────────────────
# _parse
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_clean_json():
    assert _parse('{"key": "value"}') == {"key": "value"}

def test_parse_markdown_fenced():
    content = '```json\n{"foo": 1}\n```'
    assert _parse(content) == {"foo": 1}

def test_parse_plain_code_fence():
    content = '```\n{"bar": 2}\n```'
    assert _parse(content) == {"bar": 2}

def test_parse_invalid_json_returns_empty():
    assert _parse("not json at all") == {}

def test_parse_array_returns_empty():
    # Top-level array is not a dict — should return {}
    assert _parse("[1, 2, 3]") == {}


# ─────────────────────────────────────────────────────────────────────────────
# BatchOutputValidator
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return BatchOutputValidator()

_MAPPING = {
    "f1": {"airtable_name": "Industry",    "airtable_type": "singleSelect",    "choices": ["Tech", "Finance", "Healthcare"]},
    "f2": {"airtable_name": "Skills",      "airtable_type": "multipleSelects", "choices": ["Python", "SQL", "Go"]},
    "f3": {"airtable_name": "Experience",  "airtable_type": "number",          "choices": []},
    "f4": {"airtable_name": "OpenToWork",  "airtable_type": "checkbox",        "choices": []},
    "f5": {"airtable_name": "Summary",     "airtable_type": "multilineText",   "choices": []},
    "f6": {"airtable_name": "Formula",     "airtable_type": "formula",         "choices": []},
}

def test_validate_singleselect_exact_match(validator):
    validated, errors = validator.validate({"Industry": "Tech"}, _MAPPING)
    assert validated["Industry"] == "Tech"
    assert not errors

def test_validate_singleselect_case_insensitive(validator):
    validated, errors = validator.validate({"Industry": "tech"}, _MAPPING)
    assert validated["Industry"] == "Tech"

def test_validate_singleselect_not_in_choices(validator):
    validated, errors = validator.validate({"Industry": "Legal"}, _MAPPING)
    assert "Industry" not in validated
    assert any("Industry" in e for e in errors)

def test_validate_multipleselects_filters_invalid(validator):
    validated, errors = validator.validate({"Skills": ["Python", "Rust"]}, _MAPPING)
    assert validated["Skills"] == ["Python"]

def test_validate_multipleselects_all_invalid_raises(validator):
    validated, errors = validator.validate({"Skills": ["Rust", "Haskell"]}, _MAPPING)
    assert "Skills" not in validated
    assert any("Skills" in e for e in errors)

def test_validate_number_coerce(validator):
    validated, _ = validator.validate({"Experience": "12.5"}, _MAPPING)
    assert validated["Experience"] == 12.5

def test_validate_number_bad_value(validator):
    validated, errors = validator.validate({"Experience": "not-a-number"}, _MAPPING)
    assert "Experience" not in validated
    assert errors

def test_validate_checkbox_bool(validator):
    validated, _ = validator.validate({"OpenToWork": True}, _MAPPING)
    assert validated["OpenToWork"] is True

def test_validate_checkbox_string_true(validator):
    validated, _ = validator.validate({"OpenToWork": "yes"}, _MAPPING)
    assert validated["OpenToWork"] is True

def test_validate_checkbox_string_false(validator):
    validated, _ = validator.validate({"OpenToWork": "false"}, _MAPPING)
    assert validated["OpenToWork"] is False

def test_validate_readonly_field_skipped(validator):
    validated, errors = validator.validate({"Formula": "=A1+B1"}, _MAPPING)
    assert "Formula" not in validated
    assert any("Formula" in e for e in errors)

def test_validate_unknown_field_flagged(validator):
    validated, errors = validator.validate({"Unknown": "value"}, _MAPPING)
    assert "Unknown" not in validated
    assert any("Unknown" in e for e in errors)

def test_validate_none_and_empty_string_skipped(validator):
    validated, errors = validator.validate({"Summary": None, "Experience": ""}, _MAPPING)
    assert not validated
    assert not errors

def test_validate_multilinetext_passthrough(validator):
    validated, _ = validator.validate({"Summary": "Two sentences here."}, _MAPPING)
    assert validated["Summary"] == "Two sentences here."
