"""Unit tests for template_generator.py — pure helper functions only, no LLM."""

import pytest

from backend.outreach.template_generator import (
    _apply_write_tool,
    _build_context,
    _compute_field_coverage,
    _coverage_summary,
    _ensure_html,
    _extract_variables,
    _format_field_coverage,
    _sanitize,
    _stringify,
    _tier_context,
)


# ─────────────────────────────────────────────────────────────────────────────
# _stringify
# ─────────────────────────────────────────────────────────────────────────────

def test_stringify_none():
    assert _stringify(None) == ''

def test_stringify_list():
    assert _stringify(['a', 'b', 'c']) == 'a, b, c'

def test_stringify_list_filters_falsy():
    assert _stringify(['x', None, '', 'y']) == 'x, y'

def test_stringify_string():
    assert _stringify('  hello  ') == 'hello'

def test_stringify_int():
    assert _stringify(42) == '42'


# ─────────────────────────────────────────────────────────────────────────────
# _tier_context
# ─────────────────────────────────────────────────────────────────────────────

_SCAN = {
    'total': 100,
    'signals': {
        'giving':   {'count': 40, 'pct': 40},
        'capacity': {'count': 20, 'pct': 20},
    },
    'contact_fields': {
        'name': {'count': 95, 'pct': 95},
    },
}

def test_tier_context_includes_goal():
    result = _tier_context("Build a new hospital wing", "tier_1", _SCAN)
    assert "Build a new hospital wing" in result

def test_tier_context_tier1_label():
    result = _tier_context("Goal", "tier_1", _SCAN)
    assert "Warmest" in result

def test_tier_context_tier2_tone():
    result = _tier_context("Goal", "tier_2", _SCAN)
    assert "professional" in result

def test_tier_context_dominant_signals_threshold_30():
    # giving=40% → listed in "Dominant signals"; capacity=20% → not listed there
    result = _tier_context("Goal", "tier_2", _SCAN)
    # The dominant signals line only includes signals ≥ 30%
    assert "Dominant signals:" in result
    dominant_part = result.split("Dominant signals:")[-1]
    assert "giving" in dominant_part
    assert "capacity" not in dominant_part

def test_tier_context_no_dominant_signals():
    scan = {'total': 50, 'signals': {'giving': {'count': 5, 'pct': 10}}, 'contact_fields': {}}
    result = _tier_context("Goal", "tier_2", scan)
    assert "Dominant" not in result


# ─────────────────────────────────────────────────────────────────────────────
# _coverage_summary
# ─────────────────────────────────────────────────────────────────────────────

def test_coverage_summary_total():
    total, max_pct, _ = _coverage_summary(_SCAN)
    assert total == 100

def test_coverage_summary_max_pct():
    _, max_pct, _ = _coverage_summary(_SCAN)
    assert max_pct == 95  # name=95%

def test_coverage_summary_strong_signals_above_20():
    _, _, cov = _coverage_summary(_SCAN)
    assert 'giving' in cov
    assert 'name' in cov

def test_coverage_summary_empty():
    total, max_pct, cov = _coverage_summary({})
    assert total == 0
    assert max_pct == 0
    assert cov == 'no strong signals'


# ─────────────────────────────────────────────────────────────────────────────
# _compute_field_coverage
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLES = [
    {'contact_snapshot': {'company': 'Acme', 'city': 'Boston'}},
    {'contact_snapshot': {'company': 'Beta', 'city': ''}},
    {'contact_snapshot': {'company': '',     'city': None}},
    {'contact_snapshot': {'company': 'Gamma'}},
]

def test_compute_field_coverage_exact_key():
    result = _compute_field_coverage(_SAMPLES, ['company'])
    assert result['company'] == 75  # 3 of 4 have a value

def test_compute_field_coverage_empty_field():
    result = _compute_field_coverage(_SAMPLES, ['city'])
    assert result['city'] == 25  # only 1 of 4 has Boston

def test_compute_field_coverage_underscore_variant():
    # field 'first_name' matches snapshot key 'first name' (space variant)
    samples = [
        {'contact_snapshot': {'first name': 'Alice'}},
        {'contact_snapshot': {}},
    ]
    result = _compute_field_coverage(samples, ['first_name'])
    assert result['first_name'] == 50

def test_compute_field_coverage_no_samples():
    assert _compute_field_coverage([], ['company']) == {}

def test_compute_field_coverage_no_fields():
    assert _compute_field_coverage(_SAMPLES, []) == {}


# ─────────────────────────────────────────────────────────────────────────────
# _format_field_coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_format_field_coverage_safe_verdict():
    result = _format_field_coverage({'company': 80}, ['company'])
    assert 'safe to use' in result

def test_format_field_coverage_fallback_verdict():
    result = _format_field_coverage({'company': 55}, ['company'])
    assert 'use with fallback' in result

def test_format_field_coverage_risky_verdict():
    result = _format_field_coverage({'company': 15}, ['company'])
    assert 'risky' in result

def test_format_field_coverage_not_populated_verdict():
    result = _format_field_coverage({'company': 0}, ['company'])
    assert 'not populated' in result

