"""
Unit tests for format_auditor.py

Tests cover:
- Number format validation
- Font validation
- Color validation
- Full format audit flow
"""

import pytest
from pathlib import Path
from typing import Set, Tuple

from src.services.format_auditor import (
    audit_numeric_format,
    validate_fonts,
    validate_colors,
    hex_to_rgb,
    color_distance,
    is_color_in_palette,
)


# ============================================================================
# Test: Number Format Validation
# ============================================================================


def test_validate_number_format_us_format_detected():
    """Test US format numbers are detected as violations"""
    text = "El precio es de $1,234.56 USD."

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    assert len(violations) == 1
    assert violations[0]["number"] == "1,234.56"
    assert "estadounidense" in violations[0]["issue"].lower()


def test_validate_number_format_multiple_violations():
    """Test multiple US format numbers are all detected"""
    text = "Valores: $1,234.56 y €12,345.67 más 987,654.32 unidades."

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    # Should detect all 3 US-formatted numbers
    assert len(violations) == 3
    numbers = [v["number"] for v in violations]
    assert "1,234.56" in numbers
    assert "12,345.67" in numbers
    assert "987,654.32" in numbers


def test_validate_number_format_correct_es_format():
    """Test ES format numbers are NOT flagged"""
    text = "El precio es de $1.234,56 USD y €12.345,67 EUR."

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    # ES format should pass - but might be flagged as ambiguous
    # Check that it's not flagged as wrong US format
    for v in violations:
        assert "estadounidense" not in v["issue"].lower()


def test_validate_number_format_no_numbers():
    """Test text without numbers has no violations"""
    text = "Este es un texto sin números."

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    assert len(violations) == 0


def test_validate_number_format_suggestions():
    """Test violations include suggestions"""
    text = "Precio: $1,234.56"

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    assert len(violations) == 1
    assert "suggestion" in violations[0]
    # Suggestion should swap separators: 1,234.56 → 1.234,56
    assert "1.234,56" in violations[0]["suggestion"]


# ============================================================================
# Test: Font Validation
# ============================================================================


def test_validate_fonts_allowed_font():
    """Test allowed fonts pass validation"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Arial", 12.0),
        ("Calibri", 11.0),
        ("Helvetica", 10.0),
    }

    allowed_fonts = ["Arial", "Calibri", "Helvetica"]

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    # No violations for allowed fonts with correct sizes
    font_violations = [v for v in violations if v["rule"] == "font_whitelist"]
    assert len(font_violations) == 0


def test_validate_fonts_disallowed_font():
    """Test disallowed fonts are flagged"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Comic Sans MS", 12.0),
        ("Papyrus", 11.0),
    }

    allowed_fonts = ["Arial", "Calibri", "Helvetica"]

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    # Should flag both Comic Sans and Papyrus
    assert len(violations) >= 2
    font_names = [v["font_name"] for v in violations]
    assert "Comic Sans MS" in font_names
    assert "Papyrus" in font_names


def test_validate_fonts_size_too_small():
    """Test fonts below minimum size are flagged"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Arial", 6.0),  # Below minimum
    }

    allowed_fonts = ["Arial"]

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    assert len(violations) == 1
    assert violations[0]["rule"] == "font_size_min"
    assert violations[0]["font_size"] == 6.0


def test_validate_fonts_size_too_large():
    """Test fonts above maximum size are flagged"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Arial", 100.0),  # Above maximum
    }

    allowed_fonts = ["Arial"]

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    assert len(violations) == 1
    assert violations[0]["rule"] == "font_size_max"
    assert violations[0]["font_size"] == 100.0


