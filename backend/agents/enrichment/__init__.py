"""
Enrichment Agent — LLM-based LinkedIn profile matching.

  matcher.py — ranks SERP candidates against contact data to find the correct LinkedIn URL
"""
from backend.agents.enrichment.matcher import LLMMatcher

__all__ = ["LLMMatcher"]
