"""
Context-building helpers for the email generation agent.

Pure functions — no LLM calls, no I/O.
The agent that uses these lives in backend/agents/outreach/.
"""
from __future__ import annotations

import re
from typing import Any


def _stringify(v) -> str:
    if v is None:
        return ''
    if isinstance(v, list):
        return ', '.join(str(x) for x in v if x)
    return str(v).strip()


def _tier_context(goal: str, tier: str, scan: dict) -> str:
    total   = scan.get('total', 0)
    signals = {**(scan.get('signals') or {}), **(scan.get('contact_fields') or {})}
    labels  = {
        'tier_1': 'Warmest contacts (strong giving indicators + warm-path connections)',
        'tier_2': 'Solid prospects (giving history or capacity signals present)',
        'tier_3': 'Broader cultivation pool (lower signal density, real intent)',
    }
    tones   = {
        'tier_1': 'warm, personal, direct ask',
        'tier_2': 'respectful, professional, clear mission ask',
        'tier_3': 'inclusive, hopeful, low-friction',
    }
    dominant = [f"{v['pct']}% {k}" for k, v in signals.items() if v.get('pct', 0) >= 30]
    ctx = f"{labels.get(tier, 'Contacts')} for goal: \"{goal}\". {total} contacts. Tone: {tones.get(tier, 'warm')}."
    if dominant:
        ctx += f" Dominant signals: {', '.join(dominant[:4])}."
    return ctx


def _build_context(goal: str, tier: str, scan: dict, samples: list[dict]) -> str:
    total    = scan.get('total', 0)
    all_sigs = {**(scan.get('signals') or {}), **(scan.get('contact_fields') or {})}

    sig_lines, dominant = [], []
    for k, v in all_sigs.items():
        pct = v.get('pct', 0)
        sig_lines.append(f"  {k}: {v['count']}/{total} ({pct}%)")
        if pct >= 40:
            dominant.append(f"{k} ({pct}%)")
    coverage      = '\n'.join(sig_lines) or '  (no coverage data)'
    dominant_note = (
        f"\nDominant — weave these into the appeal: {', '.join(dominant)}" if dominant else ''
    )

    sample_lines, has_warm = [], False
    for i, c in enumerate(samples[:12], 1):
        snap = c.get('contact_snapshot') or {}
        sigs = snap.get('signals') or {}
        raw  = snap.get('raw_fields') or {}
        wp   = c.get('warm_path_data') or {}

        line = f"{i}. {snap.get('name','?')}"
        role_parts = [x for x in [snap.get('title'), snap.get('company')] if x]
        if role_parts:
            line += f" ({', '.join(role_parts)})"
        location = (raw.get('Realtime location') or raw.get('City') or '').strip()
        if location:
            line += f" · {location}"

        details = []

        # Factual insight about this person — context to inform a relevant opener
        # (draw on it naturally; do NOT copy it verbatim into the email)
        insight = (raw.get('personalization_hook') or '').strip()
        if insight:
            details.append(f"about: {insight[:200]}")

        # Industry context
        industry = (raw.get('Realtime company industry') or raw.get('Industry') or '').strip()
        if industry:
            details.append(f"industry: {industry}")

        # All signals — order by fundraising relevance
        giving   = _stringify(sigs.get('giving'))
        wealth   = _stringify(sigs.get('wealth'))
        capacity = _stringify(sigs.get('capacity'))
        topics   = _stringify(sigs.get('topics'))
        persona  = _stringify(sigs.get('personality'))
        engage   = _stringify(sigs.get('engagement'))

        if giving:   details.append(f"giving: {giving[:120]}")
        if wealth:   details.append(f"wealth: {wealth[:120]}")
        if capacity: details.append(f"capacity: {capacity}")
        if topics:   details.append(f"interests: {topics}")
        if persona:  details.append(f"personality: {persona}")
        if engage:   details.append(f"engagement: {engage}")

        # Career trajectory — prefer full signal text over the archetype tag
        traj_text = (raw.get('trajectory_signal') or '').strip()
        traj_tag  = _stringify(sigs.get('trajectory'))
        if traj_text:
            details.append(f"trajectory: {traj_text[:140]}")
        elif traj_tag:
            details.append(f"trajectory: {traj_tag}")

        # Career history
        career = (raw.get('last_three_roles') or raw.get('Realtime last 3 companies') or '').strip()
        if career:
            details.append(f"career: {career[:120]}")

        if wp.get('connector'):
            details.append(f"warm path via {wp['connector']}")
            has_warm = True

        if details:
            line += '\n   · ' + '\n   · '.join(details)
        sample_lines.append(line)

    warm_note = (
        "\nNote: warm-path connections present — tone must feel collegial, not cold outreach."
        if has_warm else ''
    )

    return (
        f"CAMPAIGN GOAL (name this explicitly — never paraphrase):\n  {goal}\n\n"
        f"TIER: {_tier_context(goal, tier, scan)}{warm_note}\n\n"
        f"SIGNAL COVERAGE ({total} contacts):\n{coverage}{dominant_note}\n\n"
        f"CONTACT SAMPLES:\n" + '\n'.join(sample_lines or ['  (no samples available)'])
    )


