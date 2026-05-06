"""
Compare dev_fusion vs harvestapi/linkedin-profile-posts for Matthew Putman.
Saves both raw outputs to data/samples/ so we can inspect what each actor returns.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apify_client import ApifyClient
from backend.config import Config

PROFILE_URL = "https://www.linkedin.com/in/matthew-putman-6a58b112/"

def run_dev_fusion(client: ApifyClient):
    print("\n--- Running dev_fusion/linkedin-profile-scraper ---")
    run = client.actor("dev_fusion/linkedin-profile-scraper").call(
        run_input={"profileUrls": [PROFILE_URL]}
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Items returned: {len(items)}")
    return items[0] if items else {}

def run_harvestapi_profile(client: ApifyClient):
    print("\n--- Running harvestapi/linkedin-profile-scraper ---")
    run = client.actor("harvestapi/linkedin-profile-scraper").call(
        run_input={"urls": [PROFILE_URL], "profileScraperMode": "Profile details"}
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Items returned: {len(items)}")
    return items[0] if items else {}

def run_harvestapi_posts(client: ApifyClient):
    print("\n--- Running harvestapi/linkedin-profile-posts ---")
    run = client.actor("harvestapi/linkedin-profile-posts").call(
        run_input={"profileUrls": [PROFILE_URL], "resultsLimit": 10}
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Posts returned: {len(items)}")
    return items

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    print(f"Saved -> {path}")

if __name__ == "__main__":
    if not Config.APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set")
        sys.exit(1)

    client = ApifyClient(Config.APIFY_API_TOKEN)

    dev_fusion_data = run_dev_fusion(client)
    save("data/samples/matthew_putman_dev_fusion.json", dev_fusion_data)

    # Show updates field immediately
    updates = dev_fusion_data.get("updates", [])
    print(f"\ndev_fusion 'updates' field count: {len(updates)}")
    if updates:
        print("First update keys:", list(updates[0].keys()) if isinstance(updates[0], dict) else type(updates[0]))
        print("First update preview:")
        print(json.dumps(updates[0], indent=2, default=str)[:800])

    harvestapi_profile = run_harvestapi_profile(client)
    save("data/samples/matthew_putman_harvestapi_profile.json", harvestapi_profile)
    print("harvestapi profile top-level keys:", list(harvestapi_profile.keys()))

    harvestapi_posts = run_harvestapi_posts(client)
    save("data/samples/matthew_putman_harvestapi_posts.json", harvestapi_posts)

    if harvestapi_posts:
        print("\nharvestapi posts count:", len(harvestapi_posts))
        print("First post keys:", list(harvestapi_posts[0].keys()))

    print("\nDone. Files:")
    print("  data/samples/matthew_putman_dev_fusion.json")
    print("  data/samples/matthew_putman_harvestapi_profile.json")
    print("  data/samples/matthew_putman_harvestapi_posts.json")
