"""
LLM-based LinkedIn profile matching using OpenAI
"""
import logging
import json
from typing import List, Dict, Tuple
from openai import OpenAI
from backend.config import Config

logger = logging.getLogger(__name__)


class LLMMatcher:
    """LinkedIn profile matcher using OpenAI LLM"""

    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        logger.info(f"LLM matcher initialized with model: {self.model}")

    def rank_linkedin_profiles(
        self,
        contact: Dict,
        candidates: List[Dict],
        max_results: int = 3
    ) -> Tuple[List[str], float]:
        """
        Rank LinkedIn profile candidates using LLM

        Args:
            contact: Contact information dict
            candidates: List of candidate profiles with 'url', 'snippet', 'title'
            max_results: Maximum number of URLs to return

        Returns:
            Tuple of (ranked_urls, confidence_score)
        """
        if not candidates:
            logger.warning("No candidates to rank")
            return [], 0.0

        # Build prompt
        prompt = self._build_ranking_prompt(contact, candidates, max_results)

        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "system",
                    "content": "You are a LinkedIn profile matching assistant. Always respond with valid JSON."
                }, {
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse response
            response_text = response.choices[0].message.content.strip()
            logger.debug(f"LLM response: {response_text}")

            # Extract URLs and confidence
            urls, confidence = self._parse_llm_response(response_text, candidates)

            logger.info(f"LLM ranked {len(urls)} profiles with confidence {confidence:.2f}")
            return urls[:max_results], confidence

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise

    def _build_ranking_prompt(
        self,
        contact: Dict,
        candidates: List[Dict],
        max_results: int
    ) -> str:
        """Build the ranking prompt for Claude"""

        # Format contact info
        contact_info = f"""Name: {contact.get('name', 'Unknown')}
Company: {contact.get('company', 'Not provided')}
Job Title: {contact.get('job_title', 'Not provided')}
Location: {contact.get('location', 'Not provided')}"""

        # Format candidates
        candidate_list = []
        for i, candidate in enumerate(candidates, 1):
            candidate_list.append(
                f"{i}. {candidate['url']}\n   Title: {candidate.get('title', '')}\n   Snippet: {candidate.get('snippet', '')}"
            )
        candidates_text = '\n\n'.join(candidate_list)

        # Build prompt
        prompt = f"""You are matching a person to their correct LinkedIn profile.

Person details:
{contact_info}

Candidate LinkedIn profiles:
{candidates_text}

Task:
- Rank the profiles from most likely to least likely match
- Output the top {max_results} LinkedIn URLs in order of confidence
- Also provide a confidence score between 0 and 1 for the best match

Output format (JSON):
{{
  "urls": ["url1", "url2", "url3"],
  "confidence": 0.92,
  "reasoning": "Brief explanation of why the top match is correct"
}}

Important:
- Focus on company name matches, job title alignment, and location
- If company name appears in snippet/title, that's high confidence
- Common names need stronger secondary signals (company, title, location)
- If no strong match, still rank by best available evidence
- DO NOT hallucinate information not in the snippets
"""

        return prompt

    def _parse_llm_response(
        self,
        response_text: str,
        candidates: List[Dict]
    ) -> Tuple[List[str], float]:
        """
        Parse LLM JSON response

        Returns:
            Tuple of (urls, confidence)
        """
        try:
            # Try to parse as JSON
            data = json.loads(response_text)
            urls = data.get('urls', [])
            confidence = data.get('confidence', 0.5)
            reasoning = data.get('reasoning', '')

            logger.info(f"Match reasoning: {reasoning}")

            # Validate URLs are from candidates
            candidate_urls = {c['url'] for c in candidates}
            valid_urls = [url for url in urls if url in candidate_urls]

            return valid_urls, confidence

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON, attempting fallback")

            # Fallback: extract URLs from text
            urls = []
            for candidate in candidates:
                if candidate['url'] in response_text:
                    urls.append(candidate['url'])

            # Default confidence if parsing fails
            confidence = 0.5 if urls else 0.0

            return urls, confidence


# Standalone test mode
if __name__ == "__main__":
    print("LLM Matcher - Standalone Test Mode\n")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        from backend.config import Config

        # Check if OPENAI_API_KEY is set
        if not Config.OPENAI_API_KEY:
            print("ERROR: OPENAI_API_KEY not set in .env file")
            print("\nGet your OpenAI key from: https://platform.openai.com/api-keys")
            print("Then add to .env: OPENAI_API_KEY=your_key_here")
            exit(1)

        # Initialize matcher
        matcher = LLMMatcher()
        print(f"OK OpenAI client initialized")
        print(f"Model: {Config.OPENAI_MODEL}")
        print(f"API Key: {Config.OPENAI_API_KEY[:8]}...{Config.OPENAI_API_KEY[-4:]}")

        # Test contact
        test_contact = {
            'name': 'Kwek family',
            'company': '',
            'job_title': ''
        }

        # Sample candidates (from SERP test results)
        test_candidates = [
            {
                'url': 'https://uk.linkedin.com/in/kwek-family-7395a0366',
                'title': 'Kwek Family - London Area, United Kingdom',
                'snippet': 'Education: UCL · Location: London Area, United Kingdom. View Kwek Family\'s profile on LinkedIn...'
            },
            {
                'url': 'https://sg.linkedin.com/in/lukelimwj',
                'title': 'Luke Lim - Phillip Securities Pte Ltd',
                'snippet': 'Feb 24, 2017. Investing in Women\'s Healthcare Company. Deepest sympathy for the Kwek Family...'
            },
            {
                'url': 'https://www.linkedin.com/in/chrisyonker',
                'title': 'Chris Yonker, CFBA - Family Business Advisor',
                'snippet': 'What the Kwek Family Feud and a… Jul 29, 2025. What the Kwek Family Feud and a… 3. 1 Comment...'
            }
        ]

        print("\n" + "="*60)
        print("Testing LLM Profile Ranking")
        print("="*60)

        print(f"\nContact: {test_contact['name']}")
        print(f"Candidates: {len(test_candidates)}")

        # Rank profiles
        print(f"\nRanking profiles with {Config.OPENAI_MODEL}...")
        ranked_urls, confidence = matcher.rank_linkedin_profiles(
            test_contact,
            test_candidates,
            max_results=3
        )

        print(f"\n" + "="*60)
        print("LLM Ranking Results")
        print("="*60)
        print(f"\nConfidence: {confidence:.2f}")
        print(f"Top {len(ranked_urls)} matches:\n")

        for i, url in enumerate(ranked_urls, 1):
            # Find the candidate with this URL
            candidate = next((c for c in test_candidates if c['url'] == url), None)
            if candidate:
                print(f"{i}. {url}")
                print(f"   {candidate['title']}")
                print()

        print("="*60)
        print("OK LLM matcher test successful!")
        print("="*60)
        print("\nAll components tested. Ready to run full pipeline!")

        exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
