"""
LLM-based LinkedIn profile matcher.

Given a contact (name, company, title, location) and a list of SERP
candidates (url, snippet, title), ranks them and returns the best URL +
confidence score.
"""
import json
import logging
from typing import Dict, List, Tuple

from openai import OpenAI

from backend.config import Config

logger = logging.getLogger(__name__)


class LLMMatcher:

    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        logger.info(f"LLMMatcher initialized with model: {self.model}")

    def rank_linkedin_profiles(
        self,
        contact: Dict,
        candidates: List[Dict],
        max_results: int = 3,
    ) -> Tuple[List[str], float]:
        """
        Rank LinkedIn profile candidates using an LLM.

        Returns (ranked_urls, confidence_score).
        confidence_score is for the top match only (0.0–1.0).
        """
        if not candidates:
            return [], 0.0

        prompt = self._build_prompt(contact, candidates, max_results)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a LinkedIn profile matching assistant. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        text = response.choices[0].message.content.strip()
        urls, confidence = self._parse_response(text, candidates)
        logger.info(f"LLMMatcher: {len(urls)} match(es), confidence={confidence:.2f}")
        return urls[:max_results], confidence

    def _build_prompt(self, contact: Dict, candidates: List[Dict], max_results: int) -> str:
        contact_info = "\n".join([
            f"Name: {contact.get('name', 'Unknown')}",
            f"Company: {contact.get('company', 'Not provided')}",
            f"Job Title: {contact.get('job_title', 'Not provided')}",
            f"Location: {contact.get('location', 'Not provided')}",
        ])
        candidate_lines = "\n\n".join(
            f"{i}. {c['url']}\n   Title: {c.get('title', '')}\n   Snippet: {c.get('snippet', '')}"
            for i, c in enumerate(candidates, 1)
        )
        return (
            f"Match this person to their correct LinkedIn profile.\n\n"
            f"Person:\n{contact_info}\n\n"
            f"Candidates:\n{candidate_lines}\n\n"
            f"Return the top {max_results} URLs ranked by confidence.\n\n"
            f"Output JSON:\n"
            f'{{"urls": ["url1"], "confidence": 0.92, "reasoning": "brief explanation"}}\n\n'
            f"Rules: prioritise company name + title alignment. "
            f"Common names need strong secondary signals. "
            f"Never hallucinate information not in the snippets."
        )

    def _parse_response(
        self, text: str, candidates: List[Dict]
    ) -> Tuple[List[str], float]:
        candidate_urls = {c["url"] for c in candidates}
        try:
            data = json.loads(text)
            urls = [u for u in data.get("urls", []) if u in candidate_urls]
            confidence = float(data.get("confidence", 0.5))
            logger.info(f"Match reasoning: {data.get('reasoning', '')}")
            return urls, confidence
        except (json.JSONDecodeError, ValueError):
            logger.warning("LLMMatcher: failed to parse JSON response, using fallback")
            urls = [c["url"] for c in candidates if c["url"] in text]
            return urls, 0.5 if urls else 0.0
