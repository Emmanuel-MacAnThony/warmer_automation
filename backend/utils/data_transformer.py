"""
Data Transformation Utilities

Handles transformation of LinkedIn data to Airtable-compatible formats.
"""
import json
from typing import Any, Dict, List, Optional


class DataTransformer:
    """Transform LinkedIn data to Airtable field types."""

    @staticmethod
    def transform_field(
        value: Any,
        target_field_type: str = "singleLineText"
    ) -> Optional[Any]:
        """
        Transform a LinkedIn field value to Airtable-compatible format.

        Args:
            value: Raw value from LinkedIn data
            target_field_type: Airtable field type (e.g., 'singleLineText', 'url', 'number')

        Returns:
            Transformed value suitable for Airtable, or None if transformation fails
        """
        if value is None:
            return None

        # Handle based on target Airtable field type
        if target_field_type in ["singleLineText", "multilineText", "richText"]:
            return DataTransformer._to_text(value)

        elif target_field_type == "url":
            return DataTransformer._to_url(value)

        elif target_field_type in ["number", "currency", "percent", "duration", "rating"]:
            return DataTransformer._to_number(value)

        elif target_field_type == "checkbox":
            return DataTransformer._to_boolean(value)

        elif target_field_type == "email":
            return DataTransformer._to_email(value)

        elif target_field_type == "phoneNumber":
            return DataTransformer._to_phone(value)

        else:
            # Default: try to convert to text
            return DataTransformer._to_text(value)

    @staticmethod
    def _to_text(value: Any) -> Optional[str]:
        """Convert value to text string."""
        if isinstance(value, str):
            return value.strip() if value.strip() else None

        elif isinstance(value, (int, float, bool)):
            return str(value)

        elif isinstance(value, list):
            # Join array elements with commas
            text_items = [str(item) for item in value if item is not None]
            return ", ".join(text_items) if text_items else None

        elif isinstance(value, dict):
            # For objects, try to extract meaningful text or stringify
            # Check for common patterns
            if "name" in value:
                return str(value["name"])
            elif "title" in value:
                return str(value["title"])
            else:
                # Last resort: JSON stringify
                return json.dumps(value, ensure_ascii=False)

        else:
            return str(value) if value else None

    @staticmethod
    def _to_url(value: Any) -> Optional[str]:
        """Convert value to URL string."""
        if isinstance(value, str):
            url = value.strip()
            # Basic URL validation
            if url and (url.startswith("http://") or url.startswith("https://")):
                return url
            return None

        elif isinstance(value, dict) and "url" in value:
            return DataTransformer._to_url(value["url"])

        return None

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        """Convert value to number."""
        if isinstance(value, (int, float)):
            return float(value)

        elif isinstance(value, str):
            # Try to parse number from string
            try:
                # Remove common number formatting
                cleaned = value.replace(",", "").replace("+", "").strip()
                return float(cleaned)
            except (ValueError, AttributeError):
                return None

        return None

    @staticmethod
    def _to_boolean(value: Any) -> bool:
        """Convert value to boolean."""
        if isinstance(value, bool):
            return value

        elif isinstance(value, str):
            return value.lower() in ["true", "yes", "1", "y"]

        elif isinstance(value, (int, float)):
            return value != 0

        return bool(value)

    @staticmethod
    def _to_email(value: Any) -> Optional[str]:
        """Convert value to email string."""
        if isinstance(value, str):
            email = value.strip()
            # Basic email validation
            if "@" in email and "." in email:
                return email
        return None

    @staticmethod
    def _to_phone(value: Any) -> Optional[str]:
        """Convert value to phone number string."""
        if isinstance(value, str):
            return value.strip() if value.strip() else None
        elif isinstance(value, (int, float)):
            return str(value)
        return None


def apply_field_mapping(
    linkedin_data: Dict[str, Any],
    mapping_config: Dict[str, Any],
    airtable_fields: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Apply field mapping configuration to transform LinkedIn data to Airtable format.

    Args:
        linkedin_data: Raw LinkedIn profile data
        mapping_config: Field mapping configuration from HITL
        airtable_fields: Airtable table schema (field definitions)

    Returns:
        Dictionary of Airtable field updates ready to be sent to API
    """
    updates = {}

    # Build field type lookup
    field_types = {f["name"]: f.get("type", "singleLineText") for f in airtable_fields}

    # Process each mapping
    mappings = mapping_config.get("mappings", {})

    for airtable_field_name, mapping in mappings.items():
        # Get source field from LinkedIn data
        linkedin_field_name = mapping.get("source")
        if not linkedin_field_name or linkedin_field_name not in linkedin_data:
            continue

        # Get raw value
        raw_value = linkedin_data[linkedin_field_name]

        # Get target field type
        field_type = field_types.get(airtable_field_name, "singleLineText")

        # Transform value
        transformed_value = DataTransformer.transform_field(raw_value, field_type)

        # Only include if we got a valid value
        if transformed_value is not None:
            updates[airtable_field_name] = transformed_value

    return updates
