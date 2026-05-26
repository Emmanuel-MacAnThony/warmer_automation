"""
Configuration management for LinkedIn enrichment automation
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from backend/.env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


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
    # gpt-4o-mini: cheap, fast — used for structured extraction, scoring, insights.
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # gpt-4o: used for email generation + rewrite where quality matters.
    OPENAI_GENERATION_MODEL = os.getenv("OPENAI_GENERATION_MODEL", "gpt-4o")

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

    # Cost controls
    # Set ENRICH_TWITTER=true to enable Twitter/X scraping (extra Apify call per contact)
    ENRICH_TWITTER: bool = os.getenv("ENRICH_TWITTER", "false").lower() == "true"
    # Set ENRICH_NEWS=true to enable Google News search per contact (uses Serper.dev credits)
    ENRICH_NEWS: bool = os.getenv("ENRICH_NEWS", "false").lower() == "true"
    # Skip re-enrichment: if a contact already has trajectory_chain set, skip it
    SKIP_ALREADY_ENRICHED: bool = os.getenv("SKIP_ALREADY_ENRICHED", "true").lower() == "true"

    # Gmail OAuth
    # GOOGLE_CREDENTIALS_JSON holds EITHER the OAuth client JSON content itself
    # (preferred — keeps the secret out of the repo, set as an env var in prod)
    # OR a path to a credentials file (local-dev convenience). Never commit the file.
    GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    GMAIL_REDIRECT_URI: str = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/auth/gmail/callback")

    # Resend (optional free transactional provider — custom domain / Workspace only)
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "")
    RESEND_FROM_NAME: str = os.getenv("RESEND_FROM_NAME", "")

    @classmethod
    def google_client_config(cls) -> dict:
        """
        Return the Google OAuth client config dict (the full {"web": {...}} object).

        GOOGLE_CREDENTIALS_JSON may be the JSON content itself (env-var deploys)
        or a filesystem path (local dev). Inline JSON keeps the client_secret out
        of the repository.
        """
        raw = (cls.GOOGLE_CREDENTIALS_JSON or "").strip()
        if not raw:
            raise RuntimeError("GOOGLE_CREDENTIALS_JSON not set")
        if raw.startswith("{"):
            return json.loads(raw)
        resolved = Path(raw) if Path(raw).is_absolute() else Path.cwd() / raw
        if not resolved.exists():
            raise RuntimeError(f"Google credentials file not found: {resolved}")
        with open(resolved) as f:
            return json.load(f)

    # Email sending — provider-agnostic
    # EMAIL_PROVIDER: which backend to use for outbound email (gmail | smtp)
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "gmail")
    # Set EMAIL_DRY_RUN=true to log sends without delivering (dev / CI)
    EMAIL_DRY_RUN: bool = os.getenv("EMAIL_DRY_RUN", "false").lower() == "true"
    # SMTP provider settings (used when EMAIL_PROVIDER=smtp)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "")

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
