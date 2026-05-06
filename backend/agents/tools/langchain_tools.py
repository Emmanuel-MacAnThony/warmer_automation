"""
LangGraph Tools - Production-ready tool implementations

Now uses the multi-agent orchestrator for intelligent LinkedIn enrichment.
"""
import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool

from backend.clients.linkedin_scraper import scrape_linkedin_profile
from backend.clients.airtable_client import AirtableClient
from backend.config import Config, AIRTABLE_FIELDS
from backend.agents.subagents.linkedin_agent import LinkedInAnalyzerAgent
from backend.agents.guardrails.output_validator import OutputValidator

logger = logging.getLogger(__name__)


@tool
def scrape_linkedin_profile_tool(linkedin_url: str) -> Dict[str, Any]:
    """
    Scrape a LinkedIn profile using Apify.

    Args:
        linkedin_url: Full LinkedIn profile URL (e.g., https://linkedin.com/in/username)

    Returns:
        Dictionary with scraped profile data including name, headline, experience, etc.

    Guardrails:
    - Validates URL format
    - Handles API failures gracefully
    - Returns structured error messages
    """
    try:
        # Validate URL
        if not linkedin_url or not linkedin_url.startswith('http'):
            return {
                'success': False,
                'error': 'Invalid LinkedIn URL. Must start with http:// or https://'
            }

        if 'linkedin.com/in/' not in linkedin_url:
            return {
                'success': False,
                'error': 'URL must be a LinkedIn profile (linkedin.com/in/...)'
            }

        logger.info(f"Scraping LinkedIn profile: {linkedin_url}")

        # Scrape the profile
        profile = scrape_linkedin_profile(linkedin_url)

        if not profile:
            return {
                'success': False,
                'error': 'Failed to scrape profile. Profile may be private or does not exist.'
            }

        # Return success with data
        return {
            'success': True,
            'profile': {
                'name': profile.get('full_name'),
                'headline': profile.get('headline'),
                'location': profile.get('location'),
                'current_company': profile.get('current_company'),
                'current_title': profile.get('current_title'),
                'email': profile.get('email'),
                'phone': profile.get('phone'),
                'connections': profile.get('connections'),
                'experience_count': len(profile.get('experience', [])),
                'education_count': len(profile.get('education', [])),
                'skills_count': len(profile.get('skills', []))
            },
            'raw_profile': profile  # Full profile data
        }

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {
            'success': False,
            'error': f'Configuration error: {str(e)}'
        }
    except Exception as e:
        logger.error(f"Error scraping profile: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Scraping failed: {str(e)}'
        }


