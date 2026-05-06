"""
Batch LinkedIn enrichment with concurrent processing
Writes results to CSV file instead of Airtable
"""
import logging
import csv
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
from config import Config
from airtable_client import AirtableClient
from serp_client import SerpClient
from llm_matcher import LLMMatcher

# Setup logging
import sys

# Configure handlers with proper encoding
file_handler = logging.FileHandler('enrichment_batch.log', encoding='utf-8')
stream_handler = logging.StreamHandler(sys.stdout)

# For Windows console, set encoding to handle Unicode gracefully
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        # Python < 3.7 doesn't have reconfigure
        pass

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)


class BatchEnricher:
    """Concurrent batch enrichment"""

    def __init__(self, output_file='linkedin_results.csv'):
        self.airtable = AirtableClient()
        self.serp = SerpClient()
        self.matcher = LLMMatcher()
        self.output_file = output_file
        logger.info("Batch Enricher initialized")

    def enrich_single_contact(self, contact: Dict) -> Dict:
        """
        Enrich a single contact (thread-safe)

        Returns dict with results
        """
        record_id = contact['record_id']
        name = contact['name']

        result = {
            'record_id': record_id,
            'name': name,
            'company': contact.get('company', ''),
            'job_title': contact.get('job_title', ''),
            'linkedin_found': '',
            'confidence': 0.0,
            'status': 'failed',
            'error': ''
        }

        try:
            logger.info(f"Processing: {name}")

            # Step 1: Search
            candidates = self.serp.search_linkedin_profiles(contact, num_results=10)

            if not candidates:
                result['status'] = 'no_results'
                result['error'] = 'No LinkedIn profiles found'
                return result

            # Step 2: Rank with LLM
            ranked_urls, confidence = self.matcher.rank_linkedin_profiles(
                contact,
                candidates,
                max_results=Config.MAX_LINKEDIN_RESULTS
            )

            if not ranked_urls:
                result['status'] = 'no_match'
                result['error'] = 'LLM could not rank profiles'
                return result

            # Format results
            formatted_urls = []
            for i, url in enumerate(ranked_urls):
                if i == 0:
                    formatted_urls.append(f"{url} ({int(confidence * 100)}%)")
                else:
                    formatted_urls.append(url)

            result['linkedin_found'] = ', '.join(formatted_urls)
            result['confidence'] = round(confidence, 2)
            result['status'] = 'success'

            logger.info(f"OK {name}: Found {len(ranked_urls)} profiles (confidence: {confidence:.2f})")
            return result

        except Exception as e:
            logger.error(f"ERROR {name}: {e}")
            result['error'] = str(e)
            return result

    def process_batch_concurrent(self, contacts: List[Dict], max_workers=50, write_immediately=True) -> List[Dict]:
        """
        Process contacts concurrently using ThreadPoolExecutor

        Args:
            contacts: List of contact dicts
            max_workers: Number of concurrent threads
            write_immediately: If True, write each result to CSV as it completes

        Returns:
            List of results
        """
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_contact = {
                executor.submit(self.enrich_single_contact, contact): contact
                for contact in contacts
            }

            # Collect results as they complete
            for future in as_completed(future_to_contact):
                contact = future_to_contact[future]
                try:
                    result = future.result()
                    results.append(result)

                    # Write to CSV immediately as each result completes
                    if write_immediately:
                        self.write_results_to_csv([result], mode='a')

                except Exception as e:
                    logger.error(f"Task failed for {contact['name']}: {e}")
                    error_result = {
                        'record_id': contact['record_id'],
                        'name': contact['name'],
                        'company': contact.get('company', ''),
                        'job_title': contact.get('job_title', ''),
                        'linkedin_found': '',
                        'confidence': 0.0,
                        'status': 'error',
                        'error': str(e)
                    }
                    results.append(error_result)

                    # Write error result immediately too
                    if write_immediately:
                        self.write_results_to_csv([error_result], mode='a')

        return results

    def write_results_to_csv(self, results: List[Dict], mode='a'):
        """Write results to CSV file"""
        if not results:
            return

        fieldnames = ['record_id', 'name', 'company', 'job_title', 'linkedin_found', 'confidence', 'status', 'error']

        # Check if we need to write header (only for new files or 'w' mode)
        write_header = False
        if mode == 'w':
            write_header = True
        elif mode == 'a':
            try:
                # Check if file exists and has content
                import os
                write_header = not os.path.exists(self.output_file) or os.path.getsize(self.output_file) == 0
            except:
                write_header = True

        with open(self.output_file, mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if write_header:
                writer.writeheader()

            writer.writerows(results)

        # Only log for batches, not single results (reduce log spam)
        if len(results) > 1:
            logger.info(f"Wrote {len(results)} results to {self.output_file}")

    def run_full_batch(self, batch_size=50, max_workers=50, limit=None):
        """
        Process all contacts in batches with concurrency

        Args:
            batch_size: Number of contacts per batch
            max_workers: Number of concurrent threads
            limit: Max total contacts to process (None = all)
        """
        logger.info("="*60)
        logger.info("Starting Concurrent Batch Enrichment")
        logger.info(f"Batch size: {batch_size}")
        logger.info(f"Concurrent workers: {max_workers}")
        logger.info(f"Limit: {limit or 'All records'}")
        logger.info("="*60)

        # Fetch all contacts
        logger.info("Fetching contacts from Airtable...")
        all_contacts = self.airtable.fetch_contacts_to_enrich(limit=limit)

        if not all_contacts:
            logger.info("No contacts to enrich")
            return

        total = len(all_contacts)
        logger.info(f"Found {total} contacts to process")

        # Convert to contact dicts
        contacts = [self.airtable.get_contact_data(record) for record in all_contacts]

        # Initialize CSV file
        self.write_results_to_csv([], mode='w')  # Create with headers

        # Process in batches
        stats = {
            'total': total,
            'success': 0,
            'no_results': 0,
            'no_match': 0,
            'failed': 0
        }

        start_time = time.time()

        for i in range(0, total, batch_size):
            batch = contacts[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing Batch {batch_num}/{total_batches} ({len(batch)} contacts)")
            logger.info(f"{'='*60}")

            # Process batch concurrently (results are written immediately as they complete)
            batch_start = time.time()
            results = self.process_batch_concurrent(batch, max_workers=max_workers, write_immediately=True)
            batch_time = time.time() - batch_start

            # Results already written to CSV as they completed
            logger.info(f"All {len(results)} results from this batch written to {self.output_file}")

            # Update stats
            for result in results:
                status = result['status']
                if status == 'success':
                    stats['success'] += 1
                elif status == 'no_results':
                    stats['no_results'] += 1
                elif status == 'no_match':
                    stats['no_match'] += 1
                else:
                    stats['failed'] += 1

            logger.info(f"Batch completed in {batch_time:.1f}s")
            logger.info(f"Progress: {min(i+batch_size, total)}/{total} ({(min(i+batch_size, total)/total*100):.1f}%)")

            # Rate limiting between batches
            if i + batch_size < total:
                logger.info("Waiting 5s before next batch...")
                time.sleep(5)

        # Final stats
        total_time = time.time() - start_time

        logger.info("\n" + "="*60)
        logger.info("BATCH COMPLETE")
        logger.info("="*60)
        logger.info(f"Total processed: {stats['total']}")
        logger.info(f"OK Success: {stats['success']}")
        logger.info(f"- No results: {stats['no_results']}")
        logger.info(f"- No match: {stats['no_match']}")
        logger.info(f"ERROR Failed: {stats['failed']}")
        logger.info(f"Success rate: {stats['success']/stats['total']*100:.1f}%")
        logger.info(f"Total time: {total_time/60:.1f} minutes")
        logger.info(f"Avg time per contact: {total_time/stats['total']:.1f}s")
        logger.info(f"\nResults saved to: {self.output_file}")
        logger.info("="*60)

        return stats


def main():
    """Main entry point"""
    try:
        # Validate config
        Config.validate()

        # Initialize enricher
        enricher = BatchEnricher(output_file='linkedin_results.csv')

        # Run batch
        # Adjust these parameters:
        # - batch_size: how many to process before writing to file
        # - max_workers: how many concurrent threads
        # - limit: max total to process (None = all)

        stats = enricher.run_full_batch(
            batch_size=50,      # Process 50 at a time
            max_workers=20,     # 20 concurrent threads (adjust based on API limits)
            limit=None          # Process all records (or set a number for testing)
        )

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
