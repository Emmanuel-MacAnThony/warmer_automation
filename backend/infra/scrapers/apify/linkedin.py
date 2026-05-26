"""
Apify LinkedIn scraper — satisfies the LinkedInScraper Protocol.

All ApifyClient usage AND Apify-specific normalization for LinkedIn live here.
If you swap vendors, implement a new class with the same two methods and inject it.
"""
import logging
from typing import Any, Dict, List, Optional

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

_PROFILE_ACTOR = "harvestapi/linkedin-profile-scraper"
_POSTS_ACTOR   = "harvestapi/linkedin-profile-posts"


# ---------------------------------------------------------------------------
# Normalization — translates raw Apify output into a consistent profile dict.
# Handles both actor schemas:
#   harvestapi/linkedin-profile-scraper  (nested objects, current)
#   dev_fusion/linkedin-profile-scraper  (flat field names, legacy)
# ---------------------------------------------------------------------------

def normalize_profile(raw_item: Dict[str, Any], profile_url: str) -> Dict[str, Any]:
    """Normalise a raw Apify actor output dict into a consistent profile shape."""
    loc_obj = raw_item.get('location') or {}
    if isinstance(loc_obj, dict):
        location_str = loc_obj.get('linkedinText') or ''
        parsed       = loc_obj.get('parsed') or {}
        city         = parsed.get('city')    or raw_item.get('city')
        state        = parsed.get('state')   or raw_item.get('state')
        country      = parsed.get('country') or raw_item.get('country')
    else:
        location_str = loc_obj
        city         = raw_item.get('city')
        state        = raw_item.get('state')
        country      = raw_item.get('country')

    emails_raw = raw_item.get('emails') or raw_item.get('email')
    email = (emails_raw[0] if isinstance(emails_raw, list) and emails_raw else emails_raw) or None

    experience = (
        raw_item.get('experience')
        or raw_item.get('experiences')
        or raw_item.get('positions')
        or []
    )

    profile = {
        'profile_url': profile_url,
        'scraped_url': raw_item.get('url') or raw_item.get('linkedinUrl'),

        'full_name':  raw_item.get('fullName') or f"{raw_item.get('firstName', '')} {raw_item.get('lastName', '')}".strip(),
        'first_name': raw_item.get('firstName'),
        'last_name':  raw_item.get('lastName'),
        'headline':   raw_item.get('headline'),
        'summary':    raw_item.get('summary') or raw_item.get('about'),

        'location': location_str or raw_item.get('addressWithCountry'),
        'city':     city,
        'state':    state,
        'country':  country,

        'email':    email,
        'phone':    raw_item.get('phone') or raw_item.get('phoneNumbers'),
        'twitter':  raw_item.get('twitter'),
        'websites': raw_item.get('websites'),

        'current_company': None,
        'current_title':   None,
        'experience':      experience,
        'education':       raw_item.get('education') or raw_item.get('educations') or [],
        'skills':          raw_item.get('skills') or [],
        'languages':       raw_item.get('languages') or [],
        'certifications':  raw_item.get('certifications') or raw_item.get('licenseAndCertificates') or [],
        'volunteer':       raw_item.get('volunteer') or raw_item.get('volunteering') or [],

        'causes': raw_item.get('causes') or [],

        'connections': raw_item.get('connectionsCount') or raw_item.get('connections'),
        'followers':   raw_item.get('followerCount') or raw_item.get('followers') or raw_item.get('followersCount'),

        'premium':      raw_item.get('premium') or raw_item.get('isPremium'),
        'influencer':   raw_item.get('influencer') or raw_item.get('isInfluencer'),
        'open_to_work': raw_item.get('openToWork') or raw_item.get('isJobSeeker'),

        'profile_image':    raw_item.get('profilePicture') or raw_item.get('photo') or raw_item.get('photoUrl'),
        'background_image': raw_item.get('coverPicture') or raw_item.get('backgroundPicture') or raw_item.get('backgroundUrl'),

        'posts':       [],
        'posts_count': 0,

        'raw_data': raw_item,
    }

    if experience:
        current_exp = experience[0]
        profile['current_company'] = current_exp.get('companyName') or current_exp.get('company')
        profile['current_title']   = current_exp.get('position') or current_exp.get('title')

    return profile


# ---------------------------------------------------------------------------
# Apify implementation — satisfies LinkedInScraper Protocol
# ---------------------------------------------------------------------------

class ApifyLinkedInScraper:
    """Fetches raw LinkedIn data via Apify actors."""

    def __init__(self, token: str) -> None:
        self._token = token

    def scrape_raw_profile(self, url: str) -> Dict[str, Any]:
        """Fetch one LinkedIn profile. Returns raw Apify response dict."""
        client = ApifyClient(self._token)
        run = client.actor(_PROFILE_ACTOR).call(
            run_input={
                "urls": [url],
                "profileScraperMode": "Profile details no email ($4 per 1k)",
            }
        )
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            logger.debug(f"LinkedIn raw keys for {url}: {list(item.keys())}")
            return item
        logger.warning(f"No profile data returned from Apify for {url}")
        return {}

    def scrape_raw_posts(self, url: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent posts for one LinkedIn profile. Returns raw post dicts."""
        client = ApifyClient(self._token)
        run = client.actor(_POSTS_ACTOR).call(
            run_input={"profileUrls": [url], "resultsLimit": limit}
        )
        return list(client.dataset(run["defaultDatasetId"]).iterate_items())
