import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from apify_client import ApifyClient
from backend.config import Config

client = ApifyClient(Config.APIFY_API_TOKEN)
print('Running harvestapi/linkedin-profile-scraper...')
run = client.actor('harvestapi/linkedin-profile-scraper').call(
    run_input={
        'urls': ['https://www.linkedin.com/in/matthew-putman-6a58b112/'],
        'profileScraperMode': 'Profile details no email ($4 per 1k)'
    }
)
items = list(client.dataset(run['defaultDatasetId']).iterate_items())
print('Items returned:', len(items))
if items:
    print('Top-level keys:', list(items[0].keys()))
    os.makedirs('data/samples', exist_ok=True)
    with open('data/samples/matthew_putman_harvestapi_profile.json', 'w', encoding='utf-8') as f:
        json.dump(items[0], f, indent=2, default=str, ensure_ascii=False)
    print('Saved -> data/samples/matthew_putman_harvestapi_profile.json')
else:
    print('No items returned')
