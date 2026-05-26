"""
Apify Crunchbase scraper — satisfies a scraper boundary pattern.

All ApifyClient usage AND Apify-specific normalization for Crunchbase live here.
Deferred to Week 2 — wired in but not yet called from the pipeline.
"""
import logging
from typing import Any, Dict, List

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

_ACTOR_ID = "curious_coder/crunchbase-scraper"


def normalize_crunchbase_data(raw_item: Dict[str, Any], profile_url: str) -> Dict[str, Any]:
    """Normalise raw Apify Crunchbase output into a consistent dict."""
    entity = raw_item.get("entities", [{}])[0] if raw_item.get("entities") else raw_item
    props = entity.get("properties", entity)

    funding_rounds = props.get("funding_rounds") or raw_item.get("fundingRounds") or []
    total_funding  = (
        props.get("total_funding_usd")
        or props.get("totalFunding")
        or raw_item.get("totalFundingUsd")
    )
    investors  = props.get("investors") or raw_item.get("investors") or []
    first_name = props.get("first_name") or raw_item.get("firstName")
    last_name  = props.get("last_name")  or raw_item.get("lastName")
    full_name  = (
        props.get("full_name")
        or raw_item.get("fullName")
        or raw_item.get("name")
        or f"{first_name or ''} {last_name or ''}".strip()
    )

    return {
        "profile_url": profile_url,
        "entity_type": raw_item.get("entityType") or (
            "person" if "/person/" in profile_url else "organization"
        ),

        "name":        full_name,
        "first_name":  first_name,
        "last_name":   last_name,
        "title":       props.get("title") or raw_item.get("title"),
        "description": props.get("short_description") or props.get("description") or raw_item.get("description"),

        "company_name":  props.get("name") or raw_item.get("name") if "/organization/" in profile_url else None,
        "website":       props.get("homepage_url") or raw_item.get("website") or raw_item.get("homepageUrl"),
        "industry":      props.get("category_list") or raw_item.get("industries") or raw_item.get("industry"),
        "employee_count": props.get("num_employees_enum") or raw_item.get("employeeCount"),
        "founded_on":    props.get("founded_on") or raw_item.get("foundedOn"),
        "ipo_status":    props.get("ipo_status") or raw_item.get("ipoStatus"),

        "total_funding_usd":  total_funding,
        "last_funding_type":  props.get("last_funding_type") or raw_item.get("lastFundingType"),
        "last_funding_at":    props.get("last_funding_at")   or raw_item.get("lastFundingAt"),
        "funding_rounds":     funding_rounds,
        "num_funding_rounds": props.get("num_funding_rounds") or len(funding_rounds),

        "investors": investors,

        "linkedin_url": props.get("linkedin") or raw_item.get("linkedinUrl"),
        "twitter_url":  props.get("twitter")  or raw_item.get("twitterUrl"),

        "location": (
            props.get("location_identifiers")
            or raw_item.get("location")
            or raw_item.get("city")
        ),

        "raw_data": raw_item,
    }


class ApifyCrunchbaseScraper:
    """Fetches Crunchbase person/company profiles via Apify."""

    def __init__(self, token: str) -> None:
        self._token = token

    def scrape_raw_profile(self, url: str) -> Dict[str, Any]:
        """Fetch one Crunchbase profile. Returns normalized dict."""
        client = ApifyClient(self._token)
        run = client.actor(_ACTOR_ID).call(run_input={"startUrls": [{"url": url}]})
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            logger.debug(f"Crunchbase raw keys: {list(item.keys())}")
            return normalize_crunchbase_data(item, url)
        logger.warning(f"No Crunchbase data returned for {url}")
        return {}
