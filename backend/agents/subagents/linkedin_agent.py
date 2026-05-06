"""
LinkedIn Analysis Agent - Extract and format LinkedIn data for Airtable

This agent specializes in analyzing LinkedIn profile data and extracting
relevant information for Airtable CRM enrichment.
"""
import logging
import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import Config
from backend.agents.prompts.prompt_templates import get_prompt_templates
from backend.agents.guardrails.output_validator import OutputValidator

logger = logging.getLogger(__name__)


class LinkedInAnalyzerAgent:
    """
    Agent specialized in LinkedIn data analysis.
    
    Uses LLM reasoning to intelligently extract and format LinkedIn data
    for Airtable fields, handling complex scenarios like array concatenation,
    nested structures, and field type formatting.
    """
    
    def __init__(self, model: str = "gpt-4o", temperature: float = 0.3):
        """
        Initialize analyzer agent.

        Args:
            model: OpenAI model to use (gpt-4o for better analysis and insights)
            temperature: Temperature for LLM (0.3 for creative but focused analysis)
        """
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=Config.OPENAI_API_KEY
        )
        self.prompts = get_prompt_templates()
        self.validator = OutputValidator()
        logger.info(f"Initialized LinkedInAnalyzerAgent with model={model}")
    
    async def analyze(
        self,
        linkedin_data: Dict[str, Any],
        airtable_fields: List[Dict[str, Any]],
        profile_name: str
    ) -> Dict[str, Any]:
        """
        Analyze LinkedIn data and extract fields for Airtable.
        
        Args:
            linkedin_data: Complete LinkedIn profile data
            airtable_fields: Airtable field definitions
            profile_name: Profile name for context
        
        Returns:
            Dictionary with extracted_fields, validation_errors, and skipped_fields
        """
        try:
            logger.info(f"Analyzing LinkedIn data for {profile_name}")
            
            # Build prompts
            system_prompt = self.prompts.get_system_prompt("linkedin_analyzer")
            analysis_prompt = self.prompts.build_analysis_prompt(
                linkedin_data=linkedin_data,
                airtable_fields=airtable_fields,
                profile_name=profile_name
            )
            
            # Call LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=analysis_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # Parse JSON response
            raw_extracted = self._parse_llm_response(response.content)
            
            # Filter null values
            filtered_extracted = self.validator.filter_null_values(raw_extracted)
            
            # Validate against schema
            validated_fields, validation_errors = self.validator.validate(
                filtered_extracted,
                airtable_fields
            )
            
            logger.info(
                f"LinkedIn analysis complete: {len(validated_fields)} valid fields, "
                f"{len(validation_errors)} errors"
            )
            
            return {
                'extracted_fields': validated_fields,
                'validation_errors': validation_errors,
                'skipped_fields': [
                    field for field in raw_extracted.keys()
                    if field not in validated_fields
                ]
            }
            
        except Exception as e:
            logger.error(f"Error in LinkedIn analysis: {e}", exc_info=True)
            return {
                'extracted_fields': {},
                'validation_errors': [str(e)],
                'skipped_fields': []
            }
    
    def _parse_llm_response(self, response_content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_content:
                start = response_content.find("```json") + 7
                end = response_content.find("```", start)
                json_str = response_content[start:end].strip()
            elif "```" in response_content:
                start = response_content.find("```") + 3
                end = response_content.find("```", start)
                json_str = response_content[start:end].strip()
            else:
                json_str = response_content.strip()
            
            # Parse JSON
            data = json.loads(json_str)
            return data if isinstance(data, dict) else {}
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Response content: {response_content}")
            return {}


# Convenience function for backward compatibility
def analyze_linkedin_for_airtable(
    linkedin_data: Dict[str, Any],
    airtable_fields: List[Dict[str, Any]],
    profile_name: str
) -> Dict[str, Any]:
    """
    Convenience function to analyze LinkedIn data for Airtable enrichment.
    
    Note: This is a synchronous wrapper. For async use LinkedInAnalyzerAgent directly.
    """
    import asyncio
    agent = LinkedInAnalyzerAgent()
    result = asyncio.run(agent.analyze(linkedin_data, airtable_fields, profile_name))
    return result.get('extracted_fields', {})
