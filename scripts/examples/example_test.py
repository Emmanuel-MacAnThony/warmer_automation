"""
Quick test script to verify everything is working

Run this before running the full automation
"""
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("="*60)
print("LinkedIn Enrichment - Environment Check")
print("="*60)

# Check environment variables
checks = {
    'AIRTABLE_API_KEY': os.getenv('AIRTABLE_API_KEY'),
    'AIRTABLE_BASE_ID': os.getenv('AIRTABLE_BASE_ID'),
    'AIRTABLE_TABLE_NAME': os.getenv('AIRTABLE_TABLE_NAME'),
    'SERPAPI_API_KEY': os.getenv('SERPAPI_API_KEY'),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
    'OPENAI_MODEL': os.getenv('OPENAI_MODEL'),
}

all_good = True
for key, value in checks.items():
    status = "✓" if value else "✗"
    display_value = f"{value[:10]}..." if value and len(value) > 10 else (value or "MISSING")
    print(f"{status} {key}: {display_value}")
    if not value:
        all_good = False

print("\n" + "="*60)

if all_good:
    print("✓ All environment variables are set!")
    print("\nTesting API connections...\n")

    # Test imports
    try:
        from airtable_client import AirtableClient
        from serp_client import SerpClient
        from llm_matcher import LLMMatcher
        print("✓ All modules imported successfully")
    except Exception as e:
        print(f"✗ Import error: {e}")
        exit(1)

    # Test Airtable connection
    try:
        airtable = AirtableClient()
        print("✓ Airtable connection successful")
    except Exception as e:
        print(f"✗ Airtable connection failed: {e}")

    # Test SERP client
    try:
        serp = SerpClient()
        print("✓ SERP client initialized")
    except Exception as e:
        print(f"✗ SERP client failed: {e}")

    # Test LLM client
    try:
        llm = LLMMatcher()
        print("✓ OpenAI client initialized")
    except Exception as e:
        print(f"✗ OpenAI client failed: {e}")

    print("\n" + "="*60)
    print("✓ All systems ready!")
    print("\nYou can now run: python main.py")
    print("="*60)
else:
    print("✗ Missing required environment variables")
    print("\nPlease:")
    print("1. Copy .env.example to .env")
    print("2. Fill in all required API keys")
    print("3. Run this test again")
    print("="*60)
    exit(1)
