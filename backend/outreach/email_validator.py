"""
MX preflight — the cheapest, earliest layer of bounce detection.

Verifies an email address's *domain* has working MX records before we waste
a send on it. A domain with no MX cannot receive mail; an address there is
guaranteed dead. No false positives in the "kill good contacts" direction —
domains *with* MX always pass this check (mailbox-level deadness is layers
2 and 3's job).

Defensive against transient DNS hiccups: retries 2× with a short backoff
before flagging. An in-process cache (with TTL) avoids re-resolving the
same domain on a tight enrollment loop.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Loose RFC-ish check — enough to catch obvious garbage before DNS.
_EMAIL_RE = re.compile(r"^[^\s@]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})$")

# Cache: domain -> (has_mx, expires_at). 6h is plenty — DNS records rarely
# flip on the timescale of a single campaign, and a wrong "no MX" answer
# heals on its own at TTL expiry.
_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[bool, float]] = {}


def _domain_of(email: str) -> Optional[str]:
    m = _EMAIL_RE.match((email or "").strip().lower())
    return m.group(1) if m else None


def _has_mx_sync(domain: str) -> bool:
    """
    Blocking MX lookup with 2 retries on transient failure.

    Returns True if the domain has resolvable MX records (or an implicit A/AAAA
    fallback, per RFC 5321 §5 — some domains accept mail without MX, using the
    A record). Returns False ONLY when DNS consistently reports the domain has
    no mail-accepting records.
    """
    import dns.resolver
    from dns.exception import DNSException
    from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers

    resolver = dns.resolver.Resolver()
    resolver.timeout = 3.0
    resolver.lifetime = 5.0

    attempts = 3
    last_err: Optional[Exception] = None
    for i in range(attempts):
        try:
            answers = resolver.resolve(domain, "MX")
            return len(answers) > 0
        except (NXDOMAIN, NoAnswer):
            # NXDOMAIN: domain doesn't exist. NoAnswer: domain exists but no MX —
            # in that case check for an A record (implicit mail destination).
            try:
                a_answers = resolver.resolve(domain, "A")
                return len(a_answers) > 0
            except (NXDOMAIN, NoAnswer):
                return False
            except DNSException:
                # Treat secondary lookup failures as transient — fall through to retry.
                pass
        except NoNameservers:
            # Resolver couldn't reach any nameserver — transient.
            last_err = Exception("no nameservers")
        except DNSException as e:
            last_err = e
        # Transient — back off and retry.
        time.sleep(0.3 * (i + 1))

    # Consistent failure to resolve. Be defensive — *don't* flag as bad. The
    # email_validator's contract is no false positives. Log and let the send
    # proceed; layer 2/3 will catch it if it really bounces.
    logger.warning(f"[mx-preflight] DNS unreachable for {domain!r}: {last_err}")
    return True


async def has_valid_mx(email: str) -> bool:
    """
    Async wrapper: returns True if the domain has working MX (or an A-record
    fallback). False only when DNS *consistently* says the domain is dead.

    Cached for 6 hours per domain to keep enrollment hot-paths cheap.
    """
    domain = _domain_of(email)
    if not domain:
        # Malformed email — can't even compute a domain. Definitely dead.
        return False

    now = time.monotonic()
    cached = _cache.get(domain)
    if cached and cached[1] > now:
        return cached[0]

    has_mx = await asyncio.to_thread(_has_mx_sync, domain)
    _cache[domain] = (has_mx, now + _CACHE_TTL_SECONDS)
    return has_mx


def clear_cache() -> None:
    """Test helper: drop the MX cache between cases."""
    _cache.clear()
