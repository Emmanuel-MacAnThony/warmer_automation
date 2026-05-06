"""
LinkedIn Profile Scraper using Apify
Scrapes one profile at a time to avoid rate limiting
"""
import logging
import json
from typing import Dict, Any, Optional
from apify_client import ApifyClient
from backend.config import Config

logger = logging.getLogger(__name__)


def preserve_apify_data(raw_item: Dict[str, Any], profile_url: str) -> Dict[str, Any]:
    """
    Normalise raw Apify actor output into a consistent profile dict.

    Handles both actor schemas:
      - dev_fusion/linkedin-profile-scraper  (legacy, flat field names)
      - harvestapi/linkedin-profile-scraper  (current, nested objects, different keys)

    When both actors use the same key the fallback chain is: harvestapi key first,
    then dev_fusion key, so the function works for either without branching.
    """
    # harvestapi returns location as a nested object; dev_fusion returns a plain string
    loc_obj = raw_item.get('location') or {}
    if isinstance(loc_obj, dict):
        location_str = loc_obj.get('linkedinText') or ''
        parsed       = loc_obj.get('parsed') or {}
        city         = parsed.get('city')    or raw_item.get('city')
        state        = parsed.get('state')   or raw_item.get('state')
        country      = parsed.get('country') or raw_item.get('country')
    else:
        location_str = loc_obj  # plain string from dev_fusion
        city         = raw_item.get('city')
        state        = raw_item.get('state')
        country      = raw_item.get('country')

    # harvestapi returns emails as an array; dev_fusion returns a single string
    emails_raw = raw_item.get('emails') or raw_item.get('email')
    email = (emails_raw[0] if isinstance(emails_raw, list) and emails_raw else emails_raw) or None

    # harvestapi uses experience[], dev_fusion uses experiences[] — normalise to one key
    experience = (
        raw_item.get('experience')
        or raw_item.get('experiences')
        or raw_item.get('positions')
        or []
    )

    profile = {
        'profile_url': profile_url,
        'scraped_url': raw_item.get('url') or raw_item.get('linkedinUrl'),

        # Basic Info
        'full_name': raw_item.get('fullName') or f"{raw_item.get('firstName', '')} {raw_item.get('lastName', '')}".strip(),
        'first_name': raw_item.get('firstName'),
        'last_name':  raw_item.get('lastName'),
        'headline':   raw_item.get('headline'),
        'summary':    raw_item.get('summary') or raw_item.get('about'),

        # Location (normalised above)
        'location': location_str or raw_item.get('addressWithCountry'),
        'city':     city,
        'state':    state,
        'country':  country,

        # Contact Info
        'email':    email,
        'phone':    raw_item.get('phone') or raw_item.get('phoneNumbers'),
        'twitter':  raw_item.get('twitter'),
        'websites': raw_item.get('websites'),

        # Professional
        'current_company': None,
        'current_title':   None,
        'experience':      experience,
        'education':       raw_item.get('education') or raw_item.get('educations') or [],
        'skills':          raw_item.get('skills') or [],
        'languages':       raw_item.get('languages') or [],
        'certifications':  raw_item.get('certifications') or raw_item.get('licenseAndCertificates') or [],
        'volunteer':       raw_item.get('volunteer') or raw_item.get('volunteering') or [],

        # harvestapi-only: causes the person publicly supports (philanthropy signal)
        'causes': raw_item.get('causes') or [],

        # Social reach
        # harvestapi: followerCount / connectionsCount
        # dev_fusion: followers / connections / followersCount / connectionsCount
        'connections': (
            raw_item.get('connectionsCount')
            or raw_item.get('connections')
        ),
        'followers': (
            raw_item.get('followerCount')
            or raw_item.get('followers')
            or raw_item.get('followersCount')
        ),

        # Status flags
        # harvestapi: premium (bool), openToWork (bool)
        # dev_fusion: isPremium (bool), isJobSeeker (bool)
        'premium':      raw_item.get('premium') or raw_item.get('isPremium'),
        'influencer':   raw_item.get('influencer') or raw_item.get('isInfluencer'),
        'open_to_work': raw_item.get('openToWork') or raw_item.get('isJobSeeker'),

        # Profile images
        'profile_image':    raw_item.get('profilePicture') or raw_item.get('photo') or raw_item.get('photoUrl'),
        'background_image': raw_item.get('coverPicture')   or raw_item.get('backgroundPicture') or raw_item.get('backgroundUrl'),

        # Posts — populated separately by the harvestapi posts actor call, not from profile raw data
        'posts':       [],
        'posts_count': 0,

        'raw_data': raw_item,
    }

    # Extract current company + title from first experience entry.
    # harvestapi uses 'position' for job title; dev_fusion uses 'title'.
    if experience:
        current_exp = experience[0]
        profile['current_company'] = current_exp.get('companyName') or current_exp.get('company')
        profile['current_title']   = current_exp.get('position') or current_exp.get('title')

    return profile


