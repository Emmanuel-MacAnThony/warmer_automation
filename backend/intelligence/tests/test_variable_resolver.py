"""Unit tests for variable_resolver.py — all variables, all fallback paths."""

import re
import pytest
from backend.outreach.variable_resolver import resolve, resolve_contact, _SLOT_RE


# ── Fixtures ─────────────────────────────────────────────────────────────────

FULL_SNAPSHOT = {
    'name':    'Sarah Chen',
    'company': 'Memorial Health',
    'title':   'VP Research',
    'email':   'sarah@memorialhealth.org',
    'signals': {
        'topics':      "['medical research', 'cancer treatment']",
        'giving':      'healthcare nonprofits',
        'capacity':    'HIGH — estimated $500k+',
        'personality': 'analytical',
        'trajectory':  'ascending',
        'wealth':      'high net worth',
        'engagement':  'active',
    },
}

EMPTY_SNAPSHOT: dict = {
    'name':    'Unknown',
    'company': '',
    'title':   None,
    'signals': {},
}

WARM_PATH = {'connector': 'James Obi', 'score': 0.9}


# ── first_name ────────────────────────────────────────────────────────────────

def test_first_name_resolves():
    text, report = resolve('Hi [first_name],', FULL_SNAPSHOT, {})
    assert text == 'Hi Sarah,'
    assert 'first_name' in report['resolved']

def test_first_name_fallback_default():
    text, report = resolve('Hi [first_name],', EMPTY_SNAPSHOT, {})
    assert text == 'Hi there,'
    assert 'first_name' in report['fallback']

def test_first_name_inline_fallback():
    text, report = resolve('Hi [first_name | fallback: "friend"],', EMPTY_SNAPSHOT, {})
    assert text == 'Hi friend,'
    assert 'first_name' in report['fallback']


# ── company ───────────────────────────────────────────────────────────────────

def test_company_resolves():
    text, report = resolve('at [company]', FULL_SNAPSHOT, {})
    assert text == 'at Memorial Health'
    assert 'company' in report['resolved']

def test_company_omitted_when_empty():
    text, report = resolve('at [company]', EMPTY_SNAPSHOT, {})
    assert text == 'at '
    assert 'company' in report['omitted']

def test_company_inline_fallback():
    text, report = resolve('[company | fallback: "your organisation"]', EMPTY_SNAPSHOT, {})
    assert text == 'your organisation'
    assert 'company' in report['fallback']


# ── title ─────────────────────────────────────────────────────────────────────

def test_title_resolves():
    text, report = resolve('your role as [title]', FULL_SNAPSHOT, {})
    assert 'VP Research' in text
    assert 'title' in report['resolved']

def test_title_omitted_when_missing():
    text, report = resolve('[title]', EMPTY_SNAPSHOT, {})
    assert text == ''
    assert 'title' in report['omitted']


# ── topic_hook ────────────────────────────────────────────────────────────────

def test_topic_hook_resolves_list():
    text, report = resolve('[topic_hook], I wanted to reach out', FULL_SNAPSHOT, {})
    assert 'given your interest in' in text
    assert 'medical research' in text
    assert 'topic_hook' in report['resolved']

def test_topic_hook_resolves_plain_string():
    snap = {**FULL_SNAPSHOT, 'signals': {**FULL_SNAPSHOT['signals'], 'topics': 'education reform'}}
    text, _ = resolve('[topic_hook]', snap, {})
    assert text == 'given your interest in education reform'

def test_topic_hook_omitted_when_no_signal():
    text, report = resolve('[topic_hook | fallback: ""], I wanted', EMPTY_SNAPSHOT, {})
    assert text == ', I wanted'
    assert 'topic_hook' in report['omitted']

def test_topic_hook_default_fallback_omits():
    text, report = resolve('[topic_hook]', EMPTY_SNAPSHOT, {})
    assert text == ''
    assert 'topic_hook' in report['omitted']


# ── giving_reference ──────────────────────────────────────────────────────────

def test_giving_reference_resolves():
    text, report = resolve('[giving_reference]', FULL_SNAPSHOT, {})
    assert 'your past support of' in text
    assert 'healthcare nonprofits' in text
    assert 'giving_reference' in report['resolved']

