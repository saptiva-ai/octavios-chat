"""
Audit Engine - Core validation logic for COPILOTO_414.

This module contains:
- ValidationCoordinator: Orchestrates all 8 auditors
- PolicyManager: Loads and resolves compliance policies
- Individual auditors in the auditors/ subpackage
"""

from .coordinator import validate_document, validate_document_streaming
from .policy_manager import PolicyManager, PolicyConfig, resolve_policy, get_policy_manager

__all__ = [
    "validate_document",
    "validate_document_streaming",
    "PolicyManager",
    "PolicyConfig",
    "resolve_policy",
    "get_policy_manager",
]
