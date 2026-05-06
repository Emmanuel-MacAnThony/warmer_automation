# LinkedIn Profile Enrichment Automation

Automated LinkedIn profile discovery and matching using SERP search + OpenAI GPT.

## Overview

This system enriches contact records in Airtable by:
1. Searching Google for LinkedIn profiles via SerpAPI
2. Using OpenAI GPT to intelligently rank and match candidates
3. Updating Airtable with top 3 most likely profile URLs

## Features

- **Smart Matching**: LLM-based ranking using name, company, job title, and location
- **Confidence Scoring**: Each match includes a confidence score (0-1)
- **Batch Processing**: Process multiple contacts efficiently with rate limiting
- **Dry Run Mode**: Test without updating Airtable
- **Comprehensive Logging**: Track all operations and results
- **Error Handling**: Graceful failure handling with status tracking

## Setup

### 1. Install Dependencies

```bash
# Activate virtual environment (if not already)
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Mac/Linux

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required API keys:
- **Airtable**: Get from https://airtable.com/account
- **SerpAPI**: Get from https://serpapi.com/dashboard
- **OpenAI**: Get from https://platform.openai.com/api-keys

### 3. Configure Airtable Table

Your Airtable table should have these fields (exact names):

| Field Name | Type | Description |
|------------|------|-------------|
| Name | Single line text | Contact name (required) |
| Job Title | Single line text | Job title/role |
| Company | Single line text | Current company |
| Location | Single line text | Geographic location |
| LinkedIn URL | URL | Primary LinkedIn profile (enriched) |
| LinkedIn Candidates | Long text | All candidate URLs (comma-separated) |
| Match Confidence | Number | Confidence score (0-1) |
| Match Source | Single line text | Source identifier |
| Last Enriched | Date | Last enrichment timestamp |
| Enrichment Status | Single select | Status: High Confidence, Review Required, Low Confidence, Failed |

### 4. Run the Script

**Test run (dry run, no Airtable updates):**
```bash
python main.py
```
Set `DRY_RUN=true` in `.env` for dry run mode.

**Production run:**
```bash
# Set DRY_RUN=false in .env
python main.py
```

## Configuration Options

Edit `.env` to customize:

```env
# Process only 10 contacts per run
BATCH_SIZE=10

# Return up to 3 LinkedIn URLs per contact
MAX_LINKEDIN_RESULTS=3

# Minimum confidence threshold (0-1)
MATCH_CONFIDENCE_THRESHOLD=0.6

# OpenAI model (gpt-4o recommended for best accuracy)
OPENAI_MODEL=gpt-4o

# Logging level
LOG_LEVEL=INFO
```

## How It Works

### Search Strategy

The system builds optimized search queries:

1. **Primary**: `site:linkedin.com/in "Name" Company`
2. **Fallback 1**: `site:linkedin.com/in "Name" Job Title`
3. **Fallback 2**: `site:linkedin.com/in "Name"`

### LLM Matching

OpenAI GPT analyzes candidates considering:
- Company name matches in snippets
- Job title alignment
- Location signals
- Profile completeness indicators

Output format:
```json
{
  "urls": [
    "https://linkedin.com/in/best-match",
    "https://linkedin.com/in/second-best",
    "https://linkedin.com/in/third-best"
  ],
  "confidence": 0.92,
  "reasoning": "Company name appears in snippet, job title matches"
}
```

### Confidence Levels

- **0.85+**: High Confidence (auto-attach)
- **0.60-0.85**: Review Required (human verification recommended)
- **<0.60**: Low Confidence (likely incorrect)

## Output

### Airtable Updates

For each enriched contact:
- `LinkedIn URL`: Best match (first URL)
- `LinkedIn Candidates`: Top 3 URLs (comma-separated)
- `Match Confidence`: Score (0-1)
- `Match Source`: "serp_llm"
- `Enrichment Status`: High Confidence / Review Required / Low Confidence
- `Last Enriched`: Timestamp

### Log File

All operations logged to `enrichment.log`:
```
2026-02-06 10:15:23 - __main__ - INFO - Processing: Ben Huh (rec123)
2026-02-06 10:15:24 - serp_client - INFO - Found 8 candidate profiles
2026-02-06 10:15:26 - llm_matcher - INFO - LLM ranked 3 profiles with confidence 0.92
2026-02-06 10:15:27 - airtable_client - INFO - Updated record rec123
```

## Compliance & Safety

This system:
- ✅ Searches **public search engine indexes** (not scraping LinkedIn)
- ✅ Stores only **LinkedIn URLs** (no profile content)
- ✅ Uses **public SERP data** via official SerpAPI
- ✅ Suitable for **internal CRM enrichment**

Not suitable for:
- ❌ Scraping profile content
- ❌ Data resale
- ❌ High-volume public distribution

## Cost Estimates

Per 100 contacts (approximate):
- **SerpAPI**: ~$0.50 (10 results per search)
- **OpenAI GPT-4o**: ~$0.30 (ranking calls)
- **Total**: ~$0.80 per 100 contacts

To reduce costs, use `gpt-4o-mini` (~$0.02 per 100 contacts) by setting:
```env
OPENAI_MODEL=gpt-4o-mini
```

## Troubleshooting

### No results found
- Check if contact has name filled in Airtable
- Try providing company or job title for better matching
- Verify person has a public LinkedIn profile

### Low confidence scores
- Common names need company/title context
- Check if company name is spelled correctly
- Person may have multiple profiles (job changes)

### API errors
- Verify API keys in `.env`
- Check API rate limits (SerpAPI, OpenAI)
- Review `enrichment.log` for details

## Extending the System

This is designed as a **precursor to more automations**. Easy to extend:

### Add more data sources
```python
# In main.py, add new enrichment methods:
def enrich_contact(self, contact):
    # Existing LinkedIn enrichment
    linkedin_urls = self.enrich_linkedin(contact)

    # Add email enrichment
    email = self.enrich_email(contact)

    # Add company data
    company_data = self.enrich_company(contact)
```

### Schedule periodic runs
```bash
# Use cron (Linux/Mac) or Task Scheduler (Windows)
# Run every day at 9 AM
0 9 * * * cd /path/to/project && python main.py
```

### Add retry logic
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def enrich_contact(self, contact):
    # Your enrichment logic
    pass
```

## Support

For issues or questions:
1. Check `enrichment.log` for detailed error messages
2. Verify all environment variables are set correctly
3. Test with `DRY_RUN=true` first
4. Review Airtable field names match exactly

## License

Internal use only. Not for redistribution.