@tool
async def enrich_airtable_record_tool(
    record_id: str,
    base_id: Optional[str] = None,
    table_name: Optional[str] = None,
    user_approved: bool = False,  # User clicked approve
    edited_fields: Optional[Dict[str, Any]] = None  # User-edited field values from preview
) -> Dict[str, Any]:
    """
    Enrich a specific Airtable record by scraping its LinkedIn profile.

    Uses LLM analysis to intelligently extract and format LinkedIn data for Airtable fields.
    Requires user approval via inline yes/no prompt before writing to Airtable.
    Automatically generates similar profiles report if peopleAlsoViewed is available.

    Args:
        record_id: Airtable record ID (e.g., recXXXXXXXXXXXXXX)
        base_id: Optional Airtable base ID (uses Config.AIRTABLE_BASE_ID if not provided)
        table_name: Optional table name/ID (uses Config.AIRTABLE_TABLE_NAME if not provided)
        user_approved: If True, write to Airtable (set by user clicking "Yes")

    Returns:
        Dictionary with enrichment results and updated record data

    Guardrails:
    - Validates record_id format
    - Checks if record exists
    - Handles missing LinkedIn URL
    - Uses LLM analysis for intelligent data extraction
    - Requires explicit user approval via inline HITL before writing
    """
    try:
        # Validate record_id
        if not record_id or not record_id.startswith('rec'):
            return {
                'success': False,
                'error': 'Invalid record ID. Must start with "rec"'
            }

        # Use config defaults if not provided
        base_id = base_id or Config.AIRTABLE_BASE_ID
        table_name = table_name or Config.AIRTABLE_TABLE_NAME

        if not base_id or not table_name:
            return {
                'success': False,
                'error': 'Airtable Base ID and Table Name not configured'
            }

        logger.info(f"Enriching Airtable record: {record_id} (user_approved={user_approved})")

        # Initialize Airtable client
        airtable = AirtableClient()

        # Fetch the record
        record = airtable.fetch_record_by_id(record_id)

        if not record:
            return {
                'success': False,
                'error': f'Record {record_id} not found'
            }

        fields = record.get('fields', {})
        name = fields.get(AIRTABLE_FIELDS['name'])
        linkedin_url = fields.get(AIRTABLE_FIELDS['linkedin_url'])

        # Check if LinkedIn URL exists
        if not linkedin_url:
            return {
                'success': False,
                'error': f'Record "{name}" does not have a LinkedIn URL',
                'record': {
                    'id': record_id,
                    'name': name
                }
            }

        # Scrape the LinkedIn profile
        scrape_result = scrape_linkedin_profile_tool.invoke({'linkedin_url': linkedin_url})

        if not scrape_result.get('success'):
            return {
                'success': False,
                'error': f"Failed to scrape LinkedIn profile: {scrape_result.get('error')}",
                'record': {
                    'id': record_id,
                    'name': name,
                    'linkedin_url': linkedin_url
                }
            }

        # Extract profile data - use raw_data for complete LinkedIn info
        raw_profile = scrape_result.get('raw_profile', {})
        linkedin_data = raw_profile.get('raw_data', raw_profile)  # Prefer raw_data, fallback to top level

        # Get table schema
        schema_result = get_airtable_schema(base_id, table_name)
        if not schema_result.get('success'):
            return {
                'success': False,
                'error': f"Failed to fetch table schema: {schema_result.get('error')}"
            }

        airtable_fields = schema_result['fields']
        table_id = schema_result['table_id']

        # Import utilities
        from backend.utils.report_generator import generate_and_save_report

        # Use edited fields if provided (from preview modal), otherwise run LLM analysis
        if edited_fields:
            logger.info(f"Using user-edited fields for {name} ({len(edited_fields)} fields)")
            # Still need to validate edited fields
            validator = OutputValidator()
            update_fields, validation_errors = validator.validate(edited_fields, airtable_fields)

            if validation_errors:
                logger.warning(f"Validation errors in edited fields: {validation_errors}")
        else:
            # Use LinkedIn Analyzer Agent for intelligent extraction
            logger.info(f"Running LinkedIn Analyzer Agent for {name}")
            analyzer = LinkedInAnalyzerAgent()
            analysis_result = await analyzer.analyze(
                linkedin_data=linkedin_data,
                airtable_fields=airtable_fields,
                profile_name=name or 'Unknown'
            )

            update_fields = analysis_result.get('extracted_fields', {})
            validation_errors = analysis_result.get('validation_errors', [])

            if not update_fields:
                error_msg = 'LinkedIn analysis failed to extract any valid fields.'
                if validation_errors:
                    error_msg += f' Errors: {", ".join(validation_errors[:3])}'
                return {
                    'success': False,
                    'error': error_msg
                }

        # Validation already done by LinkedInAnalyzerAgent
        # update_fields contains only validated fields
        validated_fields = update_fields

        # Generate peopleAlsoViewed report if available
        similar_profiles_report = None
        if 'peopleAlsoViewed' in linkedin_data and linkedin_data['peopleAlsoViewed']:
            try:
                similar_profiles_report = generate_and_save_report(
                    profile_name=linkedin_data.get('fullName', name or 'Unknown'),
                    profile_title=linkedin_data.get('headline'),
                    people_also_viewed=linkedin_data['peopleAlsoViewed']
                )
                logger.info(f"Generated similar profiles report: {similar_profiles_report['count']} profiles")
            except Exception as e:
                logger.warning(f"Could not generate similar profiles report: {e}")

        # If user hasn't approved yet, return inline approval request with VALIDATED fields
        if not user_approved:
            logger.info(f"Requesting user approval for {len(validated_fields)} field updates")
            return {
                'needs_hitl': True,
                'hitl_type': 'inline_approval',
                'hitl_data': {
                    'record_id': record_id,
                    'record_name': name,
                    'update_fields': validated_fields,  # Use validated fields, not raw LLM output
                    'update_count': len(validated_fields),
                    'similar_profiles_report': similar_profiles_report,
                    'linkedin_data': linkedin_data,
                    'base_id': base_id,
                    'table_id': table_id
                },
                'message': f'Ready to update {len(validated_fields)} fields for {name}. Review and approve?'
            }

        # User approved - write validated fields to Airtable
        try:

            if not validated_fields:
                logger.warning("No valid fields to update after validation")
                return {
                    'success': False,
                    'error': f'No compatible fields to update. Skipped {len(skipped_fields)} fields: {", ".join(skipped_fields)}'
                }

            airtable.update_record(record_id, validated_fields)
            logger.info(f"✅ Updated record {record_id} with {len(validated_fields)} fields")

            return {
                'success': True,
                'record': {
                    'id': record_id,
                    'name': name,
                    'linkedin_url': linkedin_url
                },
                'fields_updated': list(validated_fields.keys()),
                'update_count': len(validated_fields),
                'update_preview': validated_fields,
                'skipped_fields': skipped_fields if skipped_fields else None,
                'profile': scrape_result.get('profile'),
                'similar_profiles_report': similar_profiles_report,
                'message': f'✅ Successfully enriched record for {name} ({len(validated_fields)} fields updated' + (f', {len(skipped_fields)} skipped' if skipped_fields else '') + ')'
            }

        except Exception as e:
            logger.error(f"Could not update record: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Failed to update Airtable record: {str(e)}'
            }

    except Exception as e:
        logger.error(f"Error enriching record: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Enrichment failed: {str(e)}'
        }


