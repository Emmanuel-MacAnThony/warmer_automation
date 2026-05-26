"""
Variable resolver for batch email templates.

Resolves [variable | fallback: "phrase"] slots from contact_snapshot +
score_breakdown. Pure Python — zero LLM calls.

Slot format
-----------
  [first_name]                              — use default fallback
  [topic_hook | fallback: ""]               — omit clause if no signal
  [giving_reference | fallback: "your commitment to this work"]

Resolution order
----------------
  1. Compute primary value from contact data
  2. If no primary — use inline fallback if specified, else _DEFAULT_FALLBACKS
  3. If resolved fallback is "" — omit (return empty string, caller strips)
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

# Matches [var name] or [var name | fallback: "phrase"] — allows spaces in names
_SLOT_RE = re.compile(r'\[([A-Za-z][A-Za-z0-9 _]*)(?:\s*\|\s*fallback:\s*"([^"]*)")?\]')


# ── Default fallbacks (used when no inline fallback is written) ──────────────

_DEFAULT_FALLBACKS: dict[str, str] = {
    'first_name':        'there',
    'company':           '',   # omit
    'title':             '',   # omit
    'topic_hook':        '',   # omit whole clause
    'giving_reference':  'your commitment to this work',
    'capacity_close':    'a contribution at any level',
    'warm_opener':       '',   # omit
}


# ── Signal text normaliser ───────────────────────────────────────────────────

def _normalise(raw: str) -> str:
    """Convert Python list repr or raw tag to clean lowercase text."""
    s = raw.strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            items = json.loads(s.replace("'", '"'))
            if isinstance(items, list):
                return ', '.join(str(i).strip().lower() for i in items)
        except Exception:
            pass
    return s.lower()


# ── Per-variable computation ─────────────────────────────────────────────────

def _compute(
    name: str,
    snapshot: dict,
    signals: dict,
    score_breakdown: dict,
    warm_path_data: Optional[dict],
    tier: str,
) -> Optional[str]:
    """Return the primary resolved value, or None if unavailable."""

    if name == 'first_name':
        full = (snapshot.get('name') or '').strip()
        first = full.split()[0] if full and full.lower() != 'unknown' else None
        return first or None

    if name == 'company':
        return (snapshot.get('company') or '').strip() or None

    if name == 'title':
        return (snapshot.get('title') or '').strip() or None

    if name == 'topic_hook':
        # Resolves to the bare topics (a noun). The email writer supplies the
        # lead-in (e.g. "given your interest in [topic_hook]"), so the slot must
        # NOT embed a lead-in itself — that caused doubled "given your interest in
        # given your interest in …" phrasing.
        raw_val = signals.get('topics')
        raw = (', '.join(str(x) for x in raw_val if x) if isinstance(raw_val, list) else str(raw_val or '')).strip()
        if not raw:
            return None
        return _normalise(raw)

    if name == 'giving_reference':
        # Bare noun phrase (e.g. "education and climate causes"); the writer adds
        # the lead-in (e.g. "your past support of [giving_reference]").
        raw_val = signals.get('giving')
        raw = (', '.join(str(x) for x in raw_val if x) if isinstance(raw_val, list) else str(raw_val or '')).strip()
        if not raw:
            return None
        return _normalise(raw)

    if name == 'capacity_close':
        cap_val = signals.get('capacity')
        cap = (', '.join(str(x) for x in cap_val if x) if isinstance(cap_val, list) else str(cap_val or '')).lower()
        if 'high' in cap or 'major' in cap or 'ultra' in cap or tier == 'tier_1':
            return 'a leadership-level gift'
        if 'mid' in cap or 'medium' in cap or tier == 'tier_2':
            return 'a significant contribution'
        return 'a gift at any level'

    if name == 'warm_opener':
        connector = (warm_path_data or {}).get('connector', '').strip()
        if connector:
            return f"Through {connector},"
        return None

    # Generic lookup — normalise and check snapshot fields + signals + raw Airtable fields
    def _norm(s: str) -> str:
        return re.sub(r'[\s_]+', '_', s.strip().lower())

    def _coerce(val) -> str:
        """Flatten any value to a human-readable string — lists become comma-separated."""
        if val is None:
            return ''
        if isinstance(val, list):
            return ', '.join(str(x).strip() for x in val if x)
        return str(val).strip()

    norm = _norm(name)

    # 1. raw_fields — exact key match first (e.g. [Realtime Role] → "Realtime Role")
    raw = snapshot.get('raw_fields') or {}
    if name in raw:
        return _coerce(raw[name]) or None
    # normalised match against raw field names
    for key, val in raw.items():
        if _norm(key) == norm and val:
            return _coerce(val) or None

    # 2. Canonical snapshot fields — exact then substring match
    for key in ('name', 'title', 'company', 'email'):
        k = _norm(key)
        if k == norm or k in norm or norm in k:
            val = _coerce(snapshot.get(key))
            if val:
                return val

    # 3. Signals dict
    for key, val in signals.items():
        if _norm(key) == norm and val:
            return _coerce(val) or None

    return None


# ── Public API ───────────────────────────────────────────────────────────────

def resolve(
    template: str,
    contact_snapshot: dict,
    score_breakdown: dict,
    warm_path_data: Optional[dict] = None,
    tier: str = 'tier_2',
) -> tuple[str, dict[str, list[str]]]:
    """
    Render all {{variable}} slots in *template*.

    Returns
    -------
    rendered : str
        Template with all slots replaced.
    report : dict
        {
          'resolved': [...],   # variables that had primary values
          'fallback': [...],   # variables that used a fallback phrase
          'omitted':  [...],   # variables whose fallback was "" (clause dropped)
        }
    """
    signals = (contact_snapshot.get('signals') or {})

    resolved_vars: list[str] = []
    fallback_vars: list[str] = []
    omitted_vars:  list[str] = []

    def _replace(m: re.Match) -> str:
        name            = m.group(1).strip()
        inline_fallback = m.group(2)  # None when not written in template

        primary = _compute(name, contact_snapshot, signals, score_breakdown, warm_path_data, tier)

        if primary is not None:
            resolved_vars.append(name)
            return primary

        # Fall back
        fb = inline_fallback if inline_fallback is not None else _DEFAULT_FALLBACKS.get(name, '')
        if fb == '':
            omitted_vars.append(name)
            return ''
        fallback_vars.append(name)
        return fb

    rendered = _SLOT_RE.sub(_replace, template)
    # strip double-spaces left by omitted slots at sentence start
    rendered = re.sub(r'  +', ' ', rendered)

    return rendered, {
        'resolved': resolved_vars,
        'fallback': fallback_vars,
        'omitted':  omitted_vars,
    }


def resolve_contact(
    template_subject: str,
    template_body: str,
    contact: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience wrapper that resolves both subject and body for a
    campaign_contacts row (as returned from DB).

    Returns
    -------
    {
      rendered_subject, rendered_body,
      resolved_vars, fallback_vars, omitted_vars
    }
    """
    snapshot       = contact.get('contact_snapshot') or {}
    score_breakdown = contact.get('score_breakdown') or {}
    warm_path_data  = contact.get('warm_path_data')
    tier            = contact.get('tier', 'tier_2')

    subj, rep_s = resolve(template_subject, snapshot, score_breakdown, warm_path_data, tier)
    body, rep_b = resolve(template_body,    snapshot, score_breakdown, warm_path_data, tier)

    return {
        'rendered_subject': subj,
        'rendered_body':    body,
        'resolved_vars':    list(set(rep_s['resolved'] + rep_b['resolved'])),
        'fallback_vars':    list(set(rep_s['fallback'] + rep_b['fallback'])),
        'omitted_vars':     list(set(rep_s['omitted']  + rep_b['omitted'])),
    }