def _coverage_summary(scan: dict) -> tuple[int, int, str]:
    total    = scan.get('total', 0)
    all_sigs = {**(scan.get('signals') or {}), **(scan.get('contact_fields') or {})}
    max_pct  = max((v.get('pct', 0) for v in all_sigs.values()), default=0) if all_sigs else 0
    lines    = [f"{k} {v.get('pct',0)}%" for k, v in all_sigs.items() if v.get('pct',0) >= 20]
    return total, max_pct, ', '.join(lines[:4]) if lines else 'no strong signals'


def _compute_field_coverage(samples: list[dict], fields: list[str]) -> dict[str, int]:
    if not samples or not fields:
        return {}
    total = len(samples)
    result = {}
    for field in fields:
        variants = {
            field, field.lower(),
            field.lower().replace(' ', '_'),
            field.lower().replace('_', ' '),
            field.lower().replace('-', '_'),
        }
        count = 0
        for c in samples:
            snap = c.get('contact_snapshot') or {}
            if any(bool(_stringify(snap.get(v))) for v in variants):
                count += 1
        result[field] = round(count / total * 100)
    return result


def _format_field_coverage(coverage: dict[str, int], fields: list[str]) -> str:
    if not coverage and not fields:
        return "No CRM fields available for personalization."

    lines = ["CRM FIELD POPULATION RATES (based on sample contacts):"]
    for f in fields:
        pct = coverage.get(f, 0)
        if pct >= 70:
            verdict = "safe to use"
        elif pct >= 40:
            verdict = "use with fallback"
        elif pct > 0:
            verdict = "risky — strong fallback required"
        else:
            verdict = "not populated — skip"
        lines.append(f"  [{f}]: {pct}% populated — {verdict}")

    safe   = [f for f in fields if coverage.get(f, 0) >= 70]
    medium = [f for f in fields if 40 <= coverage.get(f, 0) < 70]

    rec_parts = []
    if safe:
        rec_parts.append(f"Prioritise: {', '.join(f'[{f}]' for f in safe[:3])}")
    if medium:
        rec_parts.append(f"Use with fallback: {', '.join(f'[{f}]' for f in medium[:2])}")
    if rec_parts:
        lines.append("\nRECOMMENDATION: " + ". ".join(rec_parts) + ".")
        lines.append("Every slot MUST have a fallback: [field | fallback: \"natural default\"].")

    return '\n'.join(lines)


def _ensure_html(text: str) -> str:
    if not text.strip():
        return text
    if re.search(r'<[pP][\s>]|<br[\s/]', text):
        return text
    sep   = r'\n{2,}' if '\n\n' in text else r'\n'
    paras = [p.strip() for p in re.split(sep, text) if p.strip()]
    return ''.join(f'<p>{p}</p>' for p in paras) if paras else f'<p>{text.strip()}</p>'


def _sanitize(subject: str, body: str) -> tuple[str, str]:
    subject = re.sub(r'\{\{(\w+)(?:[^}]*)?\}\}', r'[\1]', subject)
    body    = re.sub(r'\{\{(\w+)(?:[^}]*)?\}\}', r'[\1]', body)
    return subject, body


def _extract_variables(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'\[(\w+)', text)))


def _apply_write_tool(name: str, args: dict, subject: str, body: str) -> tuple[str, str]:
    if name == 'rewrite_both':
        subject = str(args.get('new_subject', subject))
        body    = _ensure_html(str(args.get('new_body', body)))
    elif name == 'rewrite_subject':
        subject = str(args.get('new_subject', subject))
    elif name == 'rewrite_body':
        body = _ensure_html(str(args.get('new_body', body)))
    return _sanitize(subject, body)