def test_giving_reference_default_fallback():
    text, report = resolve('[giving_reference]', EMPTY_SNAPSHOT, {})
    assert text == 'your commitment to this work'
    assert 'giving_reference' in report['fallback']

def test_giving_reference_inline_fallback():
    text, report = resolve(
        '[giving_reference | fallback: "your generous history"]', EMPTY_SNAPSHOT, {}
    )
    assert text == 'your generous history'
    assert 'giving_reference' in report['fallback']


# ── capacity_close ────────────────────────────────────────────────────────────

def test_capacity_close_high():
    text, _ = resolve('consider [capacity_close]', FULL_SNAPSHOT, {}, tier='tier_2')
    assert text == 'consider a leadership-level gift'

def test_capacity_close_mid_signal():
    snap = {**FULL_SNAPSHOT, 'signals': {**FULL_SNAPSHOT['signals'], 'capacity': 'MID'}}
    text, _ = resolve('[capacity_close]', snap, {}, tier='tier_2')
    assert text == 'a significant contribution'

def test_capacity_close_tier_3_low():
    snap = {**FULL_SNAPSHOT, 'signals': {**FULL_SNAPSHOT['signals'], 'capacity': ''}}
    text, _ = resolve('[capacity_close]', snap, {}, tier='tier_3')
    assert text == 'a gift at any level'

def test_capacity_close_fallback_override():
    text, report = resolve(
        '[capacity_close | fallback: "a contribution at any level"]', EMPTY_SNAPSHOT, {}, tier='tier_3'
    )
    assert 'capacity_close' in report['resolved']


# ── warm_opener ───────────────────────────────────────────────────────────────

def test_warm_opener_resolves():
    text, report = resolve('[warm_opener] I thought of you.', FULL_SNAPSHOT, {}, warm_path_data=WARM_PATH)
    assert 'Through James Obi,' in text
    assert 'warm_opener' in report['resolved']

def test_warm_opener_omitted_no_connector():
    text, report = resolve('[warm_opener] I thought of you.', FULL_SNAPSHOT, {}, warm_path_data=None)
    assert text == ' I thought of you.'
    assert 'warm_opener' in report['omitted']

def test_warm_opener_inline_fallback():
    text, report = resolve(
        '[warm_opener | fallback: "As someone who cares deeply,"]',
        FULL_SNAPSHOT, {}, warm_path_data=None,
    )
    assert text == 'As someone who cares deeply,'
    assert 'warm_opener' in report['fallback']


# ── Mixed template ────────────────────────────────────────────────────────────

def test_full_template_render():
    template = (
        "Hi [first_name],\n\n"
        "[warm_opener] [topic_hook], I wanted to reach out about our campaign.\n\n"
        "[giving_reference] means so much to us. "
        "We hope you'll consider [capacity_close].\n\n"
        "Best,\nThe Team"
    )
    rendered, report = resolve(
        template, FULL_SNAPSHOT, {}, warm_path_data=WARM_PATH, tier='tier_1'
    )
    assert 'Sarah' in rendered
    assert 'James Obi' in rendered
    assert 'given your interest in' in rendered
    assert 'your past support of' in rendered
    assert 'a leadership-level gift' in rendered
    assert not _SLOT_RE.search(rendered)


def test_completely_empty_contact():
    template = 'Hi [first_name], [topic_hook | fallback: ""] we\'d love your support — [capacity_close].'
    rendered, report = resolve(template, EMPTY_SNAPSHOT, {}, tier='tier_3')
    assert 'Hi there,' in rendered
    assert 'a gift at any level' in rendered
    assert not _SLOT_RE.search(rendered)


# ── resolve_contact convenience wrapper ──────────────────────────────────────

def test_resolve_contact_wrapper():
    contact = {
        'contact_snapshot': FULL_SNAPSHOT,
        'score_breakdown':  {},
        'warm_path_data':   WARM_PATH,
        'tier':             'tier_1',
    }
    result = resolve_contact(
        'Re: [first_name] at [company]',
        'Hi [first_name], [warm_opener] [giving_reference].',
        contact,
    )
    assert 'Sarah' in result['rendered_subject']
    assert 'Memorial Health' in result['rendered_subject']
    assert 'James Obi' in result['rendered_body']
    assert isinstance(result['resolved_vars'], list)
    assert isinstance(result['fallback_vars'], list)
    assert isinstance(result['omitted_vars'], list)