def test_format_field_coverage_recommendation_section():
    result = _format_field_coverage({'company': 80, 'city': 55}, ['company', 'city'])
    assert 'RECOMMENDATION' in result
    assert 'Prioritise' in result
    assert 'Use with fallback' in result

def test_format_field_coverage_no_fields():
    result = _format_field_coverage({}, [])
    assert 'No CRM fields' in result


# ─────────────────────────────────────────────────────────────────────────────
# _ensure_html
# ─────────────────────────────────────────────────────────────────────────────

def test_ensure_html_already_tagged():
    html = '<p>Hello world.</p>'
    assert _ensure_html(html) == html

def test_ensure_html_plain_double_newline():
    text = 'First paragraph.\n\nSecond paragraph.'
    result = _ensure_html(text)
    assert result == '<p>First paragraph.</p><p>Second paragraph.</p>'

def test_ensure_html_single_newline():
    text = 'Line one.\nLine two.'
    result = _ensure_html(text)
    assert result == '<p>Line one.</p><p>Line two.</p>'

def test_ensure_html_empty():
    assert _ensure_html('') == ''

def test_ensure_html_single_paragraph():
    result = _ensure_html('Just one para.')
    assert result == '<p>Just one para.</p>'


# ─────────────────────────────────────────────────────────────────────────────
# _sanitize
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_converts_double_braces_to_brackets():
    subj, body = _sanitize('{{first_name}} joins us', 'Dear {{company}}')
    assert subj == '[first_name] joins us'
    assert body == 'Dear [company]'

def test_sanitize_no_braces_unchanged():
    subj, body = _sanitize('Hello', 'World')
    assert subj == 'Hello'
    assert body == 'World'

def test_sanitize_preserves_bracket_slots():
    # Existing [bracket] slots should not be affected
    subj, body = _sanitize('[first_name]', '[company]')
    assert '[first_name]' in subj
    assert '[company]' in body


# ─────────────────────────────────────────────────────────────────────────────
# _extract_variables
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_variables_basic():
    result = _extract_variables('[first_name] and [company]')
    assert result == ['first_name', 'company']

def test_extract_variables_deduplicates():
    result = _extract_variables('[name] ... [name] ... [name]')
    assert result == ['name']

def test_extract_variables_preserves_first_occurrence_order():
    result = _extract_variables('[c] [a] [b] [a]')
    assert result == ['c', 'a', 'b']

def test_extract_variables_fallback_slot():
    result = _extract_variables('[city | fallback: "your area"]')
    assert 'city' in result

def test_extract_variables_empty():
    assert _extract_variables('No slots here') == []


# ─────────────────────────────────────────────────────────────────────────────
# _apply_write_tool
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_write_tool_rewrite_both():
    subj, body = _apply_write_tool(
        'rewrite_both',
        {'new_subject': 'New subject', 'new_body': 'New body text.'},
        'Old subject', 'Old body',
    )
    assert subj == 'New subject'
    assert '<p>New body text.</p>' == body

def test_apply_write_tool_rewrite_subject_only():
    subj, body = _apply_write_tool(
        'rewrite_subject',
        {'new_subject': 'Updated subject'},
        'Old subject', '<p>Keep this body.</p>',
    )
    assert subj == 'Updated subject'
    assert body == '<p>Keep this body.</p>'

def test_apply_write_tool_rewrite_body_only():
    subj, body = _apply_write_tool(
        'rewrite_body',
        {'new_body': 'Fresh body text.'},
        'Keep this subject', 'Old body',
    )
    assert subj == 'Keep this subject'
    assert '<p>Fresh body text.</p>' == body

def test_apply_write_tool_missing_arg_falls_back_to_existing():
    # If new_subject is absent, existing subject should be preserved
    subj, body = _apply_write_tool('rewrite_subject', {}, 'Original', '<p>body</p>')
    assert subj == 'Original'


# ─────────────────────────────────────────────────────────────────────────────
# _build_context (integration of several helpers)
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLES_CTX = [
    {
        'contact_snapshot': {
            'name': 'Alice Wong', 'title': 'Director', 'company': 'NGO',
            'signals': {'topics': 'climate', 'giving': 'UNICEF'},
        },
        'warm_path_data': {'connector': 'Bob Smith'},
    },
    {
        'contact_snapshot': {
            'name': 'John Doe', 'title': 'Manager', 'company': 'Corp',
            'signals': {},
        },
        'warm_path_data': None,
    },
]

def test_build_context_includes_goal():
    ctx = _build_context("Fund clean water", "tier_1", _SCAN, _SAMPLES_CTX)
    assert "Fund clean water" in ctx

def test_build_context_includes_contact_names():
    ctx = _build_context("Goal", "tier_2", _SCAN, _SAMPLES_CTX)
    assert "Alice Wong" in ctx
    assert "John Doe" in ctx

def test_build_context_warm_path_note():
    ctx = _build_context("Goal", "tier_1", _SCAN, _SAMPLES_CTX)
    assert "warm-path" in ctx.lower()

def test_build_context_no_samples():
    ctx = _build_context("Goal", "tier_2", _SCAN, [])
    assert "no samples available" in ctx

def test_build_context_dominant_signal_note():
    ctx = _build_context("Goal", "tier_2", _SCAN, [])
    assert "Dominant" in ctx  # giving=40% triggers dominant note
