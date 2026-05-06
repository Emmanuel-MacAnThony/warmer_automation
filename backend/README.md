# FastAPI + LangGraph Backend

Production-ready AI backend for LinkedIn enrichment automation.

## Architecture

```
Chrome Extension → FastAPI Server → LangGraph Agent → Tools
                                         ↓
                                    - Apify (LinkedIn scraping)
                                    - Airtable API
                                    - Serper.dev (Google search)
```

## Features

- ✅ **Multi-agent LangGraph system** with tool orchestration
- ✅ **Natural language interface** - chat with the AI
- ✅ **Context-aware** - knows which Airtable record you're viewing
- ✅ **Production guardrails** - validation, error handling, rate limiting
- ✅ **CORS enabled** - works with Chrome extension
- ✅ **Comprehensive logging** - debug and audit trails

## Tools

### 1. scrape_linkedin_profile_tool
Scrapes a LinkedIn profile URL using Apify.

**Guardrails:**
- URL validation
- LinkedIn domain check
- Error handling
- Rate limiting

### 2. enrich_airtable_record_tool
Enriches a specific Airtable record by scraping its LinkedIn URL.

**Guardrails:**
- Record ID validation
- Record existence check
- Safe Airtable updates
- Missing URL handling

### 3. batch_enrich_airtable_tool
Batch processes multiple records.

**Guardrails:**
- Limited concurrency (10 workers)
- Smaller batch sizes (20 per batch)
- Progress tracking
- Per-record error handling

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Verify configuration
python -c "from config import Config; Config.validate()"
```

## Running the Server

```bash
# Development mode (auto-reload)
python backend/server.py

# Or with uvicorn directly
uvicorn backend.server:app --reload --host 0.0.0.0 --port 8000
```

Server will start at: `http://localhost:8000`

## API Endpoints

### GET /health
Health check - verifies all services are configured

```bash
curl http://localhost:8000/health
```

### POST /chat
Main conversational endpoint

```json
{
  "message": "enrich this record",
  "context": {
    "recordId": "recXXXXXXXXXXXXXX",
    "baseId": "appXXXXXXXXXXXXXX"
  }
}
```

### POST /scrape
Direct scraping (bypasses AI)

```json
{
  "context": {
    "recordId": "recXXXXXXXXXXXXXX"
  }
}
```

### POST /batch-enrich
Batch processing

```json
{
  "limit": 10
}
```

## Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you do?"}'
```

## API Documentation

Interactive API docs available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Production Deployment

### Environment Variables
Ensure all required environment variables are set:
- `OPENAI_API_KEY`
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `APIFY_API_TOKEN`
- `SERPAPI_API_KEY`

### Security
- Use HTTPS in production
- Restrict CORS origins
- Add authentication/authorization
- Enable rate limiting
- Monitor logs

### Scaling
- Use process manager (gunicorn, supervisor)
- Deploy behind reverse proxy (nginx)
- Horizontal scaling with load balancer
- Cache frequently accessed data

## Troubleshooting

### "Module not found" errors
```bash
# Make sure you're in the project root
cd c:\Users\USER\twolions\fundraising_automations

# Install dependencies
pip install -r requirements.txt
```

### "Configuration error"
Check your `.env` file has all required keys.

### CORS errors
The server allows all origins by default. In production, update `allow_origins` in `server.py`.
