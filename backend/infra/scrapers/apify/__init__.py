"""
Apify scraper implementation — all ApifyClient usage lives here.
"""
from backend.infra.scrapers.apify.pool import get_pool, ApifyTokenPool


class ApifyCreditsError(Exception):
    """Raised on Apify 403 — credits exhausted or token invalid. Do not retry."""


def check_apify_403(e: Exception) -> None:
    """Raise ApifyCreditsError if the exception indicates a 403."""
    status = getattr(e, "status_code", None) or getattr(e, "status", None)
    if status == 403:
        raise ApifyCreditsError(f"Apify 403 — credits exhausted or token invalid: {e}") from e
    msg = str(e)
    if "403" in msg or "Forbidden" in msg or "forbidden" in msg:
        raise ApifyCreditsError(f"Apify 403 — credits exhausted or token invalid: {msg}") from e


__all__ = ["ApifyCreditsError", "check_apify_403", "get_pool", "ApifyTokenPool"]
