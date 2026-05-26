"""
Warm path matcher — Layer 3 + 4.

build_index(contacts) -> Index
find_paths(target, index, top_n) -> list[Path]
run(contacts, top_n) -> dict[record_id, list[Path]]
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

CURRENT_YEAR = 2026

# ── large corp list — company overlap is weak signal here ───────────────────
_LARGE_CORPS: frozenset[str] = frozenset({
    "alphabet", "google", "meta", "amazon", "microsoft", "apple", "netflix",
    "salesforce", "oracle", "ibm", "accenture", "deloitte", "pwc", "ey",
    "kpmg", "mckinsey", "bcg", "bain", "goldman sachs", "jpmorgan",
    "morgan stanley", "blackrock", "bank of america", "wells fargo",
    "citigroup", "hsbc",
})

_SENIOR_TITLES: tuple[str, ...] = (
    "ceo", "cto", "coo", "cfo", "cpo", "ciso",
    "president", "founder", "co-founder",
    "vp", "vice president",
    "director", "head",
    "partner", "managing partner", "general partner",
    "principal", "managing director", "md",
)


# ── data types ───────────────────────────────────────────────────────────────

@dataclass
class IndexEntry:
    contact_id: str
    name: str
    title: str
    start: Optional[int]
    end: Optional[int]   # None = still there
    trajectory_tag: str
    company_raw: str


@dataclass
class Path:
    bridge_id: str
    bridge_name: str
    bridge_title: str
    company: str         # raw company name from target's role
    company_key: str
    score: int
    evidence: str


Index = dict[str, list[IndexEntry]]


# ── index builder ────────────────────────────────────────────────────────────

def build_index(contacts) -> Index:
    """One pass over all contacts → inverted index keyed by company_key."""
    index: Index = defaultdict(list)
    for contact in contacts:
        for role in contact.roles:
            index[role.company_key].append(IndexEntry(
                contact_id=   contact.record_id,
                name=         contact.name,
                title=        role.title,
                start=        role.start,
                end=          role.end,
                trajectory_tag=contact.trajectory_tag,
                company_raw=  role.company,
            ))
    return index


# ── scoring ──────────────────────────────────────────────────────────────────

def _is_senior(title: str) -> bool:
    t = title.lower()
    return any(t.startswith(s) or f" {s}" in t for s in _SENIOR_TITLES)


def _resolve_end(end: Optional[int]) -> int:
    return CURRENT_YEAR if end is None else end


def score_overlap(
    t_start: Optional[int], t_end: Optional[int],
    b_start: Optional[int], b_end: Optional[int],
    company_key: str,
    t_title: str, b_title: str,
) -> tuple[int, str]:
    """
    Returns (score, evidence_fragment).
    score = 0 means discard (no overlap in different eras).
    """
    is_large = company_key in _LARGE_CORPS

    # ── one or both dates missing ─────────────────────────────────────────
    if t_start is None or b_start is None:
        score = 45
        evidence = "(dates unavailable)"
        if is_large:
            score = max(0, score - 15)
        return min(score, 100), evidence

    # ── both dates available ──────────────────────────────────────────────
    t_e = _resolve_end(t_end)
    b_e = _resolve_end(b_end)

    overlap = min(t_e, b_e) - max(t_start, b_start)

    if overlap < 0:
        return 0, ""

    # base score by overlap length
    if overlap == 0:
        score = 35
    elif overlap == 1:
        score = 55
    elif overlap == 2:
        score = 70
    else:
        score = 80

    # modifiers
    both_present = (t_end is None and b_end is None)
    if both_present:
        score += 10

    if _is_senior(t_title) and _is_senior(b_title):
        score += 10

    if is_large:
        if overlap < 2:
            score -= 15
    else:
        score += 15

    # evidence string
    t_end_str = "present" if t_end is None else str(t_end)
    b_end_str = "present" if b_end is None else str(b_end)
    if both_present:
        evidence = f"{t_start}-present | both still there"
    elif overlap == 0:
        evidence = f"{t_start}-{t_end_str} / {b_start}-{b_end_str} | briefly overlapped"
    else:
        evidence = f"{t_start}-{t_end_str} / {b_start}-{b_end_str} | {overlap}yr overlap"

    return min(max(score, 0), 100), evidence


# ── path finder ──────────────────────────────────────────────────────────────

def find_paths(target, index: Index, top_n: int = 5) -> list[Path]:
    """
    Find all bridge contacts that share a company with target.
    Returns top_n paths sorted by score descending.
    """
    # bridge_id → best Path (keep highest score if same bridge via multiple companies)
    best: dict[str, Path] = {}

    for role in target.roles:
        candidates = index.get(role.company_key, [])
        for entry in candidates:
            if entry.contact_id == target.record_id:
                continue  # skip self

            score, evidence_frag = score_overlap(
                t_start=role.start,   t_end=role.end,
                b_start=entry.start,  b_end=entry.end,
                company_key=role.company_key,
                t_title=role.title,   b_title=entry.title,
            )

            if score == 0:
                continue

            evidence = f"Both at {role.company} | {evidence_frag}"

            existing = best.get(entry.contact_id)
            if existing is None or score > existing.score:
                best[entry.contact_id] = Path(
                    bridge_id=    entry.contact_id,
                    bridge_name=  entry.name,
                    bridge_title= entry.title,
                    company=      role.company,
                    company_key=  role.company_key,
                    score=        score,
                    evidence=     evidence,
                )

    paths = sorted(best.values(), key=lambda p: p.score, reverse=True)
    return paths[:top_n]


# ── top-level runner ─────────────────────────────────────────────────────────

def run(contacts, top_n: int = 5) -> dict[str, list[Path]]:
    """
    Full warm path computation over a contact list.

    Returns dict mapping target record_id → list of top Paths.
    Only Tier 1/2 contacts get path results; all contacts are in the bridge pool.
    """
    index = build_index(contacts)
    results: dict[str, list[Path]] = {}

    for contact in contacts:
        if not contact.is_target:
            continue
        paths = find_paths(contact, index, top_n=top_n)
        if paths:
            results[contact.record_id] = paths

    return results
