"""
Email Generation Agent — single-pass, streamed, with a deterministic gate.

Flow:
  1. READING  — gather resolvable slot vocabulary + context (no LLM)
  2. WRITING   — ONE streamed generation call; body streams live to the UI
  3. POLISHING — symbolic check; one focused fix call ONLY if a real violation
  4. VARIANTS  — subject alternatives (runs in parallel)

No LLM critique loop. The strong model writes once; a deterministic check
catches the few things that actually matter (forbidden phrases, ignored
constraints, unresolvable slots) and fixes only those.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from backend.config import Config
from backend.agents.outreach.prompts import (
    MAX_GENERATE_CALLS, MAX_FIX_CALLS, _GENERATE_SYSTEM, _FIX_SYSTEM,
)
from backend.outreach.template_generator import (
    _build_context, _coverage_summary,
    _compute_field_coverage, _ensure_html, _sanitize, _extract_variables,
)

logger = logging.getLogger(__name__)

# ── Forbidden phrases — always enforced ───────────────────────────────────────

_FORBIDDEN: list[str] = [
    "i hope you're", "i hope you are", "i hope this finds", "hope this email",
    "i trust you", "i trust this", "hope you're doing", "hope all is well",
    "transformative", "make a difference", "lasting impact",
    "incredible opportunity", "important work", "important cause",
    "our mission", "meaningful endeavor", "meaningful journey", "this endeavor",
]
_FORBIDDEN_DISPLAY = (
    "any 'I hope…' opener, 'transformative', 'make a difference', 'lasting impact', "
    "'incredible opportunity', 'important work', 'our mission', 'meaningful', 'endeavor'"
)


# ── Resolvable slot vocabulary ─────────────────────────────────────────────────

def _resolvable_slots(scan: dict, field_coverage: dict, has_warm: bool) -> str:
    """
    Build the list of personalization slots the model is allowed to use —
    only slots the variable_resolver can actually fill. Prevents the model
    inventing [industry]/[interest] slots that render as broken text.
    """
    sigs   = scan.get('signals') or {}
    fields = scan.get('contact_fields') or {}

    def pct(d: dict, k: str) -> float:
        return (d.get(k) or {}).get('pct', 0)

    slots: list[str] = ["[first_name] — recipient's first name (always available)"]

    if pct(fields, 'company') >= 40:
        slots.append('[company | fallback: "your organization"] — their company')
    if pct(fields, 'title') >= 40:
        slots.append('[title | fallback: "your role"] — their job title')
    if pct(sigs, 'topics') >= 25:
        slots.append('[topic_hook | fallback: "this work"] — their topic interests as a plain noun, e.g. "advertising, technology". Write your own lead-in, e.g. "given your interest in [topic_hook | fallback: \\"this work\\"]". The slot does NOT include the lead-in words.')
    if pct(sigs, 'giving') >= 25:
        slots.append('[giving_reference | fallback: "causes like this"] — what they\'ve given to, as a plain noun, e.g. "education and climate". Write your own lead-in, e.g. "your past support of [giving_reference | fallback: \\"causes like this\\"]". The slot does NOT include the lead-in words.')
    slots.append('[capacity_close | fallback: "a gift at any level"] — tier-appropriate ask framing (always available)')
    if has_warm:
        slots.append('[warm_opener | fallback: ""] — renders "Through <connector>,"; use to open warmly')

    # High-coverage Airtable fields the user can also slot in by exact name
    for fname, cov in (field_coverage or {}).items():
        if cov >= 60 and fname.lower() not in ('company', 'title', 'name', 'email', 'first name', 'personalization_hook'):
            slots.append(f'[{fname} | fallback: "…"] — {cov}% populated')

    return "\n".join(f"  · {s}" for s in slots)


# ── Constraint block (placed at END of prompts = highest weight) ───────────────

def _build_constraint_block(active_guidance: str, history: list[str]) -> str:
    lines: list[str] = []

    # Fundraiser guidance = directions for HOW to write. It is NOT email content.
    # De-dup current + recent prior guidance, current first.
    seen: set[str] = set()
    instructions: list[str] = []
    for g in [active_guidance, *history[-3:]]:
        g = (g or "").strip()
        if g and g not in seen:
            seen.add(g)
            instructions.append(g)

    if instructions:
        lines.append("FUNDRAISER INSTRUCTIONS — directions for HOW to write this email.")
        lines.append("Follow them exactly. They are instructions, NOT content — NEVER copy, quote, "
                     "answer, or restate any of this wording inside the email itself.")
        for g in instructions:
            lines.append(f"  • {g}")
        lines.append("")

    lines.append("HARD RULES:")
    lines.append(f"  • Never use these phrases anywhere in the email: {_FORBIDDEN_DISPLAY}")
    lines.append("  • Use only the slots listed under RESOLVABLE SLOTS, each with a fallback")
    return "\n".join(lines)


# ── Draft parsing ──────────────────────────────────────────────────────────────

_SUBJECT_RE = re.compile(r'SUBJECT:\s*(.+?)(?:\n|$)', re.IGNORECASE)


def _parse_draft(text: str) -> tuple[str, str]:
    """Parse 'SUBJECT: ...\\nBODY:\\n...' into (subject, body_raw)."""
    subject = ''
    m = _SUBJECT_RE.search(text)
    if m:
        subject = m.group(1).strip().strip('"')
    parts = re.split(r'\n?\s*BODY:\s*\n?', text, maxsplit=1, flags=re.IGNORECASE)
    body = parts[1].strip() if len(parts) == 2 else ''
    return subject, body


# ── Symbolic validation ────────────────────────────────────────────────────────

def _symbolic_check(subject: str, body: str, guidance: str, goal: str, allowed_slots: set[str]) -> list[str]:
    violations: list[str] = []
    text = (subject + " " + body).lower()

    for phrase in _FORBIDDEN:
        if phrase in text:
            violations.append(f"Remove dead phrase: '{phrase}'")

    # Unresolvable slots — the model invented a slot that won't render
    for raw in re.findall(r'\[([A-Za-z][A-Za-z0-9 _]*)', subject + " " + body):
        name = raw.strip().lower()
        if name not in allowed_slots:
            violations.append(
                f"Slot [{raw.strip()}] is not resolvable — replace with a slot from RESOLVABLE SLOTS or plain text"
            )

    if guidance:
        g = guidance.lower()
        # "don't mention the amount"
        if re.search(r"\b(no|not|don'?t|avoid|omit|without)\b.{0,30}(amount|sum|dollar|\$|figure|specific)", g):
            amounts = re.findall(
                r'\$[\d,]+(?:\s*[MBK]|\s*million|\s*billion|\s*thousand)?'
                r'|\d[\d,]*\s*(?:million|billion|thousand)',
                goal, re.IGNORECASE,
            )
            for amt in amounts:
                if amt.lower() in text:
                    violations.append(f"Remove '{amt}' — fundraiser asked not to mention the specific amount")
        # "secure a call / meeting"
        if re.search(r'(secure|book|schedule|arrange|get|set up|request)\s+a?\s*(call|meeting|chat|time|conversation|appointment)', g):
            if not any(s in text for s in ["call", "meeting", "chat", "connect", "speak", "15 min", "30 min", "appointment", "schedule", "talk"]):
                violations.append("Add a clear ask for a short call/meeting — fundraiser asked to secure one")

    return violations


# ── Tier insight (unchanged, cheap model) ──────────────────────────────────────

async def generate_tier_insight(goal: str, tier: str, scan: dict, samples: list[dict], provider=None) -> str:
    if provider is None:
        from backend.infra.llm.factory import get_llm_provider
        provider = get_llm_provider()
    client = provider.raw_client

    total, _, cov_summary = _coverage_summary(scan)
    sample_preview = '; '.join(
        f"{(c.get('contact_snapshot') or {}).get('name','?')} "
        f"({(c.get('contact_snapshot') or {}).get('title','')})"
        for c in samples[:5] if c.get('contact_snapshot')
    ) or 'no samples'

    try:
        resp = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': (
                    'You are a terse fundraising data analyst. Write exactly 1-2 sentences. '
                    'Only concrete facts: signal percentages, dominant titles, industries, giving patterns. '
                    'No generic advice. No preamble.'
                )},
                {'role': 'user', 'content': (
                    f'Campaign: "{goal}" | Tier: {tier} ({total} contacts) | '
                    f'Signals: {cov_summary} | Samples: {sample_preview}\n\n'
                    f'What concrete patterns stand out in this audience?'
                )},
            ],
            temperature=0.2, max_tokens=120,
        )
        return (resp.choices[0].message.content or '').strip()
    except Exception as e:
        logger.warning(f'Tier insight failed (non-fatal): {e}')
        return ''


# ── Subject variants (cheap model, parallel) ───────────────────────────────────

async def _get_subject_variants(client: Any, subject: str, body: str) -> list[str]:
    try:
        vr = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': 'Email subject writer. Return valid JSON only.'},
                {'role': 'user', 'content': (
                    f'Body:\n{body}\nCurrent subject: "{subject}"\n\n'
                    f'Write 2 alternative subjects (different angles). 5-9 words, conversational, no ALL CAPS.\n'
                    f'Return: {{"alternatives": ["...", "..."]}}'
                )},
            ],
            response_format={'type': 'json_object'},
            temperature=0.9, max_tokens=80,
        )
        alts = json.loads(vr.choices[0].message.content or '{}').get('alternatives', [])[:2]
        return [subject] + [str(a) for a in alts]
    except Exception as e:
        logger.warning(f'Subject variants failed (non-fatal): {e}')
        return []


# ── Main streaming agent ───────────────────────────────────────────────────────

async def generate_streaming(
    goal: str,
    tier: str,
    scan: dict,
    samples: list[dict],
    guidance: str = '',
    existing_subject: str = '',
    existing_body: str = '',
    guidance_history: list[str] | None = None,
    airtable_fields: list[str] | None = None,
    tier_insight: str = '',
    source_material: str = '',
    provider=None,
):
    """
    Streaming email generation.

    Events:
      data_warning                          — thin signal coverage
      status   {step, label}                — reading | writing | polishing | done
      draft    {subject, body}              — live email as it's written
      subject_variants {variants}
      complete {result} | error {message}
    """
    if provider is None:
        from backend.infra.llm.factory import get_llm_provider
        provider = get_llm_provider()
    client = provider.raw_client

    total, max_sig_pct, _ = _coverage_summary(scan)
    history         = [g for g in (guidance_history or []) if g and g.strip()]
    active_guidance = guidance.strip() if guidance and guidance.strip() else ''

    _skip = {'id', 'email', 'status', 'created_at', 'updated_at', 'record_id',
             'tier', 'score', 'name', 'first_name', 'firstname', 'last_name', 'lastname'}
    relevant_slots = [f for f in (airtable_fields or []) if f.lower() not in _skip][:8]
    field_coverage = _compute_field_coverage(samples, relevant_slots)

    has_warm = any((c.get('warm_path_data') or {}).get('connector') for c in samples)

    # ── READING ───────────────────────────────────────────────────────────────
    yield {'type': 'status', 'step': 'reading', 'label': f'Reading {len(samples)} contacts and their signals…'}

    data_context = _build_context(goal, tier, scan, samples)
    if tier_insight and tier_insight.strip():
        data_context = f"AUDIENCE INSIGHT: {tier_insight.strip()}\n\n" + data_context
    if source_material and source_material.strip():
        # The fundraiser's own deck/brief — ground the mission and facts in this,
        # don't invent. Placed first so it anchors the email's substance.
        data_context = (
            "CAMPAIGN SOURCE MATERIAL (from the fundraiser's deck — use its real facts, "
            "language, and numbers; do not invent beyond it):\n"
            f"{source_material.strip()}\n\n" + data_context
        )

    slot_block       = _resolvable_slots(scan, field_coverage, has_warm)
    constraint_block = _build_constraint_block(active_guidance, history)

    # Allowed slot names for symbolic validation (lowercased)
    allowed = {'first_name', 'company', 'title', 'topic_hook', 'giving_reference',
               'capacity_close', 'warm_opener'}
    allowed |= {f.lower() for f in relevant_slots}

    if total > 0 and max_sig_pct < 30:
        yield {'type': 'data_warning', 'text': (
            f"Signal coverage is thin — only {max_sig_pct}% of {total} contacts have meaningful signals. "
            f"The email will lean on name and role; enrich data for stronger personalization."
        )}

    user_prompt = (
        f"{data_context}\n\n"
        f"RESOLVABLE SLOTS (use only these):\n{slot_block}\n\n"
        f"Write the email now in the exact SUBJECT/BODY format.\n\n"
        f"{constraint_block}"
    )

    # ── WRITING (streamed) ──────────────────────────────────────────────────────
    yield {'type': 'status', 'step': 'writing', 'label': 'Writing the email…'}

    subject, body = '', ''
    try:
        for attempt in range(MAX_GENERATE_CALLS):
            stream = await client.chat.completions.create(
                model=Config.OPENAI_GENERATION_MODEL,
                messages=[
                    {'role': 'system', 'content': _GENERATE_SYSTEM},
                    {'role': 'user',   'content': user_prompt},
                ],
                stream=True,
                temperature=0.75,
                max_tokens=700,
            )
            acc = ''
            last_emit = ''
            async for chunk in stream:
                tok = (chunk.choices[0].delta.content or '') if chunk.choices else ''
                if not tok:
                    continue
                acc += tok
                s, b = _parse_draft(acc)
                # Emit live once the body has started forming
                if b and b != last_emit:
                    last_emit = b
                    yield {'type': 'draft', 'subject': s, 'body': b}

            subject, body = _parse_draft(acc)
            if subject and body:
                break
            logger.warning(f'Generation attempt {attempt + 1} produced incomplete draft; retrying')

        if not body:
            yield {'type': 'error', 'message': 'Could not produce a draft — try again.'}
            return

    except Exception as e:
        logger.error(f'Generation failed: {e}', exc_info=True)
        yield {'type': 'error', 'message': f'Generation failed: {e}'}
        return

    # Start subject variants now — runs while we polish
    variants_task = asyncio.create_task(_get_subject_variants(client, subject, _ensure_html(body)))

    # ── POLISHING (deterministic gate) ──────────────────────────────────────────
    violations = _symbolic_check(subject, body, active_guidance, goal, allowed)
    if violations:
        logger.info(f"Symbolic gate: {len(violations)} violation(s) → focused fix")
        yield {'type': 'status', 'step': 'polishing', 'label': 'Polishing to match your guidance…'}

        for _ in range(MAX_FIX_CALLS):
            issues = '\n'.join(f'- {v}' for v in violations)
            fix_prompt = (
                f"CURRENT DRAFT:\nSUBJECT: {subject}\nBODY:\n{body}\n\n"
                f"VIOLATIONS TO FIX (fix all, change nothing else):\n{issues}\n\n"
                f"RESOLVABLE SLOTS:\n{slot_block}\n\n"
                f"{constraint_block}"
            )
            try:
                stream = await client.chat.completions.create(
                    model=Config.OPENAI_GENERATION_MODEL,
                    messages=[
                        {'role': 'system', 'content': _FIX_SYSTEM},
                        {'role': 'user',   'content': fix_prompt},
                    ],
                    stream=True,
                    temperature=0.3,
                    max_tokens=700,
                )
                acc = ''
                last_emit = ''
                async for chunk in stream:
                    tok = (chunk.choices[0].delta.content or '') if chunk.choices else ''
                    if not tok:
                        continue
                    acc += tok
                    s, b = _parse_draft(acc)
                    if b and b != last_emit:
                        last_emit = b
                        yield {'type': 'draft', 'subject': s, 'body': b}
                ns, nb = _parse_draft(acc)
                if ns and nb:
                    subject, body = ns, nb
            except Exception as e:
                logger.warning(f'Fix call failed (non-fatal): {e}')
                break

            violations = _symbolic_check(subject, body, active_guidance, goal, allowed)
            if not violations:
                break

    # ── FINALISE ────────────────────────────────────────────────────────────────
    subject, body = _sanitize(subject, _ensure_html(body))
    variables = _extract_variables(subject + ' ' + body)

    yield {'type': 'status', 'step': 'done', 'label': 'Done'}
    yield {'type': 'draft', 'subject': subject, 'body': body}

    try:
        variants = await variants_task
        if variants:
            yield {'type': 'subject_variants', 'variants': variants}
    except (asyncio.CancelledError, Exception) as e:  # noqa
        if not isinstance(e, asyncio.CancelledError):
            logger.warning(f'Subject variants await failed: {e}')

    logger.info("Agent done tier=%s vars=%s clean=%s", tier, variables, not violations)

    yield {
        'type': 'complete',
        'result': {
            'subject':      subject,
            'body':         body,
            'variables':    variables,
            'tier_summary': '',
            'final_score':  10 if not violations else 7,
        },
    }


async def generate(goal: str, tier: str, scan: dict, samples: list[dict], guidance: str = '') -> dict[str, Any]:
    """Non-streaming shim — collects the complete event."""
    result: dict[str, Any] = {}
    async for event in generate_streaming(goal, tier, scan, samples, guidance=guidance):
        if event['type'] == 'complete':
            result = event['result']
        elif event['type'] == 'error':
            raise RuntimeError(event['message'])
    return result