def enrich_linkedin_profile(linkedin_url: str, base_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich profile with additional data (email, phone)

    For now, this is a placeholder. Can be extended with services like:
    - Hunter.io for email finding
    - Clearbit for company data
    - etc.

    Args:
        linkedin_url: LinkedIn profile URL
        base_profile: Base profile data from scraper

    Returns:
        Enriched profile data
    """
    logger.info("Enrichment placeholder - using base profile data")
    # TODO: Add enrichment services here if needed
    return base_profile


def scrape_linkedin_profile(profile_url: str) -> Dict[str, Any]:
    """
    Scrape LinkedIn profile using Apify - preserve ALL data

    Args:
        profile_url: LinkedIn profile URL to scrape

    Returns:
        Complete profile data dictionary

    Raises:
        ValueError: If APIFY_API_TOKEN not configured
        Exception: If scraping fails
    """
    if not Config.APIFY_API_TOKEN:
        raise ValueError("APIFY_API_TOKEN not configured in .env file")

    client = ApifyClient(Config.APIFY_API_TOKEN)

    run_input = {
        "profileUrls": [profile_url],
    }

    try:
        logger.info(f"Starting LinkedIn scrape for: {profile_url}")

        # Call the Apify actor
        run = client.actor("dev_fusion/linkedin-profile-scraper").call(run_input=run_input)

        # Wait for completion and get results
        profile = None
        raw_item = None

        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            raw_item = item
            logger.debug(f"Raw Apify data keys: {list(item.keys())}")

            # Preserve ALL data from Apify - minimal processing
            profile = preserve_apify_data(item, profile_url)
            break  # Get first result

        if not profile:
            logger.warning("No profile data returned from Apify")
            # Return raw item if processing failed
            if raw_item:
                logger.info("Returning raw Apify data")
                return raw_item
            return {}

        logger.info(f"Profile scraped: {profile.get('full_name', 'Unknown')}")
        logger.debug(f"Profile keys: {list(profile.keys())}")

        # Enrich with email/phone (adds to existing data, doesn't replace)
        try:
            enriched = enrich_linkedin_profile(profile_url, profile)
            logger.info(f"Enrichment completed. Email: {bool(enriched.get('email'))}, Phone: {bool(enriched.get('phone'))}")
            return enriched
        except Exception as e:
            logger.warning(f"Enrichment error (non-fatal): {e}")
            return profile

    except Exception as e:
        logger.error(f"Error scraping LinkedIn profile: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to scrape profile: {str(e)}")


def print_profile_summary(profile: Dict[str, Any]):
    """Print a nice summary of the scraped profile"""
    print("\n" + "="*80)
    print("LINKEDIN PROFILE SCRAPED")
    print("="*80)

    print(f"\nName: {profile.get('full_name', 'N/A')}")
    print(f"Headline: {profile.get('headline', 'N/A')}")
    print(f"Location: {profile.get('location', 'N/A')}")
    print(f"Current Company: {profile.get('current_company', 'N/A')}")
    print(f"Current Title: {profile.get('current_title', 'N/A')}")

    # Contact Info
    print(f"\nContact:")
    print(f"  Email: {profile.get('email', 'N/A')}")
    print(f"  Phone: {profile.get('phone', 'N/A')}")

    # Social
    print(f"\nSocial:")
    print(f"  Connections: {profile.get('connections', 'N/A')}")
    print(f"  Followers: {profile.get('followers', 'N/A')}")

    # Experience
    experience = profile.get('experience', [])
    if experience:
        print(f"\nExperience ({len(experience)} positions):")
        for i, exp in enumerate(experience[:3], 1):  # Show first 3
            company = exp.get('companyName') or exp.get('company', 'Unknown Company')
            title = exp.get('title', 'Unknown Title')
            print(f"  {i}. {title} at {company}")
        if len(experience) > 3:
            print(f"  ... and {len(experience) - 3} more")

    # Education
    education = profile.get('education', [])
    if education:
        print(f"\nEducation ({len(education)} schools):")
        for i, edu in enumerate(education[:2], 1):  # Show first 2
            school = edu.get('schoolName') or edu.get('school', 'Unknown School')
            degree = edu.get('degreeName') or edu.get('degree', '')
            print(f"  {i}. {school} - {degree}")

    # Skills
    skills = profile.get('skills', [])
    if skills:
        skill_names = []
        for s in skills[:10]:
            if isinstance(s, dict):
                name = s.get('name') or s.get('skillName') or 'Unknown'
            else:
                name = str(s)
            skill_names.append(name)
        print(f"\nSkills ({len(skills)} total): {', '.join(skill_names)}")
        if len(skills) > 10:
            print(f"  ... and {len(skills) - 10} more")

    print("\n" + "="*80)


# Standalone test mode
if __name__ == "__main__":
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("LinkedIn Scraper - Test Mode\n")

    # Check for APIFY_API_TOKEN
    if not Config.APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env file")
        print("\nGet your Apify token from: https://console.apify.com/account/integrations")
        print("Then add to .env: APIFY_API_TOKEN=your_token_here")
        exit(1)

    # Get URL from command line or use default test URL
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        # Default test - Satya Nadella (Microsoft CEO)
        test_url = "https://www.linkedin.com/in/satyanadella/"
        print(f"No URL provided, using test profile: {test_url}")

    print(f"\nScraping: {test_url}")
    print("This may take 30-60 seconds...\n")

    try:
        # Scrape the profile
        profile = scrape_linkedin_profile(test_url)

        if profile:
            # Print summary
            print_profile_summary(profile)

            # Optionally save to JSON file
            output_file = "scraped_profile.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)
            print(f"\nFull profile data saved to: {output_file}")
        else:
            print("\nERROR: No profile data returned")
            exit(1)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
