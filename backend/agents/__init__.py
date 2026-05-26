"""
AI Agents

  outreach/    — Email generation agent (Generate → Critique → Rewrite ReAct loop)
  segmentation/ — Campaign segmentation agent (LangGraph scoring pipeline)
  enrichment/  — LinkedIn profile matching agent (LLM-ranked SERP candidates)
"""
from backend.agents.outreach import generate_streaming, generate_tier_insight, generate
from backend.agents.segmentation import run_segmentation, register, unregister, get_queue, SENTINEL
from backend.agents.enrichment import LLMMatcher

__all__ = [
    "generate_streaming",
    "generate_tier_insight",
    "generate",
    "run_segmentation",
    "register",
    "unregister",
    "get_queue",
    "SENTINEL",
    "LLMMatcher",
]