@tool
def batch_enrich_airtable_tool(limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Run batch enrichment for all Airtable records without LinkedIn data.

    Args:
        limit: Optional limit on number of records to process

    Returns:
        Dictionary with batch processing statistics

    Guardrails:
    - Limits concurrent processing
    - Progress tracking
    - Error handling per record
    - Safe batch operations
    """
    try:
        logger.info(f"Starting batch enrichment (limit: {limit or 'all'})")

        # Import here to avoid circular dependencies
        from main_batch import BatchEnricher

        # Initialize enricher
        enricher = BatchEnricher(output_file='linkedin_results.csv')

        # Run batch with safeguards
        stats = enricher.run_full_batch(
            batch_size=20,        # Smaller batches for stability
            max_workers=10,       # Limit concurrent threads
            limit=limit           # User-specified limit
        )

        return {
            'success': True,
            'stats': stats,
            'message': f"Batch completed: {stats['success']} successful, {stats['failed']} failed"
        }

    except Exception as e:
        logger.error(f"Batch enrichment error: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Batch enrichment failed: {str(e)}'
        }


def get_airtable_schema(base_id: Optional[str] = None, table_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get Airtable table schema (field definitions).

    Args:
        base_id: Airtable base ID (uses Config.AIRTABLE_BASE_ID if not provided)
        table_name: Table name (uses Config.AIRTABLE_TABLE_NAME if not provided)

    Returns:
        Dict with table schema information including fields list

    Example return:
        {
            'success': True,
            'fields': [
                {'id': 'fld...', 'name': 'Name', 'type': 'singleLineText'},
                {'id': 'fld...', 'name': 'Company', 'type': 'singleLineText'},
                ...
            ]
        }
    """
    try:
        # Use config defaults if not provided
        base_id = base_id or Config.AIRTABLE_BASE_ID
        table_name = table_name or Config.AIRTABLE_TABLE_NAME

        if not base_id or not table_name:
            return {
                'success': False,
                'error': 'Missing base_id or table_name'
            }

        logger.info(f"Fetching schema for {base_id}/{table_name}")

        # Initialize client
        client = AirtableClient()

        # Get table metadata via Airtable API
        # Airtable API endpoint: GET /v0/meta/bases/{baseId}/tables
        import requests

        url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
        headers = {
            "Authorization": f"Bearer {Config.AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Parse response
        data = response.json()

        # Find the specific table (by name OR id)
        tables = data.get('tables', [])
        logger.info(f"Found {len(tables)} tables in base. Looking for: {table_name}")
        logger.info(f"Available tables: {[(t.get('id'), t.get('name')) for t in tables]}")

        target_table = next(
            (t for t in tables if t['name'] == table_name or t['id'] == table_name),
            None
        )

        if not target_table:
            return {
                'success': False,
                'error': f"Table '{table_name}' not found in base. Available: {[t.get('name') for t in tables]}"
            }

        # Extract fields
        fields = target_table.get('fields', [])

        return {
            'success': True,
            'table_id': target_table.get('id'),
            'table_name': target_table.get('name'),
            'fields': fields
        }

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.error(f"Base not found: {base_id}")
            return {
                'success': False,
                'error': 'Base not found. Check AIRTABLE_BASE_ID configuration.'
            }
        else:
            logger.error(f"HTTP error fetching schema: {e}")
            return {
                'success': False,
                'error': f'API error: {str(e)}'
            }
    except Exception as e:
        logger.error(f"Error fetching schema: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Failed to fetch schema: {str(e)}'
        }


# Export tools for LangGraph
TOOLS = [
    scrape_linkedin_profile_tool,
    enrich_airtable_record_tool,
    batch_enrich_airtable_tool
]
