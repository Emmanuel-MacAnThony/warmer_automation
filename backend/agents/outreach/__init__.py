"""
Email Generation Agent

Single-pass streamed generation with a deterministic symbolic gate.
Prompts live alongside the agent; context-building helpers live in
backend/outreach/template_generator.py.
"""
from backend.agents.outreach.agent import generate_streaming, generate_tier_insight, generate

__all__ = ["generate_streaming", "generate_tier_insight", "generate"]
