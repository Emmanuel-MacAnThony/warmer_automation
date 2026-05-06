"""
Output Validator - Validate LLM outputs before using them
"""
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class OutputValidator:
    """Validate LLM outputs against Airtable schema"""
    
    # Field types that should be skipped (read-only or complex)
    SKIP_FIELD_TYPES = {
        'formula', 'rollup', 'count', 'lookup', 'createdTime', 'lastModifiedTime',
        'createdBy', 'lastModifiedBy', 'autoNumber', 'barcode', 'button'
    }
    
    # Field types that require special formatting (currently skipped)
    COMPLEX_FIELD_TYPES = {
        'singleSelect', 'multipleSelects', 'multipleRecordLinks',
        'singleCollaborator', 'multipleCollaborators', 'multipleAttachments'
    }
    
    def validate(
        self,
        extracted_fields: Dict[str, Any],
        airtable_schema: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Validate extracted fields against Airtable schema.
        
        Args:
            extracted_fields: Fields extracted by LLM
            airtable_schema: Airtable field definitions
        
        Returns:
            Tuple of (validated_fields, errors)
        """
        validated = {}
        errors = []
        
        # Create field lookup
        schema_lookup = {f['name']: f for f in airtable_schema}
        
        for field_name, value in extracted_fields.items():
            # Check if field exists in schema
            if field_name not in schema_lookup:
                errors.append(f"Field '{field_name}' not found in Airtable schema")
                logger.warning(f"Skipping unknown field: {field_name}")
                continue
            
            field_def = schema_lookup[field_name]
            field_type = field_def.get('type', '')
            
            # Skip read-only and computed fields
            if field_type in self.SKIP_FIELD_TYPES:
                errors.append(f"Field '{field_name}' is read-only ({field_type})")
                logger.info(f"Skipping read-only field: {field_name} ({field_type})")
                continue
            
            # Skip complex field types that need special formatting
            if field_type in self.COMPLEX_FIELD_TYPES:
                errors.append(f"Field '{field_name}' requires special formatting ({field_type})")
                logger.info(f"Skipping complex field: {field_name} ({field_type})")
                continue
            
            # Validate value
            try:
                validated_value = self._validate_value(value, field_type, field_name)
                validated[field_name] = validated_value
            except ValueError as e:
                errors.append(f"Invalid value for '{field_name}': {str(e)}")
                logger.warning(f"Validation error for {field_name}: {e}")
                continue
        
        logger.info(f"Validated {len(validated)}/{len(extracted_fields)} fields ({len(errors)} errors)")
        return validated, errors
    
    def _validate_value(self, value: Any, field_type: str, field_name: str) -> Any:
        """Validate and format value based on field type"""
        
        # Handle null/empty values
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Empty or null value")
        
        # Type-specific validation
        if field_type == 'number':
            try:
                return float(value) if isinstance(value, (int, float, str)) else value
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert to number: {value}")
        
        elif field_type == 'checkbox':
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('true', 'yes', '1', 'checked')
            raise ValueError(f"Cannot convert to checkbox: {value}")
        
        elif field_type in ('email', 'url', 'phoneNumber'):
            # Basic validation - just ensure it's a string
            if not isinstance(value, str):
                raise ValueError(f"Must be a string for {field_type}")
            return value.strip()
        
        elif field_type in ('singleLineText', 'multilineText', 'richText'):
            # Convert to string
            return str(value).strip()
        
        elif field_type == 'date':
            # Should be in ISO format (YYYY-MM-DD)
            if not isinstance(value, str):
                raise ValueError("Date must be a string in YYYY-MM-DD format")
            return value
        
        elif field_type == 'dateTime':
            # Should be in ISO format
            if not isinstance(value, str):
                raise ValueError("DateTime must be a string in ISO format")
            return value
        
        else:
            # For unknown types, pass through as-is
            logger.warning(f"Unknown field type '{field_type}' for field '{field_name}', passing through")
            return value
    
    def filter_null_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out null, empty strings, and 'null' string values"""
        filtered = {}
        for key, value in data.items():
            # Skip if value is None
            if value is None:
                continue
            # Skip if value is empty string or string "null"
            if isinstance(value, str):
                if not value.strip() or value.strip().lower() == 'null':
                    continue
            filtered[key] = value
        return filtered
