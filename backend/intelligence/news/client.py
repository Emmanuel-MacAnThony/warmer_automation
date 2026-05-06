"""
News Client — Google News search via Serper.dev
"""
import logging
from typing import Dict, List

import requests

from backend.config import Config

logger = logging.getLogger(__name__)


class NewsClient:
    """Client for searching Google News via Serper.dev."""

    NEWS_URL = "https://google.serper.dev/news"

    def __init__(self):
        self.api_key = Config.SERPAPI_API_KEY
        logger.info("NewsClient (Serper.dev) initialized")

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
