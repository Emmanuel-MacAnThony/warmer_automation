"""
Airtable client for fetching and updating contact records
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime
from pyairtable import Api
from backend.config import Config, AIRTABLE_FIELDS

logger = logging.getLogger(__name__)


class AirtableClient:
    """Client for interacting with Airtable"""

    def __init__(self):
        self.api = Api(Config.AIRTABLE_API_KEY)
        self.table = self.api.table(Config.AIRTABLE_BASE_ID, Config.AIRTABLE_TABLE_NAME)
        self.view_name = Config.AIRTABLE_VIEW_NAME
        if self.view_name:
            logger.info(f"Connected to Airtable: {Config.AIRTABLE_TABLE_NAME} (View: {self.view_name})")
        else:
            logger.info(f"Connected to Airtable: {Config.AIRTABLE_TABLE_NAME}")

    def fetch_contacts_to_enrich(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch contacts that need LinkedIn enrichment

        Returns list of records with structure:
        {
            'id': 'rec123',
            'fields': {'Name': 'John Doe', 'Job Title': 'CEO', ...}
        }
        """
        # Formula to filter records without LinkedIn URL
        formula = f"AND({{{AIRTABLE_FIELDS['name']}}} != '', {{{AIRTABLE_FIELDS['linkedin_url']}}} = '')"

        try:
            # Add view parameter if specified
            kwargs = {'formula': formula, 'max_records': limit}
            if self.view_name:
                kwargs['view'] = self.view_name

            records = self.table.all(**kwargs)
            logger.info(f"Fetched {len(records)} contacts to enrich")
            return records
        except Exception as e:
            logger.error(f"Error fetching contacts: {e}")
            raise

    def fetch_record_by_id(self, record_id: str) -> Optional[Dict]:
        """
        Fetch a single record by its ID

        Args:
            record_id: Airtable record ID (e.g., recXXXXXXXXXXXXXX)

        Returns:
            Record dict with 'id' and 'fields', or None if not found
        """
        try:
            record = self.table.get(record_id)
            logger.info(f"Fetched record {record_id}")
            return record
        except Exception as e:
            logger.error(f"Error fetching record {record_id}: {e}")
            return None

    def update_record(self, record_id: str, fields: Dict) -> bool:
        """
        Update a record with new field values

        Args:
            record_id: Airtable record ID
            fields: Dictionary of field names and values to update

        Returns:
            Success status
        """
        if Config.DRY_RUN:
            logger.info(f"[DRY RUN] Would update record {record_id} with fields: {fields}")
            return True

        try:
            self.table.update(record_id, fields)
            logger.info(f"Updated record {record_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating record {record_id}: {e}")
            return False

    def get_contact_data(self, record: Dict) -> Dict:
        """Extract relevant contact data from Airtable record"""
        fields = record.get('fields', {})

        return {
            'record_id': record['id'],
            'name': fields.get(AIRTABLE_FIELDS['name'], ''),
            'job_title': fields.get(AIRTABLE_FIELDS['job_title'], ''),
            'company': fields.get(AIRTABLE_FIELDS['company'], ''),
            'location': fields.get(AIRTABLE_FIELDS['location'], ''),
        }

    def update_linkedin_results(
        self,
        record_id: str,
        linkedin_urls: List[str],
        confidence: float,
        all_candidates: Optional[List[str]] = None
    ) -> bool:
        """
        Update a contact record with LinkedIn enrichment results

        Args:
            record_id: Airtable record ID
            linkedin_urls: Top matched LinkedIn URLs (up to 3)
            confidence: Match confidence score
            all_candidates: All candidate URLs found (for reference)

        Returns:
            Success status
        """
        if Config.DRY_RUN:
            logger.info(f"[DRY RUN] Would update record {record_id}")
            logger.info(f"  LinkedIn URLs: {linkedin_urls}")
            logger.info(f"  Confidence: {confidence}")
            return True

        try:
            update_fields = {
                AIRTABLE_FIELDS['match_source']: 'serp_llm',
                AIRTABLE_FIELDS['last_enriched']: datetime.utcnow().isoformat(),
            }

            # Format LinkedIn field with confidence scores
            if linkedin_urls:
                # First URL gets the confidence score, others don't
                formatted_urls = []
                for i, url in enumerate(linkedin_urls):
                    if i == 0:
                        # Top match with confidence percentage
                        formatted_urls.append(f"{url} ({int(confidence * 100)}%)")
                    else:
                        # Other matches without score
                        formatted_urls.append(url)

                update_fields[AIRTABLE_FIELDS['linkedin_url']] = ', '.join(formatted_urls)

            # Keep all candidates in separate field for reference
            if linkedin_urls:
                update_fields[AIRTABLE_FIELDS['linkedin_candidates']] = ', '.join(linkedin_urls)

            # Add confidence score
            update_fields[AIRTABLE_FIELDS['match_confidence']] = round(confidence, 2)

            # Set enrichment status
            if confidence >= 0.85:
                update_fields[AIRTABLE_FIELDS['enrichment_status']] = 'High Confidence'
            elif confidence >= Config.MATCH_CONFIDENCE_THRESHOLD:
                update_fields[AIRTABLE_FIELDS['enrichment_status']] = 'Review Required'
            else:
                update_fields[AIRTABLE_FIELDS['enrichment_status']] = 'Low Confidence'

            self.table.update(record_id, update_fields)
            logger.info(f"Updated record {record_id} with {len(linkedin_urls)} LinkedIn URLs")
            return True

        except Exception as e:
            logger.error(f"Error updating record {record_id}: {e}")
            return False

    def mark_enrichment_failed(self, record_id: str, reason: str) -> bool:
        """Mark a record as failed enrichment"""
        if Config.DRY_RUN:
            logger.info(f"[DRY RUN] Would mark record {record_id} as failed: {reason}")
            return True

        try:
            update_fields = {
                AIRTABLE_FIELDS['enrichment_status']: f'Failed: {reason}',
                AIRTABLE_FIELDS['last_enriched']: datetime.utcnow().isoformat(),
            }
            self.table.update(record_id, update_fields)
            logger.info(f"Marked record {record_id} as failed")
            return True

        except Exception as e:
            logger.error(f"Error marking record {record_id} as failed: {e}")
            return False

    def get_record(self, base_id: str, table_id: str, record_id: str) -> Optional[Dict]:
        """
        Fetch a single record from any base/table by record id.
        Returns {id, fields} or None if not found.
        """
        try:
            table = self.api.table(base_id, table_id)
            record = table.get(record_id)
            return record
        except Exception as e:
            logger.error(f"Error fetching record {record_id} from {base_id}/{table_id}: {e}")
            return None

    def update_record_in_table(
        self, base_id: str, table_id: str, record_id: str, fields: Dict
    ) -> bool:
        """Update a single record in any base/table by field names."""
        if Config.DRY_RUN:
            logger.info(f"[DRY RUN] Would update {record_id} in {base_id}/{table_id}: {fields}")
            return True
        try:
            table = self.api.table(base_id, table_id)
            table.update(record_id, fields)
            return True
        except Exception as e:
            logger.error(f"Error updating {record_id} in {base_id}/{table_id}: {e}")
            return False

    def batch_update_in_table(
        self, base_id: str, table_id: str, records: List[Dict]
    ) -> int:
        """
        Batch-update records in any base/table.
        records: [{"id": "recXXX", "fields": {...}}, ...]
        Airtable allows max 10 records per request — chunks automatically.
        Returns count of successfully updated records.
        """
        if Config.DRY_RUN:
            logger.info(f"[DRY RUN] Would batch-update {len(records)} records in {base_id}/{table_id}")
            return len(records)

        table = self.api.table(base_id, table_id)
        updated = 0

        # Chunk into groups of 10 (Airtable API limit)
        for i in range(0, len(records), 10):
            chunk = records[i:i + 10]
            try:
                table.batch_update(chunk, typecast=True)
                updated += len(chunk)
            except Exception as e:
                logger.error(
                    f"Error batch-updating chunk {i//10 + 1} in {base_id}/{table_id}: {e}"
                )
                # Continue with remaining chunks — partial success is better than full stop

        logger.info(f"Batch updated {updated}/{len(records)} records in {base_id}/{table_id}")
        return updated

    def get_view_record_ids(self, base_id: str, table_id: str, view_id: str) -> List[str]:
        """
        Fetch all record IDs from a specific view.
        Only retrieves IDs (no field data) to keep it fast.
        """
        try:
            table = self.api.table(base_id, table_id)
            records = table.all(view=view_id, fields=[])
            ids = [r["id"] for r in records]
            logger.info(f"Fetched {len(ids)} record IDs from view {view_id}")
            return ids
        except Exception as e:
            logger.error(f"Error fetching record IDs for {base_id}/{table_id}/{view_id}: {e}")
            raise

    def get_table_schema(self, base_id: str, table_id: str) -> Dict:
        """
        Return field definitions for a given base + table using the Airtable Metadata API.

        Returns:
            {
                "table_id": "tblXXX",
                "table_name": "Contacts",
                "fields": [
                    {"id": "fldXXX", "name": "Full Name", "type": "singleLineText"},
                    ...
                ]
            }
        """
        try:
            base = self.api.base(base_id)
            schema = base.schema()
            table = next((t for t in schema.tables if t.id == table_id), None)
            if not table:
                raise ValueError(f"Table {table_id} not found in base {base_id}")

            def field_options(f):
                opts = getattr(f, 'options', None)
                if opts is None:
                    return None
                choices = getattr(opts, 'choices', None)
                if choices:
                    return {"choices": [{"id": c.id, "name": c.name, "color": getattr(c, 'color', None)} for c in choices]}
                return None

            return {
                "table_id": table.id,
                "table_name": table.name,
                "fields": [
                    {"id": f.id, "name": f.name, "type": f.type, "options": field_options(f)}
                    for f in table.fields
                ]
            }
        except Exception as e:
            logger.error(f"Error fetching schema for {base_id}/{table_id}: {e}")
            raise

    def test_connection(self):
        """Test Airtable connection and show actual columns"""
        try:
            print("\n" + "="*60)
            print("Testing Airtable Connection")
            print("="*60)

            # Show credentials (partially masked)
            api_key = Config.AIRTABLE_API_KEY
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if api_key else "MISSING"
            print(f"\nAPI Key: {masked_key}")
            print(f"Base ID: {Config.AIRTABLE_BASE_ID}")
            print(f"Table: {Config.AIRTABLE_TABLE_NAME}")

            # Try to list tables in base first
            print("\nAttempting to list tables in base...")
            try:
                base = self.api.base(Config.AIRTABLE_BASE_ID)
                tables_info = base.schema()
                print(f"✓ Successfully connected to base!")
                print(f"\nAvailable tables in this base:")
                for i, table in enumerate(tables_info.tables, 1):
                    print(f"  {i}. {table.name} (ID: {table.id})")

                # Check if our table name exists
                table_names = [t.name for t in tables_info.tables]
                if Config.AIRTABLE_TABLE_NAME not in table_names:
                    print(f"\n⚠️  WARNING: '{Config.AIRTABLE_TABLE_NAME}' not found in available tables!")
                    print(f"Available table names: {table_names}")
                    return False
                else:
                    print(f"\n✓ Table '{Config.AIRTABLE_TABLE_NAME}' exists")

            except Exception as e:
                print(f"✗ Could not list tables: {e}")
                print("This might be a permissions issue with your token.")
                return False

            # Count total records first
            view_msg = f" (View: '{Config.AIRTABLE_VIEW_NAME}')" if Config.AIRTABLE_VIEW_NAME else ""
            print(f"\nCounting total records in '{Config.AIRTABLE_TABLE_NAME}'{view_msg}...")

            kwargs_all = {}
            if Config.AIRTABLE_VIEW_NAME:
                kwargs_all['view'] = Config.AIRTABLE_VIEW_NAME
            all_records = self.table.all(**kwargs_all)
            total_count = len(all_records)

            if total_count == 0:
                print("WARNING: View is empty - no records found")
                return False

            print(f"OK Total records in view: {total_count}")

            # Fetch ONLY records that need LinkedIn enrichment using our filtering method
            print(f"\n" + "="*60)
            print("FETCHING RECORDS NEEDING LINKEDIN ENRICHMENT")
            print("="*60)
            print("Using filter: Name != '' AND LinkedIn = ''")

            records_to_enrich = self.fetch_contacts_to_enrich(limit=10)

            if not records_to_enrich:
                print("\nNo records found that need LinkedIn enrichment!")
                print("All records already have LinkedIn URLs.")
                return True

            print(f"\nFound {len(records_to_enrich)} records to enrich (showing first 10)")

            # Display sample records
            print("\n" + "="*60)
            print("SAMPLE RECORDS NEEDING ENRICHMENT:")
            print("="*60)

            for i, record in enumerate(records_to_enrich[:10], 1):
                fields = record.get('fields', {})
                name = fields.get(AIRTABLE_FIELDS['name'], 'N/A')
                company = fields.get(AIRTABLE_FIELDS['company'], 'N/A')
                job_title = fields.get(AIRTABLE_FIELDS['job_title'], 'N/A')
                linkedin = fields.get(AIRTABLE_FIELDS['linkedin_url'], '')

                print(f"\n{i}. {name}")
                print(f"   Company: {company}")
                print(f"   Job Title: {job_title}")
                print(f"   LinkedIn: '{linkedin}' (EMPTY - NEEDS ENRICHMENT)")
                print(f"   Record ID: {record['id']}")

            # Get total count of all records needing enrichment
            print(f"\n" + "="*60)
            print("GETTING TOTAL COUNT OF ALL RECORDS NEEDING ENRICHMENT...")
            print("="*60)
            all_records_to_enrich = self.fetch_contacts_to_enrich(limit=None)
            total_needing_enrichment = len(all_records_to_enrich)

            print(f"\nTotal records in view: {total_count}")
            print(f"Total records NEEDING LinkedIn: {total_needing_enrichment}")
            print(f"Records already WITH LinkedIn: {total_count - total_needing_enrichment}")

            print("\n" + "="*60)
            print("OK Connection successful!")
            print("OK Ready to enrich {0} records!".format(total_needing_enrichment))
            print("="*60)

            return True

        except Exception as e:
            print("\n" + "="*60)
            print("❌ Connection Failed")
            print("="*60)
            print(f"\nError: {e}")
            print("\nCheck:")
            print("  1. AIRTABLE_API_KEY is correct")
            print("  2. AIRTABLE_BASE_ID is correct")
            print("  3. AIRTABLE_TABLE_NAME matches exactly")
            return False


# Standalone test mode
if __name__ == "__main__":
    print("Airtable Client - Standalone Test Mode\n")

    # Setup basic logging for test
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        # Validate config
        from backend.config import Config
        Config.validate()

        # Create client
        client = AirtableClient()

        # Run test
        success = client.test_connection()

        exit(0 if success else 1)

    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\nMake sure you have a .env file with:")
        print("  AIRTABLE_API_KEY=your_key")
        print("  AIRTABLE_BASE_ID=your_base_id")
        print("  AIRTABLE_TABLE_NAME=your_table_name")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
