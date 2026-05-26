"""
Company name normalizer for warm path career overlap matching.

normalize(raw) -> str

Pipeline:
  1. Lowercase
  2. Strip legal suffixes
  3. Strip punctuation
  4. Strip leading "the"
  5. Collapse whitespace
  6. Apply known aliases
  7. Fuzzy dedup (Levenshtein <= 1 for len >= 8) — applied externally on the
     full index, not per-name, so not part of this function
"""

import re
import unicodedata
from typing import Optional

# ── legal suffix pattern ────────────────────────────────────────────────────
# applied as whole-word matches at the end of the string

_LEGAL_SUFFIXES = [
    "incorporated", "inc",
    "limited liability company", "llc",
    "limited", "ltd",
    "corporation", "corp",
    "company", "co",
    "public limited company", "plc",
    "gesellschaft mit beschränkter haftung", "gmbh",
    "aktiengesellschaft", "ag",
    "besloten vennootschap", "bv",
    "naamloze vennootschap", "nv",
    "proprietary limited", "pty",
    "private limited", "pvt",
    "group",
    "holdings", "holding",
    "technologies", "technology",
    "tech",
    "services",
    "solutions",
    "systems",
    "ventures",
    "partners", "partnership",
    "management",
    "international",
    "global",
    "association",
    "enterprises", "enterprise",
]

# build one regex: trailing suffix(es) preceded by comma/space, repeated
_SUFFIX_PATTERN = re.compile(
    r'[,\s]+(?:' + '|'.join(re.escape(s) for s in sorted(_LEGAL_SUFFIXES, key=len, reverse=True)) + r')+\s*$',
    re.IGNORECASE,
)

# ── punctuation to strip ────────────────────────────────────────────────────
_PUNCT_RE = re.compile(r"[.,'\"\-–—&@#()\[\]{}|\\/:;!?*]")

# ── noise names — not real employers, skip in index ────────────────────────
_NOISE_NAMES: frozenset[str] = frozenset({
    "self employed", "self-employed", "freelance", "freelancer",
    "independent", "independent consultant", "independent contractor",
    "consultant", "contractor", "advisor", "advisors",
    "various", "n/a", "none", "unknown", "stealth", "stealth startup",
})

# ── known aliases ───────────────────────────────────────────────────────────
# applied AFTER the suffix/punct stripping, so keys are already normalized
_ALIASES: dict[str, str] = {
    # Meta family
    "facebook":                     "meta",
    "instagram":                    "meta",
    "whatsapp":                     "meta",
    "oculus":                       "meta",
    # Alphabet family
    "google":                       "alphabet",
    "youtube":                      "alphabet",
    "deepmind":                     "alphabet",
    "waymo":                        "alphabet",
    # Microsoft family
    "linkedin":                     "microsoft",
    "github":                       "microsoft",
    "skype":                        "microsoft",
    # Amazon family
    "aws":                          "amazon",
    "amazon web services":          "amazon",
    "twitch":                       "amazon",
    # Finance — banks
    "jp morgan":                    "jpmorgan",
    "j p morgan":                   "jpmorgan",
    "jpmorgan chase":               "jpmorgan",
    "jp morgan chase":              "jpmorgan",
    "bank of america merrill lynch":"bank of america",
    "bofa":                         "bank of america",
    "wells fargo bank":             "wells fargo",
    "citi":                         "citigroup",
    "citibank":                     "citigroup",
    "citicorp":                     "citigroup",
    "ubs investment bank":          "ubs",
    "credit suisse":                "ubs",           # acquired 2023
    "deutsche bank ag":             "deutsche bank",
    "barclays bank":                "barclays",
    "barclays investment bank":     "barclays",
    "hsbc bank":                    "hsbc",
    # Consulting
    "mckinsey and company":         "mckinsey",
    "mckinsey company":             "mckinsey",
    "the boston consulting":        "bcg",
    "boston consulting":            "bcg",
    "bain and company":             "bain",
    "booz allen hamilton":          "booz allen",
    "oliver wyman":                 "oliver wyman",  # keep distinct
    # Accounting / big 4
    "pricewaterhousecoopers":       "pwc",
    "price waterhouse coopers":     "pwc",
    "price waterhouse":             "pwc",
    "ernst young":                  "ey",
    "ernst and young":              "ey",
    "kpmg peat marwick":            "kpmg",
    "deloitte touche":              "deloitte",
    "deloitte touche tohmatsu":     "deloitte",
    # VC / PE common variants
    "andreessen horowitz":          "a16z",
    "a16z crypto":                  "a16z",
    "sequoia capital":              "sequoia",
    "sequoia capital india":        "sequoia",
    "benchmark capital":            "benchmark",
    "general catalyst partners":    "general catalyst",
    "bessemer venture partners":    "bessemer",
    "tiger global management":      "tiger global",
    "softbank vision fund":         "softbank",
    "softbank investment advisers": "softbank",
    # Common university variants
    "massachusetts institute of technology": "mit",
    "harvard business school":      "harvard",
    "stanford graduate school of business": "stanford",
    "london school of economics and political science": "lse",
    "london school of economics":   "lse",
    # Misc well-known
    "alphabet inc":                 "alphabet",
    "meta platforms":               "meta",
}


# ── normalizer ──────────────────────────────────────────────────────────────

def normalize(raw: Optional[str]) -> str:
    """
    Normalize a company name for index key comparison.
    Returns empty string if input is empty/None or is a noise name
    (self-employed, freelance, etc.) that should not be indexed.
    """
    if not raw:
        return ""

    # unicode → ascii-safe (handles accented chars, smart quotes etc.)
    text = unicodedata.normalize("NFKD", raw)
    text = text.encode("ascii", "ignore").decode("ascii")

    # lowercase
    text = text.lower().strip()

    # strip parenthetical annotations before anything else
    # "Honeydew (YC W23)" → "Honeydew", "MLLC (None-present)" → "MLLC"
    text = re.sub(r'\s*\([^)]*\)', '', text).strip()

    # strip punctuation first so trailing dots don't block suffix matching
    # e.g. "Butterfly Network, Inc." → "butterfly network  inc " → suffix strips cleanly
    text = _PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # strip legal suffixes (may repeat: "Holdings LLC" → strip both)
    prev = None
    while prev != text:
        prev = text
        text = _SUFFIX_PATTERN.sub("", text).strip()

    # strip leading "the "
    if text.startswith("the "):
        text = text[4:].strip()

    # alias lookup (exact match on normalized form)
    text = _ALIASES.get(text, text)

    # reject noise names — not real employers
    if text in _NOISE_NAMES:
        return ""

    return text
