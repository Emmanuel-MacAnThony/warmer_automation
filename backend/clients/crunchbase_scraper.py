"""
Crunchbase Scraper using Apify
Supports person and company profiles via Crunchbase URL
"""
import json
import logging
from typing import Any, Dict

from apify_client import ApifyClient

from backend.config import Config

logger = logging.getLogger(__name__)

ACTOR_ID = "curious_coder/crunchbase-scraper"


def normalize_crunchbase_data(raw_item: Dict[str, Any], profile_url: str) -> Dict[str, Any]:
    """Normalise raw Apify Crunchbase actor output into a consistent dict."""
    entity = raw_item.get("entities", [{}])[0] if raw_item.get("entities") else raw_item
    props = entity.get("properties", entity)

    # Funding rounds
    funding_rounds = props.get("funding_rounds") or raw_item.get("fundingRounds") or []
    total_funding = (
        props.get("total_funding_usd")
        or props.get("totalFunding")
        or raw_item.get("totalFundingUsd")
    )

    # Investors
    investors = props.get("investors") or raw_item.get("investors") or []

    # Person-specific fields
    first_name = props.get("first_name") or raw_item.get("firstName")
    last_name = props.get("last_name") or raw_item.get("lastName")
    full_name = (
        props.get("full_name")
        or raw_item.get("fullName")
        or raw_item.get("name")
        or f"{first_name or ''} {last_name or ''}".strip()
    )

    return {
        "profile_url": profile_url,
        "entity_type": raw_item.get("entityType") or ("person" if "/person/" in profile_url else "organization"),

        # Identity
        "name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "title": props.get("title") or raw_item.get("title"),
        "description": props.get("short_description") or props.get("description") or raw_item.get("description"),

        # Organisation fields (populated when entity_type == organization)
        "company_name": props.get("name") or raw_item.get("name") if "/organization/" in profile_url else None,
        "website": props.get("homepage_url") or raw_item.get("website") or raw_item.get("homepageUrl"),
        "industry": props.get("category_list") or raw_item.get("industries") or raw_item.get("industry"),
        "employee_count": props.get("num_employees_enum") or raw_item.get("employeeCount"),
        "founded_on": props.get("founded_on") or raw_item.get("foundedOn"),
        "ipo_status": props.get("ipo_status") or raw_item.get("ipoStatus"),

        # Funding
        "total_funding_usd": total_funding,
        "last_funding_type": props.get("last_funding_type") or raw_item.get("lastFundingType"),
        "last_funding_at": props.get("last_funding_at") or raw_item.get("lastFundingAt"),
        "funding_rounds": funding_rounds,
        "num_funding_rounds": props.get("num_funding_rounds") or len(funding_rounds),

        # Investors / board
        "investors": investors,

        # Social
        "linkedin_url": props.get("linkedin") or raw_item.get("linkedinUrl"),
        "twitter_url": props.get("twitter") or raw_item.get("twitterUrl"),

        # Location
        "location": (
            props.get("location_identifiers")
            or raw_item.get("location")
            or raw_item.get("city")
        ),

        "raw_data": raw_item,
    }


def scrape_crunchbase_profile(profile_url: str) -> Dict[str, Any]:
    """
    Scrape a Crunchbase person or company profile via Apify.

    Args:
        profile_url: Full Crunchbase URL (person or organization)

    Returns:
        Normalized profile dict

    Raises:
        ValueError: If APIFY_API_TOKEN not configured
        Exception: If scraping fails
    """
    if not Config.APIFY_API_TOKEN:
        raise ValueError("APIFY_API_TOKEN not configured in .env file")

    client = ApifyClient(Config.APIFY_API_TOKEN)

    run_input = {
        "startUrls": [{"url": profile_url}],
    }

    try:
        logger.info(f"Starting Crunchbase scrape for: {profile_url}")

        run = client.actor(ACTOR_ID).call(run_input=run_input)

        profile = None
        raw_item = None

        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            raw_item = item
            logger.debug(f"Raw Crunchbase keys: {list(item.keys())}")
            profile = normalize_crunchbase_data(item, profile_url)
            break

        if not profile:
            logger.warning("No data returned from Apify Crunchbase actor")
            return raw_item or {}

        logger.info(f"Crunchbase scraped: {profile.get('name', 'Unknown')}")
        return profile

    except Exception as e:
        logger.error(f"Error scraping Crunchbase profile: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to scrape Crunchbase profile: {str(e)}")


def print_crunchbase_summary(profile: Dict[str, Any]):
    """Print a readable summary of the scraped Crunchbase profile."""
    print("\n" + "=" * 80)
    print("CRUNCHBASE PROFILE SCRAPED")
    print("=" * 80)

    print(f"\nName:        {profile.get('name', 'N/A')}")
    print(f"Type:        {profile.get('entity_type', 'N/A')}")
    print(f"Title:       {profile.get('title', 'N/A')}")
    print(f"Description: {profile.get('description', 'N/A')}")
    print(f"Website:     {profile.get('website', 'N/A')}")
    print(f"Location:    {profile.get('location', 'N/A')}")

    print(f"\nFunding:")
    print(f"  Total:          ${profile.get('total_funding_usd', 'N/A'):,}" if isinstance(profile.get('total_funding_usd'), (int, float)) else f"  Total:          {profile.get('total_funding_usd', 'N/A')}")
    print(f"  Rounds:         {profile.get('num_funding_rounds', 'N/A')}")
    print(f"  Last Type:      {profile.get('last_funding_type', 'N/A')}")
    print(f"  Last Date:      {profile.get('last_funding_at', 'N/A')}")

    investors = profile.get("investors", [])
    if investors:
        print(f"\nInvestors ({len(investors)}):")
        for inv in investors[:5]:
            name = inv.get("name") or inv.get("investor_identifier", {}).get("value") if isinstance(inv, dict) else str(inv)
            print(f"  - {name}")
        if len(investors) > 5:
            print(f"  ... and {len(investors) - 5} more")

    print(f"\nSocial:")
    print(f"  LinkedIn: {profile.get('linkedin_url', 'N/A')}")
    print(f"  Twitter:  {profile.get('twitter_url', 'N/A')}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Crunchbase Scraper - Test Mode\n")

    if not Config.APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env file")
        exit(1)

    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.crunchbase.com/person/aaron--bird"
    print(f"Scraping: {test_url}")
    print("This may take 30-60 seconds...\n")

    try:
        profile = scrape_crunchbase_profile(test_url)

        if profile:
            print_crunchbase_summary(profile)

            output_file = "crunchbase_profile.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            print(f"\nFull data saved to: {output_file}")
        else:
            print("\nERROR: No data returned")
            exit(1)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
