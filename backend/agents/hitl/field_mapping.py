"""
Field Mapping HITL Module

Handles field mapping configuration for LinkedIn → Airtable enrichment.
Uses HITL to get user preferences for which fields to update and how.

Field Type Handling:
- Scalars (str/int/bool): Direct mapping to Airtable fields
- Arrays: Join with commas OR take first item (configurable)
- Objects: Stringify OR extract specific subfield (configurable)

Special Auto-Features (NOT in field mapping):
- peopleAlsoViewed: Automatically generates "Similar Profiles Report" as downloadable
  text/PDF when available. Perfect for fundraising CRM - discover similar donors/prospects
  in the same network without manual work. Report is presented in frontend for download.
"""

import uuid
from typing import Dict, Any, List, Optional
from .core import hitl_core


class FieldMappingHITL:
    """
    HITL module for configuring field mappings.

    Handles:
    - Auto-detection of field mappings
    - User configuration via HITL panel
    - Validation of mapping configuration
    """

    def __init__(self):
        """Initialize field mapping HITL."""
        pass

    async def get_mapping_config(
        self,
        base_id: str,
        table_id: str,
        airtable_fields: List[Dict[str, Any]],
        linkedin_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Get field mapping configuration from user.

        Args:
            base_id: Airtable base ID
            table_id: Airtable table ID
            airtable_fields: List of Airtable field schemas
            linkedin_data: LinkedIn profile data

        Returns:
            Mapping configuration dict or None if cancelled
        """
        # Auto-detect suggested mappings
        suggestions = self._auto_detect_mappings(airtable_fields, linkedin_data)

        # Get available LinkedIn fields
        linkedin_fields = self._extract_linkedin_fields(linkedin_data)

        # Prepare panel data
        panel_data = {
            "base_id": base_id,
            "table_id": table_id,
            "airtable_fields": airtable_fields,
            "linkedin_fields": linkedin_fields,
            "suggestions": suggestions,
        }

        # Generate unique agent ID -> probably encapsulate this in a more custom logic
        agent_id = f"field-mapping-{uuid.uuid4().hex[:8]}"

        # Show HITL panel and wait for user response
        response = await hitl_core.wait_for_user_input(
            agent_id=agent_id,
            panel_type="field_mapping",
            panel_data=panel_data,
            timeout=300,  # 5 minutes
        )

        # Handle response
        if response.get("status") == "confirmed":
            config = response.get("data", {})

            # Validate configuration
            validated = self._validate_mapping(config, airtable_fields)
            return validated
        else:
            # User cancelled or timeout
            return None

    def _auto_detect_mappings(
        self, airtable_fields: List[Dict[str, Any]], linkedin_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Auto-detect field mappings using simple heuristics.

        Args:
            airtable_fields: List of Airtable field schemas
            linkedin_data: LinkedIn profile data

        Returns:
            Dict mapping Airtable field names to suggested LinkedIn fields
        """
        suggestions = {}

        # Get available LinkedIn fields
        linkedin_fields = self._extract_linkedin_fields(linkedin_data)

        for field in airtable_fields:
            field_name = field["name"].lower()
            field_type = field.get("type", "singleLineText")

            # Skip computed/formula fields
            if field_type in ["formula", "rollup", "lookup"]:
                continue

            # Name matching
            if "name" in field_name and "fullName" in linkedin_fields:
                suggestions[field["name"]] = {
                    "source": "fullName",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            elif "company" in field_name and "companyName" in linkedin_fields:
                suggestions[field["name"]] = {
                    "source": "companyName",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            elif (
                any(x in field_name for x in ["title", "role", "position"])
                and "jobTitle" in linkedin_fields
            ):
                suggestions[field["name"]] = {
                    "source": "jobTitle",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            elif "headline" in field_name and "headline" in linkedin_fields:
                suggestions[field["name"]] = {
                    "source": "headline",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            elif "linkedin" in field_name and field_type == "url":
                suggestions[field["name"]] = {
                    "source": "profileUrl",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            elif "location" in field_name and "addressWithCountry" in linkedin_fields:
                suggestions[field["name"]] = {
                    "source": "addressWithCountry",
                    "enabled": True,
                    "overwrite": "empty_only",
                }
            else:
                # No suggestion - user will configure manually if needed
                suggestions[field["name"]] = {
                    "source": None,
                    "enabled": False,
                    "overwrite": "empty_only",
                }

        return suggestions

    def _extract_linkedin_fields(self, linkedin_data: Dict[str, Any]) -> List[str]:
        """
        Extract available field names from LinkedIn data.

        FULLY DYNAMIC: Returns ALL fields present in LinkedIn data,
        letting users decide which ones to map. Different data types
        are handled appropriately during enrichment.

        SPECIAL FIELDS (excluded from mapping):
        - peopleAlsoViewed: Auto-generates downloadable report, not mapped to Airtable

        Args:
            linkedin_data: LinkedIn profile data

        Returns:
            List of available field names (excluding special auto-features)
        """
        fields = []

        # Special fields that are handled automatically, not mapped
        SPECIAL_AUTO_FIELDS = {
            "peopleAlsoViewed"  # Auto-generates similar profiles report for download
        }

        # Extract ALL fields present in the data (fully dynamic)
        for field_name, field_value in linkedin_data.items():
            # Skip special auto-feature fields
            if field_name in SPECIAL_AUTO_FIELDS:
                continue

            # Skip None/empty values
            if field_value is None:
                continue

            # Skip empty strings
            if isinstance(field_value, str) and not field_value.strip():
                continue

            # Skip empty arrays/lists
            if isinstance(field_value, list) and len(field_value) == 0:
                continue

            # Skip empty dicts/objects
            if isinstance(field_value, dict) and len(field_value) == 0:
                continue

            # Include this field - it has actual data
            fields.append(field_name)

        # Sort alphabetically for better UX
        return sorted(fields)

    def _validate_mapping(
        self, config: Dict[str, Any], airtable_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate and sanitize mapping configuration.

        Note: This only validates the mapping structure. Data type transformation
        (arrays → strings, objects → JSON, etc.) happens during enrichment when
        we actually apply the LinkedIn data to Airtable records.

        Args:
            config: User-provided mapping configuration
            airtable_fields: List of Airtable field schemas

        Returns:
            Validated configuration
        """
        validated = {
            "mappings": {},
            "base_id": config.get("base_id"),
            "table_id": config.get("table_id"),
        }

        # Get field names from schema
        valid_field_names = {f["name"] for f in airtable_fields}

        # Validate each mapping
        for field_name, mapping in config.get("mappings", {}).items():
            # Skip if field doesn't exist in schema
            if field_name not in valid_field_names:
                continue

            # Validate mapping structure
            if not isinstance(mapping, dict):
                continue

            # Ensure required keys
            validated_mapping = {
                "source": mapping.get("source"),
                "enabled": bool(mapping.get("enabled", False)),
                "overwrite": mapping.get("overwrite", "empty_only"),
            }

            # Only include if enabled and has source
            if validated_mapping["enabled"] and validated_mapping["source"]:
                validated["mappings"][field_name] = validated_mapping

        return validated


# Global instance
field_mapping_hitl = FieldMappingHITL()