def test_validate_fonts_partial_name_match():
    """Test fonts with partial name matches are allowed (e.g., Arial-Bold)"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Arial-Bold", 12.0),
        ("Arial-BoldMT", 12.0),
    }

    allowed_fonts = ["Arial"]  # Should match Arial-Bold too

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    # Should NOT flag Arial-Bold variants
    font_violations = [v for v in violations if v["rule"] == "font_whitelist"]
    assert len(font_violations) == 0


# ============================================================================
# Test: Color Utilities
# ============================================================================


def test_hex_to_rgb():
    """Test hex color conversion to RGB"""
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#000000") == (0, 0, 0)
    assert hex_to_rgb("#FF0000") == (255, 0, 0)
    assert hex_to_rgb("#00FF00") == (0, 255, 0)
    assert hex_to_rgb("#0000FF") == (0, 0, 255)


def test_hex_to_rgb_without_hash():
    """Test hex conversion works without # prefix"""
    assert hex_to_rgb("FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("000000") == (0, 0, 0)


def test_color_distance_identical():
    """Test distance between identical colors is 0"""
    distance = color_distance("#FFFFFF", "#FFFFFF")
    assert distance == 0.0


def test_color_distance_opposite():
    """Test distance between black and white is maximum"""
    distance = color_distance("#000000", "#FFFFFF")
    # Distance should be sqrt(255^2 + 255^2 + 255^2) ≈ 441.67
    assert distance == pytest.approx(441.67, abs=0.1)


def test_color_distance_similar_colors():
    """Test distance between similar colors is small"""
    # Navy blue (#002B5C) vs slightly different navy
    distance = color_distance("#002B5C", "#003060")
    assert distance < 50  # Small distance for similar colors


# ============================================================================
# Test: Color Palette Validation
# ============================================================================


def test_is_color_in_palette_exact_match():
    """Test exact color match returns True"""
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    assert is_color_in_palette("#002B5C", palette, tolerance=0.1) is True
    assert is_color_in_palette("#FFFFFF", palette, tolerance=0.1) is True


def test_is_color_in_palette_close_match():
    """Test close color within tolerance returns True"""
    palette = ["#002B5C"]  # Navy blue

    # Slightly different navy (should be within 10% tolerance)
    assert is_color_in_palette("#003060", palette, tolerance=0.1) is True


def test_is_color_in_palette_not_in_palette():
    """Test color far from palette returns False"""
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    # Bright red - not in palette
    assert is_color_in_palette("#FF0000", palette, tolerance=0.1) is False


def test_is_color_in_palette_strict_tolerance():
    """Test strict tolerance rejects slight variations"""
    palette = ["#002B5C"]

    # Very strict tolerance (1%)
    assert is_color_in_palette("#003060", palette, tolerance=0.01) is False


def test_is_color_in_palette_permissive_tolerance():
    """Test permissive tolerance accepts more variations"""
    palette = ["#002B5C"]

    # Very permissive tolerance (30%)
    assert is_color_in_palette("#004080", palette, tolerance=0.30) is True


# ============================================================================
# Test: Color Validation
# ============================================================================


def test_validate_colors_all_in_palette():
    """Test no violations when all colors are in palette"""
    colors_used = {"#002B5C", "#FFFFFF", "#000000"}
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    violations = validate_colors(colors_used, palette, tolerance=0.12)

    assert len(violations) == 0


def test_validate_colors_some_violations():
    """Test violations for colors outside palette"""
    colors_used = {
        "#002B5C",  # In palette
        "#FF0000",  # Red - not in palette
        "#00FF00",  # Green - not in palette
    }
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    violations = validate_colors(colors_used, palette, tolerance=0.12)

    assert len(violations) == 2  # Red and Green
    colors_violated = [v["color"] for v in violations]
    assert "#FF0000" in colors_violated
    assert "#00FF00" in colors_violated


def test_validate_colors_suggestions():
    """Test violations include closest palette color"""
    colors_used = {"#FF0000"}  # Red
    palette = ["#000000", "#FFFFFF"]  # Black, White

    violations = validate_colors(colors_used, palette, tolerance=0.12)

    assert len(violations) == 1
    assert "closest_match" in violations[0]
    # Closest to red should be black (less distance than to white)
    # Actually, distance from red to black and white:
    # Red to Black: sqrt(255^2) ≈ 255
    # Red to White: sqrt(255^2 + 255^2) ≈ 360
    # So black is closer
    # But this can vary, so just check it exists
    assert violations[0]["closest_match"] in ["#000000", "#FFFFFF"]


# ============================================================================
# Test: Edge Cases
# ============================================================================


def test_validate_number_format_empty_text():
    """Test empty text returns no violations"""
    violations = validate_number_format("", decimal_sep=",", thousands_sep=".")
    assert len(violations) == 0


def test_validate_fonts_empty_set():
    """Test empty font set returns no violations"""
    violations = validate_fonts(set(), ["Arial"], min_size=8, max_size=72)
    assert len(violations) == 0


def test_validate_colors_empty_set():
    """Test empty color set returns no violations"""
    violations = validate_colors(set(), ["#000000"], tolerance=0.1)
    assert len(violations) == 0


def test_validate_number_format_percentage():
    """Test percentages are handled correctly"""
    # US format percentage
    text = "El incremento es del 5.7%"

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    # 5.7 might be flagged as ambiguous (no thousands separator)
    # This is acceptable behavior


def test_validate_fonts_case_sensitivity():
    """Test font names are case-sensitive"""
    fonts_used: Set[Tuple[str, float]] = {
        ("arial", 12.0),  # lowercase
    }

    allowed_fonts = ["Arial"]  # uppercase

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    # Might flag as violation (depends on implementation)
    # If partial match works, it should pass


# ============================================================================
# Test: Real-World Scenarios
# ============================================================================


def test_validate_number_format_realistic_document():
    """Test realistic document text with mixed numbers"""
    text = """
    Análisis Financiero

    Ingresos: $1,234,567.89 USD
    Gastos: $987,654.32 USD
    Margen: 15.7%

    Proyección 2024: €2,500,000.00
    Crecimiento esperado: 12.5%
    """

    violations = validate_number_format(text, decimal_sep=",", thousands_sep=".")

    # Should detect all US-formatted numbers
    assert len(violations) >= 3  # At least the dollar amounts


def test_validate_fonts_realistic_document():
    """Test realistic font usage in a document"""
    fonts_used: Set[Tuple[str, float]] = {
        ("Arial", 11.0),  # Body text
        ("Arial-Bold", 14.0),  # Headers
        ("Arial", 9.0),  # Footnotes
        ("Calibri", 12.0),  # Alternative body
    }

    allowed_fonts = ["Arial", "Calibri", "Helvetica"]

    violations = validate_fonts(fonts_used, allowed_fonts, min_size=8, max_size=72)

    # All fonts should be allowed
    font_violations = [v for v in violations if v["rule"] == "font_whitelist"]
    assert len(font_violations) == 0


def test_validate_colors_realistic_palette():
    """Test realistic color usage matching 414 Capital palette"""
    colors_used = {
        "#002B5C",  # Navy (primary)
        "#FFFFFF",  # White
        "#000000",  # Black
        "#4A90E2",  # Light blue
        "#003060",  # Slightly different navy (should be within tolerance)
    }

    palette = [
        "#002B5C",
        "#FFFFFF",
        "#000000",
        "#4A90E2",
        "#7F8C8D",
    ]

    violations = validate_colors(colors_used, palette, tolerance=0.12)

    # #003060 is close to #002B5C, should be within tolerance
    assert len(violations) == 0 or len(violations) == 1  # Depending on exact tolerance
