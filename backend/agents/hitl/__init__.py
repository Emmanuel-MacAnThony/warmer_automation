"""
Human-in-the-Loop (HITL) Module

Provides infrastructure for pausing agent execution and waiting for user input.
"""

from .core import HITLCore, hitl_core
from .field_mapping import FieldMappingHITL, field_mapping_hitl

__all__ = ['HITLCore', 'hitl_core', 'FieldMappingHITL', 'field_mapping_hitl']
