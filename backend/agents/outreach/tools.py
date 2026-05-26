"""
OpenAI tool schemas for the email generation agent.

Three tool groups:
  _INSPECT_TOOL  — agent calls this first to see CRM field coverage before writing
  _WRITE_TOOLS   — rewrite_subject | rewrite_body | rewrite_both
  _CRITIQUE_TOOL — structured audit: issues, score, must_rewrite flag
"""

from backend.agents.outreach.prompts import QUALITY_THRESHOLD

_INSPECT_TOOL = {
    'type': 'function',
    'function': {
        'name': 'inspect_crm_fields',
        'description': (
            'Inspect available CRM personalization fields and their population rate '
            'across contacts in this tier. '
            'Call this FIRST to decide which slots are safe to use based on data coverage, '
            'before writing the email.'
        ),
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
}

_WRITE_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'rewrite_subject',
            'description': 'Rewrite ONLY the subject line — body stays exactly as-is.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'reasoning': {'type': 'string'},
                    'new_subject': {'type': 'string', 'description': '5-9 words, conversational, no ALL CAPS.'},
                },
                'required': ['reasoning', 'new_subject'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rewrite_body',
            'description': 'Rewrite ONLY the email body — subject stays exactly as-is.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'reasoning': {'type': 'string'},
                    'new_body': {
                        'type': 'string',
                        'description': (
                            'HTML <p> tags. Starts with <p>Hi [first_name],</p>. 2-3 paragraphs. No sign-off. '
                            'Every personalization slot MUST include a fallback: [field | fallback: "natural default"]. '
                            'Example: [company | fallback: "your organization"], [city | fallback: "your area"]. '
                            'Never write bare [field] without a fallback.'
                        ),
                    },
                },
                'required': ['reasoning', 'new_body'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'rewrite_both',
            'description': 'Write or rewrite both subject and body together.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'reasoning': {'type': 'string'},
                    'new_subject': {'type': 'string', 'description': '5-9 words, conversational, no ALL CAPS.'},
                    'new_body': {
                        'type': 'string',
                        'description': (
                            'HTML <p> tags. Starts with <p>Hi [first_name],</p>. 2-3 paragraphs. No sign-off. '
                            'Every personalization slot MUST include a fallback: [field | fallback: "natural default"]. '
                            'Example: [company | fallback: "your organization"], [city | fallback: "your area"]. '
                            'Never write bare [field] without a fallback.'
                        ),
                    },
                },
                'required': ['reasoning', 'new_subject', 'new_body'],
            },
        },
    },
]

_CRITIQUE_TOOL = {
    'type': 'function',
    'function': {
        'name': 'submit_critique',
        'description': 'Submit a structured audit of the draft against the enrichment data.',
        'parameters': {
            'type': 'object',
            'properties': {
                'issues': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Specific, actionable fix instructions citing exact text from the draft '
                        'or exact data from the enrichment context. Empty = draft is strong.'
                    ),
                },
                'score': {
                    'type': 'integer',
                    'minimum': 1,
                    'maximum': 10,
                    'description': '9-10: excellent. 7-8: good. 1-6: significant failures.',
                },
                'must_rewrite': {
                    'type': 'boolean',
                    'description': (
                        f'True if score < {QUALITY_THRESHOLD} OR critical failure: '
                        'goal vague, slots missing, filler phrases, wrong tier tone.'
                    ),
                },
            },
            'required': ['issues', 'score', 'must_rewrite'],
        },
    },
}
