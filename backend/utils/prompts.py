"""
Prompt Template Loader

Loads prompts from prompts.json for consistent, version-controlled prompt management.
"""
import json
import os
from typing import Dict, Any


class PromptLoader:
    """Load and format prompts from prompts.json"""

    _prompts: Dict[str, Any] = None

    @classmethod
    def _load_prompts(cls):
        """Load prompts from JSON file (cached)"""
        if cls._prompts is None:
            prompts_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'prompts.json'
            )
            with open(prompts_path, 'r', encoding='utf-8') as f:
                cls._prompts = json.load(f)
        return cls._prompts

    @classmethod
    def get(cls, category: str, key: str, **kwargs) -> str:
        """
        Get a prompt template and format it with kwargs.

        Args:
            category: Prompt category (e.g., 'response_synthesis')
            key: Specific prompt key (e.g., 'success', 'failed')
            **kwargs: Variables to format into the prompt

        Returns:
            Formatted prompt string

        Example:
            >>> PromptLoader.get('response_synthesis', 'success',
            ...                  workflow_type='enrichment',
            ...                  outcome_summary='Updated 15 fields',
            ...                  key_results='Name, Email, Company')
        """
        prompts = cls._load_prompts()

        if category not in prompts:
            raise ValueError(f"Prompt category '{category}' not found")

        if key not in prompts[category]:
            raise ValueError(f"Prompt key '{key}' not found in category '{category}'")

        template = prompts[category][key]

        # Format template with provided kwargs
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required variable {e} for prompt {category}.{key}")

    @classmethod
    def get_system(cls, category: str) -> str:
        """Get system prompt for a category"""
        return cls.get(category, 'system')

    @classmethod
    def get_error_explanation(cls, error_type: str) -> str:
        """Get friendly error explanation"""
        prompts = cls._load_prompts()
        return prompts['error_explanations'].get(
            error_type,
            "An unexpected error occurred. Please try again."
        )
