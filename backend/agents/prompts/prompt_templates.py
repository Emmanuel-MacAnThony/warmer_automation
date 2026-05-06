"""
Prompt Template Management - Load and build prompts from JSON
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class PromptTemplates:
    """Centralized prompt template manager"""
    
    def __init__(self):
        self.prompts_dir = Path(__file__).parent
        self.analysis_prompts = self._load_json("analysis_prompts.json")
        self.hitl_prompts = self._load_json("hitl_prompts.json")
        self.react_prompts = self._load_json("react_prompts.json")
        self.orchestrator_prompts = self._load_json("orchestrator_prompts.json")
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON file from prompts directory"""
        try:
            file_path = self.prompts_dir / filename
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {filename}: {e}")
            return {}
    
    def build_analysis_prompt(
        self,
        linkedin_data: Dict[str, Any],
        airtable_fields: List[Dict[str, Any]],
        profile_name: str
    ) -> str:
        """Build LinkedIn analysis prompt from template"""
        config = self.analysis_prompts.get("linkedin_analysis", {})
        
        # Build field schema
        field_schema_lines = []
        for field in airtable_fields:
            field_name = field.get('name')
            field_type = field.get('type')
            field_desc = field.get('description', '')
            
            line = f"- **{field_name}** (type: {field_type})"
            if field_desc:
                line += f": {field_desc}"
            field_schema_lines.append(line)
        
        field_schema = "\n".join(field_schema_lines)
        
        # Serialize LinkedIn data
        linkedin_json = json.dumps(linkedin_data, indent=2, default=str)
        
        # Build instructions
        instructions = "\n".join([f"{i+1}. {inst}" for i, inst in enumerate(config.get("instructions", []))])
        
        # Build full prompt
        prompt = f"""Analyze this LinkedIn profile data and extract relevant information for the Airtable fields.

**Profile**: {profile_name}

**FULL LinkedIn Data (JSON)**:
```json
{linkedin_json}
```

**Airtable Fields to Populate**:
{field_schema}

**Instructions**:
{instructions}

**Output**: Return ONLY a JSON object with Airtable field names as keys and extracted/formatted values.

Example output:
```json
{{
    "Job Title": "Senior Software Engineer at Acme Corp",
    "Company": "Acme Corp",
    "Email": "john@example.com",
    "Skills": "Python, JavaScript, React",
    "Location": "San Francisco, CA"
}}
```

Now analyze the FULL JSON data above and return the complete mapping:
"""
        return prompt
    
    def get_system_prompt(self, agent_type: str) -> str:
        """Get system prompt for specific agent type"""
        if agent_type == "linkedin_analyzer":
            return self.analysis_prompts.get("linkedin_analysis", {}).get("system", "")
        elif agent_type == "field_matcher":
            return self.analysis_prompts.get("field_matching", {}).get("system", "")
        return ""
    
    def get_hitl_prompt(self, prompt_type: str) -> Dict[str, Any]:
        """Get HITL prompt configuration"""
        return self.hitl_prompts.get(prompt_type, {})

    def build_react_system_prompt(self, tool_descriptions: str) -> str:
        """Build ReAct agent system prompt from template"""
        config = self.react_prompts.get("react_agent", {})

        # Build sections
        sections = []

        # System intro
        sections.append(config.get("system", ""))
        sections.append("")

        # Capabilities
        sections.append(config.get("capabilities_header", ""))
        sections.append(f"\nAvailable tools:\n{tool_descriptions}")
        sections.append("")

        # Context awareness
        ctx = config.get("context_awareness", {})
        if ctx:
            sections.append(ctx.get("header", ""))
            sections.append("")
            sections.append(ctx.get("description", ""))
            sections.append("")
            sections.append(ctx.get("critical_rule", ""))
            sections.append("")
            sections.append(ctx.get("example", ""))
            sections.append("")

        # Security rules
        sec = config.get("security_rules", {})
        if sec:
            sections.append(sec.get("header", ""))
            sections.append("")
            for i, rule in enumerate(sec.get("rules", []), 1):
                sections.append(f"{i}. {rule}")
            sections.append("")

        # Behavioral guidelines
        beh = config.get("behavioral_guidelines", {})
        if beh:
            sections.append(beh.get("header", ""))
            sections.append("")
            for guideline in beh.get("guidelines", []):
                sections.append(f"- {guideline}")
            sections.append("")

        # Unsupported requests
        uns = config.get("unsupported_requests", {})
        if uns:
            sections.append(uns.get("header", ""))
            sections.append("")
            sections.append(uns.get("instructions", ""))
            sections.append("")
            sections.append(uns.get("example", ""))
            sections.append("")

        # Conversation style
        conv = config.get("conversation_style", {})
        if conv:
            sections.append(conv.get("header", ""))
            sections.append("")
            for style in conv.get("styles", []):
                sections.append(f"- {style}")
            sections.append("")

        # Reminder
        sections.append(config.get("reminder", ""))

        return "\n".join(sections)


# Global instance
_prompt_templates = None

def get_prompt_templates() -> PromptTemplates:
    """Get or create prompt templates instance"""
    global _prompt_templates
    if _prompt_templates is None:
        _prompt_templates = PromptTemplates()
    return _prompt_templates
