"""
Main orchestration script for LinkedIn enrichment automation

This script:
1. Fetches contacts from Airtable that need LinkedIn URLs
2. Searches for LinkedIn profiles via SerpAPI
3. Uses Claude LLM to rank and match profiles
4. Updates Airtable with top 3 matched URLs
"""
import logging
import time
from typing import Dict, List
from config import Config
from airtable_client import AirtableClient
from serp_client import SerpClient
from llm_matcher import LLMMatcher

# Setup logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('enrichment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LinkedInEnricher:
    """Main enrichment orchestrator"""

    def __init__(self):
        self.airtable = AirtableClient()
        self.serp = SerpClient()
        self.matcher = LLMMatcher()
        logger.info("LinkedIn Enricher initialized")

    def enrich_contact(self, contact: Dict) -> bool:
        """
        Enrich a single contact with LinkedIn profile

        Args:
            contact: Contact dict with name, company, job_title, etc.

        Returns:
            Success status
        """
        record_id = contact['record_id']
        name = contact['name']

        logger.info(f"Processing: {name} ({record_id})")

        try:
            # Step 1: Search for LinkedIn profiles via SERP
            logger.info(f"  → Searching LinkedIn profiles...")
            candidates = self.serp.search_linkedin_profiles(contact, num_results=10)

            if not candidates:
                logger.warning(f"  ✗ No LinkedIn profiles found for {name}")
                self.airtable.mark_enrichment_failed(record_id, "No search results")
                return False

            logger.info(f"  → Found {len(candidates)} candidate profiles")

            # Step 2: Rank candidates using LLM
            logger.info(f"  → Ranking profiles with LLM...")
            ranked_urls, confidence = self.matcher.rank_linkedin_profiles(
                contact,
                candidates,
                max_results=Config.MAX_LINKEDIN_RESULTS
            )

            if not ranked_urls:
                logger.warning(f"  ✗ LLM could not rank profiles for {name}")
                self.airtable.mark_enrichment_failed(record_id, "LLM ranking failed")
                return False

            # Check confidence threshold
            if confidence < Config.MATCH_CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"  ⚠ Low confidence ({confidence:.2f}) for {name}, "
                    f"but still updating with top matches"
                )

            # Step 3: Update Airtable
            logger.info(f"  → Updating Airtable...")
            success = self.airtable.update_linkedin_results(
                record_id,
                ranked_urls,
                confidence,
                all_candidates=[c['url'] for c in candidates]
            )

            if success:
                logger.info(f"  ✓ Successfully enriched {name} with {len(ranked_urls)} URLs (confidence: {confidence:.2f})")
                return True
            else:
                logger.error(f"  ✗ Failed to update Airtable for {name}")
                return False

        except Exception as e:
            logger.error(f"  ✗ Error enriching {name}: {e}", exc_info=True)
            self.airtable.mark_enrichment_failed(record_id, f"Error: {str(e)}")
            return False

    def run_batch(self, batch_size: int = None) -> Dict[str, int]:
        """
        Run enrichment on a batch of contacts

        Returns:
            Stats dict with success/failure counts
        """
        batch_size = batch_size or Config.BATCH_SIZE

        logger.info("="*60)
        logger.info("Starting LinkedIn Enrichment Batch")
        logger.info(f"Batch size: {batch_size}")
        logger.info(f"Dry run: {Config.DRY_RUN}")
        logger.info("="*60)

        # Fetch contacts
        logger.info("Fetching contacts from Airtable...")
        records = self.airtable.fetch_contacts_to_enrich(limit=batch_size)

        if not records:
            logger.info("No contacts to enrich. Exiting.")
            return {'total': 0, 'success': 0, 'failed': 0}

        # Process each contact
        stats = {'total': len(records), 'success': 0, 'failed': 0}

        for i, record in enumerate(records, 1):
            logger.info(f"\n[{i}/{stats['total']}] Processing contact...")

            contact = self.airtable.get_contact_data(record)
            success = self.enrich_contact(contact)

            if success:
                stats['success'] += 1
            else:
                stats['failed'] += 1

            # Rate limiting (avoid hitting API limits)
            if i < stats['total']:
                logger.debug("Waiting 2s before next request...")
                time.sleep(2)

        # Print summary
        logger.info("\n" + "="*60)
        logger.info("Batch Complete!")
        logger.info(f"Total: {stats['total']}")
        logger.info(f"Success: {stats['success']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Success rate: {stats['success']/stats['total']*100:.1f}%")
        logger.info("="*60)

        return stats


def main():
    """Main entry point"""
    try:
        # Validate configuration
        Config.validate()

        # Initialize enricher
        enricher = LinkedInEnricher()

        # Run batch
        stats = enricher.run_batch()

        # Exit with appropriate code
        if stats['success'] == stats['total']:
            logger.info("All contacts enriched successfully!")
            return 0
        elif stats['success'] > 0:
            logger.warning("Some contacts failed enrichment")
            return 1
        else:
            logger.error("All contacts failed enrichment")
            return 2

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 3
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 4


if __name__ == '__main__':
    exit(main())
