"""
LinkedIn Profile Finder — searches Google via Serper.dev to find LinkedIn profile URLs.

Extracted from the former SerpClient. The news search functionality lives separately
in backend.intelligence.news.client.NewsClient.
"""

import logging
from typing import Dict, List
import requests
from backend.config import Config

logger = logging.getLogger(__name__)


def is_valid_field(value) -> bool:
    """Check if a contact field has an actual usable value (not a placeholder)."""
    if not value:
        return False
    value = value.strip().upper()
    invalid_values = {"N/A", "NA", "NONE", "NULL", "-", "TBD", "UNKNOWN"}
    return value not in invalid_values


def build_search_query(contact: Dict) -> str:
    """
    Build optimized LinkedIn search query using all available contact fields.

    Strategy:
    - Use all non-empty fields (company, job_title, location)
    - Skip fields that are empty, 'N/A', or other placeholder values
    """
    name = contact.get("name", "").strip()
    company = contact.get("company", "").strip()
    job_title = contact.get("job_title", "").strip()
    location = contact.get("location", "").strip()

    if not name or not is_valid_field(name):
        raise ValueError("Name is required for search")

    # Start with base LinkedIn search
    query_parts = [f'site:linkedin.com/in "{name}"']

    # Add all available context fields (only if they have real values)
    if is_valid_field(company):
        query_parts.append(company)
    if is_valid_field(job_title):
        query_parts.append(job_title)
    if is_valid_field(location):
        query_parts.append(location)

    query = " ".join(query_parts)

    logger.debug(f"Search query: {query}")
    logger.debug(
        f"  Using fields - Company: {is_valid_field(company)}, "
        f"Title: {is_valid_field(job_title)}, Location: {is_valid_field(location)}"
    )
    return query


def _filter_linkedin_results(results: List[Dict]) -> List[Dict]:
    """
    Filter and clean search results.

    - Keep only linkedin.com/in/ URLs
    - Exclude /pub/dir/ and other non-profile URLs
    - Deduplicate
    """
    filtered = []
    seen_urls = set()

    for result in results:
        link = result.get("link", "")

        # Must contain linkedin.com/in/
        if "linkedin.com/in/" not in link:
            continue

        # Exclude directory pages
        if "/pub/dir/" in link or "/directory/" in link:
            continue

        # Normalize URL (remove query params and fragments)
        clean_url = link.split("?")[0].split("#")[0].rstrip("/")

        # Deduplicate
        if clean_url in seen_urls:
            continue

        seen_urls.add(clean_url)

        filtered.append(
            {
                "url": clean_url,
                "snippet": result.get("snippet", ""),
                "title": result.get("title", ""),
            }
        )

    return filtered


class LinkedInFinder:
    """Searches for LinkedIn profiles via Serper.dev Google search."""

    BASE_URL = "https://google.serper.dev/search"

    def __init__(self):
        self.api_key = Config.SERPAPI_API_KEY
        logger.info("LinkedInFinder (Serper.dev) initialized")

    def build_search_query(self, contact: Dict) -> str:
        """Build optimized LinkedIn search query. Delegates to module-level function."""
        return build_search_query(contact)

    def search_linkedin_profiles(
        self, contact: Dict, num_results: int = 10
    ) -> List[Dict]:
        """
        Search for LinkedIn profiles via Serper.dev.

        Returns:
            List of search results with 'url', 'snippet', and 'title'.
        """
        query = build_search_query(contact)

        payload = {"q": query, "num": num_results, "gl": "us"}

        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

        try:
            response = requests.post(
                self.BASE_URL, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Extract organic results (Serper.dev format)
            results = data.get("organic", [])

            # Filter and clean results
            linkedin_results = _filter_linkedin_results(results)

            logger.info(
                f"Found {len(linkedin_results)} LinkedIn results for {contact['name']}"
            )
            return linkedin_results

        except requests.RequestException as e:
            logger.error(f"Serper.dev API request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing search results: {e}")
            raise


# ---------------------------------------------------------------------------
# Standalone test mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("LinkedIn Finder - Standalone Test Mode\n")

    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        from backend.config import Config

        if not Config.SERPAPI_API_KEY:
            print("ERROR: SERPAPI_API_KEY not set in .env file")
            exit(1)

        finder = LinkedInFinder()
        print(f"OK LinkedInFinder initialized")

        test_contact = {"name": "Kwek family", "company": "", "job_title": ""}

        query = finder.build_search_query(test_contact)
        print(f"\nSearch Query: {query}")

        results = finder.search_linkedin_profiles(test_contact, num_results=5)
        print(f"\nFiltered LinkedIn profiles: {len(results)}")

        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['url']}")
            snippet = result.get("snippet", "N/A")
            print(f"   Snippet: {snippet[:100]}{'...' if len(snippet) > 100 else ''}")

        exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
