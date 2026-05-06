"""
Configuration management for LinkedIn enrichment automation
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
# __file__ is backend/config.py, so parent.parent gets to project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

# Also try to load from current directory as fallback
load_dotenv()


class Config:
    """Central configuration class"""

    # Airtable settings
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
    AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Contacts")
    AIRTABLE_VIEW_NAME = os.getenv(
        "AIRTABLE_VIEW_NAME", ""
    )  # Optional: filter by specific view

    # SerpAPI settings
    SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

    # OpenAI settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Apify settings
    APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
    APIFY_TOKENS: list = [
        t.strip() for t in os.getenv("APIFY_TOKENS", "").split(",") if t.strip()
    ]
    APIFY_CONCURRENCY_PER_TOKEN: int = int(os.getenv("APIFY_CONCURRENCY_PER_TOKEN", "2"))

    # Batch enrichment
    BATCH_OUTPUT_DIR: str = os.getenv("BATCH_OUTPUT_DIR", "./data/batches")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Script settings
    MAX_LINKEDIN_RESULTS = int(os.getenv("MAX_LINKEDIN_RESULTS", 3))
    MATCH_CONFIDENCE_THRESHOLD = float(os.getenv("MATCH_CONFIDENCE_THRESHOLD", 0.6))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls):
        """Validate required environment variables"""
        required_vars = [
            ("AIRTABLE_API_KEY", cls.AIRTABLE_API_KEY),
            ("AIRTABLE_BASE_ID", cls.AIRTABLE_BASE_ID),
            ("SERPAPI_API_KEY", cls.SERPAPI_API_KEY),
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
        ]

        missing = [var_name for var_name, var_value in required_vars if not var_value]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        return True


# Airtable field mappings (matched to your actual column names)
AIRTABLE_FIELDS = {
    "name": "Name",
    "job_title": "Job Title",
    "company": "Company Name",  # Your column
    "location": "Realtime location",  # Your column
    "linkedin_url": "LinkedIn",  # Your column
    "linkedin_candidates": "LinkedIn Candidates",  # Will be created
    "match_confidence": "Match Confidence",  # Will be created
    "match_source": "Match Source",  # Will be created
    "last_enriched": "Last Enriched",  # Will be created
    "enrichment_status": "Enrichment Status",  # Will be created
}
