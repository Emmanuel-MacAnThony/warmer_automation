# Quick Start Guide

## Get Running in 5 Minutes

### Step 1: Get Your API Keys

1. **Airtable**
   - Go to https://airtable.com/account
   - Click "Generate API key"
   - Copy your API key
   - Get your Base ID: Open your base → Help → API documentation → Copy Base ID

2. **SerpAPI**
   - Sign up at https://serpapi.com/
   - Go to Dashboard: https://serpapi.com/dashboard
   - Copy your API key (100 free searches/month)

3. **OpenAI**
   - Go to https://platform.openai.com/api-keys
   - Click "Create new secret key"
   - Copy the key immediately (you won't see it again)

### Step 2: Configure Environment

Create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and add your keys:

```env
AIRTABLE_API_KEY=your_actual_key_here
AIRTABLE_BASE_ID=your_actual_base_id_here
AIRTABLE_TABLE_NAME=Contacts

SERPAPI_API_KEY=your_actual_serpapi_key_here

OPENAI_API_KEY=your_actual_openai_key_here
OPENAI_MODEL=gpt-4o

MAX_LINKEDIN_RESULTS=3
MATCH_CONFIDENCE_THRESHOLD=0.6
BATCH_SIZE=10
DRY_RUN=true

LOG_LEVEL=INFO
```

### Step 3: Setup Your Airtable

Create these fields in your Airtable table:

**Required Input Fields:**
- Name (Single line text)
- Job Title (Single line text)
- Company (Single line text)
- Location (Single line text)

**Output Fields (will be auto-populated):**
- LinkedIn URL (URL field)
- LinkedIn Candidates (Long text)
- Match Confidence (Number, 0-2 decimals)
- Match Source (Single line text)
- Last Enriched (Date field)
- Enrichment Status (Single select with options: High Confidence, Review Required, Low Confidence, Failed)

### Step 4: Test Run (Dry Run)

```bash
python main.py
```

This will:
- Fetch contacts without LinkedIn URLs
- Search and match profiles
- Show results in the console
- **NOT** update Airtable (DRY_RUN=true)

Check `enrichment.log` for detailed output.

### Step 5: Production Run

Once you're happy with the dry run results:

1. Edit `.env` and set:
   ```env
   DRY_RUN=false
   ```

2. Run again:
   ```bash
   python main.py
   ```

3. Check Airtable - your records should now have LinkedIn URLs!

## Example Output

```
2026-02-06 10:15:23 - __main__ - INFO - Starting LinkedIn Enrichment Batch
2026-02-06 10:15:23 - __main__ - INFO - Batch size: 10
2026-02-06 10:15:23 - __main__ - INFO - Fetching contacts from Airtable...
2026-02-06 10:15:24 - airtable_client - INFO - Fetched 5 contacts to enrich

[1/5] Processing contact...
2026-02-06 10:15:24 - __main__ - INFO - Processing: Ben Huh (rec123)
2026-02-06 10:15:25 - serp_client - INFO - Found 8 LinkedIn results
2026-02-06 10:15:27 - llm_matcher - INFO - LLM ranked 3 profiles with confidence 0.92
2026-02-06 10:15:28 - airtable_client - INFO - Updated record rec123 with 3 LinkedIn URLs
2026-02-06 10:15:28 - __main__ - INFO - ✓ Successfully enriched Ben Huh

============================================================
Batch Complete!
Total: 5
Success: 5
Failed: 0
Success rate: 100.0%
============================================================
```

## Troubleshooting

### "Missing required environment variables"
- Check your `.env` file exists
- Verify all API keys are filled in
- Remove any quotes around the values

### "No contacts to enrich"
- Make sure you have contacts in Airtable
- Check the `LinkedIn URL` field is empty for those contacts
- Verify `AIRTABLE_TABLE_NAME` matches your table name exactly

### "SERP API request failed"
- Check your SerpAPI key is valid
- Verify you have credits remaining (check dashboard)
- Free tier: 100 searches/month

### "OpenAI API error"
- Check your API key is valid
- Verify you have credits in your OpenAI account
- Try switching to `gpt-4o-mini` if you're on free tier

## Cost Management

### Reduce Costs

1. Use GPT-4o-mini instead of GPT-4o:
   ```env
   OPENAI_MODEL=gpt-4o-mini
   ```
   Saves ~90% on LLM costs

2. Process fewer results per search:
   ```env
   MAX_LINKEDIN_RESULTS=1
   ```

3. Batch smaller amounts:
   ```env
   BATCH_SIZE=5
   ```

### Current Costs (Approximate)
- **GPT-4o**: $0.30 per 100 contacts
- **GPT-4o-mini**: $0.02 per 100 contacts
- **SerpAPI**: $0.50 per 100 searches (free tier: 100/month)

## Next Steps

Once this is working:

1. **Schedule Regular Runs**
   - Use Windows Task Scheduler or cron
   - Run daily/weekly to enrich new contacts

2. **Add More Enrichment**
   - Email finding
   - Company data
   - Social profiles

3. **Improve Matching**
   - Adjust confidence thresholds
   - Tweak search queries
   - Add custom filtering logic

4. **Monitor Results**
   - Review "Review Required" contacts manually
   - Track accuracy over time
   - Refine based on false positives

## Support

Questions? Check:
- `enrichment.log` for detailed errors
- `README.md` for full documentation
- Your API dashboards for usage/credits
