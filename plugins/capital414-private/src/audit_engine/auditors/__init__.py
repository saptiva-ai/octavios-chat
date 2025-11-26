"""
Auditors Package - 8 specialized validators for COPILOTO_414.

Each auditor follows the same interface:
    async def audit_*(fragments, config, ...) -> Tuple[List[Finding], Dict[str, Any]]

Returns:
    - List of Finding objects (issues detected)
    - Summary dict with auditor-specific metrics
"""

from .compliance_auditor import audit_disclaimers, load_compliance_config
from .format_auditor import audit_format
from .typography_auditor import audit_typography
from .grammar_auditor import audit_grammar
from .logo_auditor import audit_logo
from .color_palette_auditor import audit_color_palette
from .entity_consistency_auditor import audit_entity_consistency
from .semantic_consistency_auditor import audit_semantic_consistency

__all__ = [
    # Auditor functions
    "audit_disclaimers",
    "audit_format",
    "audit_typography",
    "audit_grammar",
    "audit_logo",
    "audit_color_palette",
    "audit_entity_consistency",
    "audit_semantic_consistency",
    # Config loader
    "load_compliance_config",
]
