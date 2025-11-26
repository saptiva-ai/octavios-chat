"""
Capital 414 Private Plugin - Document Compliance Validation MCP Server.

This plugin provides the COPILOTO_414 audit system as a standalone MCP service.
It validates PDF documents against corporate compliance policies using 8 specialized auditors:

1. Disclaimer - Legal disclaimer validation (fuzzy matching)
2. Format - Font and number format compliance
3. Typography - Typography consistency checks
4. Grammar - Spelling and grammar validation (LanguageTool)
5. Logo - Logo detection and placement (OpenCV)
6. Color Palette - Color palette compliance
7. Entity Consistency - Entity consistency validation
8. Semantic Consistency - Semantic coherence analysis

Usage:
    # Start the MCP server
    python -m capital414_private

    # Or via FastMCP CLI
    fastmcp run plugins/capital414-private/src/main.py
"""

__version__ = "1.0.0"
__author__ = "414 Capital"
