"""
SERP API client for LinkedIn profile search
"""
import logging
from typing import List, Dict, Optional
import requests
from urllib.parse import urlencode
from backend.config import Config

logger = logging.getLogger(__name__)


class SerpClient:
    """Client for searching LinkedIn profiles and news via Serper.dev"""

    BASE_URL      = "https://google.serper.dev/search"
    NEWS_URL      = "https://google.serper.dev/news"

    def __init__(self):
        self.api_key = Config.SERPAPI_API_KEY
        logger.info("Serper.dev client initialized")

    def build_search_query(self, contact: Dict) -> str:
        """
        Build optimized LinkedIn search query using all available fields

        Strategy:
        - Use all non-empty fields (company, job_title, location)
        - Skip fields that are empty, 'N/A', or other placeholder values
        """
        def is_valid_field(value):
            """Check if field has actual usable value"""
            if not value:
                return False
            value = value.strip().upper()
            # Common placeholder values to exclude
            invalid_values = ['N/A', 'NA', 'NONE', 'NULL', '-', 'TBD', 'UNKNOWN']
            return value not in invalid_values

        name = contact.get('name', '').strip()
        company = contact.get('company', '').strip()
        job_title = contact.get('job_title', '').strip()
        location = contact.get('location', '').strip()

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

        query = ' '.join(query_parts)

        logger.debug(f"Search query: {query}")
        logger.debug(f"  Using fields - Company: {is_valid_field(company)}, Title: {is_valid_field(job_title)}, Location: {is_valid_field(location)}")
        return query

    def search_linkedin_profiles(self, contact: Dict, num_results: int = 10) -> List[Dict]:
        """
        Search for LinkedIn profiles via Serper.dev

        Returns:
            List of search results with 'link' and 'snippet'
        """
        query = self.build_search_query(contact)

        payload = {
            'q': query,
            'num': num_results,
            'gl': 'us'
        }

        headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract organic results (Serper.dev format)
            results = data.get('organic', [])

            # Filter and clean results
            linkedin_results = self._filter_linkedin_results(results)

            logger.info(f"Found {len(linkedin_results)} LinkedIn results for {contact['name']}")
            return linkedin_results

        except requests.RequestException as e:
            logger.error(f"Serper.dev API request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Error processing search results: {e}")
            raise

    def search_news(self, name: str, company: str = "") -> List[Dict]:
        """
        Search Google News for press mentions of a person.

        Query: '"Full Name" "Company"' or '"Full Name"' if no company.
        Returns raw Serper news result objects (title, snippet, source, date, link).
        Empty list on error — callers should treat no-news as a soft miss.
        """
        if not name:
            return []
        query = f'"{name}"'
        if company:
            query += f' "{company}"'

        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        try:
            response = requests.post(
                self.NEWS_URL,
                json={"q": query, "num": 10, "gl": "us"},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            results = response.json().get("news", [])
            logger.debug(f"News search '{query}': {len(results)} results")
            return results
        except requests.RequestException as e:
            logger.warning(f"News search failed for '{name}': {e}")
            return []

    def _filter_linkedin_results(self, results: List[Dict]) -> List[Dict]:
        """
        Filter and clean search results

        - Keep only linkedin.com/in/ URLs
        - Exclude /pub/dir/ and other non-profile URLs
        - Deduplicate
        """
        filtered = []
        seen_urls = set()

        for result in results:
            link = result.get('link', '')

            # Must contain linkedin.com/in/
            if 'linkedin.com/in/' not in link:
                continue

            # Exclude directory pages
            if '/pub/dir/' in link or '/directory/' in link:
                continue

            # Normalize URL (remove query params and fragments)
            clean_url = link.split('?')[0].split('#')[0].rstrip('/')

            # Deduplicate
            if clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)

            filtered.append({
                'url': clean_url,
                'snippet': result.get('snippet', ''),
                'title': result.get('title', '')
            })

        return filtered


# Standalone test mode
if __name__ == "__main__":
    print("SERP Client - Standalone Test Mode\n")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        from backend.config import Config

        # Check if SERPAPI_API_KEY is set
        if not Config.SERPAPI_API_KEY:
            print("ERROR: SERPAPI_API_KEY not set in .env file")
            print("\nGet your Serper.dev key from: https://serper.dev/dashboard")
            print("Then add to .env: SERPAPI_API_KEY=your_key_here")
            exit(1)

        # Initialize client
        client = SerpClient()
        print(f"OK Serper.dev client initialized")
        print(f"API Key: {Config.SERPAPI_API_KEY[:8]}...{Config.SERPAPI_API_KEY[-4:]}")

        # Test with a sample contact
        print("\n" + "="*60)
        print("Testing LinkedIn Profile Search")
        print("="*60)

        # Test contact
        test_contact = {
            'name': 'Kwek family',
            'company': '',
            'job_title': ''
        }

        print(f"\nTest Contact:")
        print(f"  Name: {test_contact['name']}")
        print(f"  Company: {test_contact['company']}")
        print(f"  Title: {test_contact['job_title']}")

        # Build search query
        query = client.build_search_query(test_contact)
        print(f"\nSearch Query: {query}")

        # Perform search
        print(f"\nSearching Google via Serper.dev...")
        print(f"Requesting 5 results...")

        results = client.search_linkedin_profiles(test_contact, num_results=5)

        print(f"\nRaw results count: {len(results)}")
        print(f"Filtered LinkedIn profiles: {len(results)}")

        if results:
            print("\n" + "="*60)
            print("Top Results:")
            print("="*60)
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result['url']}")
                print(f"   Title: {result.get('title', 'N/A')}")
                snippet = result.get('snippet', 'N/A')
                if len(snippet) > 100:
                    snippet = snippet[:100] + "..."
                print(f"   Snippet: {snippet}")

            print("\n" + "="*60)
            print("OK Serper.dev test successful!")
            print("="*60)
            print("\nYou can now proceed to test the full pipeline.")
        else:
            print("\nWARNING: No results found. This might be:")
            print("  1. Invalid API key")
            print("  2. Out of credits (check: https://serper.dev/dashboard)")
            print("  3. Network issue")

        exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
