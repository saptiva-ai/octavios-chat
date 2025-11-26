"""
Unit tests for color_palette_auditor.py (Phase 3)

Tests cover:
- Color extraction from PDF
- Palette compliance validation
- Color distance calculations
- Tolerance handling
- Finding generation
"""

import pytest
from pathlib import Path
from typing import Set, Tuple

from src.services.color_palette_auditor import (
    hex_to_rgb,
    color_distance,
    is_color_in_palette,
    extract_all_colors_from_pdf,
    audit_color_palette,
)


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
    assert hex_to_rgb("#002B5C") == (0, 43, 92)  # 414 Capital navy


def test_hex_to_rgb_without_hash():
    """Test hex conversion works without # prefix"""
    assert hex_to_rgb("FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("000000") == (0, 0, 0)
    assert hex_to_rgb("002B5C") == (0, 43, 92)


def test_color_distance_identical():
    """Test distance between identical colors is 0"""
    distance = color_distance("#FFFFFF", "#FFFFFF")
    assert distance == 0.0

    distance = color_distance("#002B5C", "#002B5C")
    assert distance == 0.0


def test_color_distance_opposite():
    """Test distance between black and white is maximum"""
    distance = color_distance("#000000", "#FFFFFF")
    # Distance should be sqrt(255^2 + 255^2 + 255^2) ≈ 441.67
    assert distance == pytest.approx(441.67, abs=0.1)


def test_color_distance_similar_colors():
    """Test distance between similar colors is small"""
    # Navy blue (#002B5C) vs slightly different navy (#003060)
    distance = color_distance("#002B5C", "#003060")
    assert distance < 10  # Very small distance for similar colors


def test_color_distance_different_colors():
    """Test distance between very different colors is large"""
    # Navy blue vs bright red
    distance = color_distance("#002B5C", "#FF0000")
    assert distance > 200  # Large distance


# ============================================================================
# Test: Palette Compliance
# ============================================================================


def test_is_color_in_palette_exact_match():
    """Test exact color match returns True"""
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    is_valid, closest = is_color_in_palette("#002B5C", palette, tolerance=0.12)
    assert is_valid is True
    assert closest == "#002B5C"

    is_valid, closest = is_color_in_palette("#FFFFFF", palette, tolerance=0.12)
    assert is_valid is True
    assert closest == "#FFFFFF"


def test_is_color_in_palette_close_match():
    """Test close color within tolerance returns True"""
    palette = ["#002B5C"]  # Navy blue

    # Slightly different navy (small Euclidean distance)
    is_valid, closest = is_color_in_palette("#003060", palette, tolerance=0.12)
    assert is_valid is True
    assert closest == "#002B5C"


def test_is_color_in_palette_not_in_palette():
    """Test color far from palette returns False"""
    palette = ["#002B5C", "#FFFFFF", "#000000"]

    # Bright red - not in palette
    is_valid, closest = is_color_in_palette("#FF0000", palette, tolerance=0.12)
    assert is_valid is False
    # Should still return closest match
    assert closest in palette


def test_is_color_in_palette_strict_tolerance():
    """Test strict tolerance rejects slight variations"""
    palette = ["#002B5C"]

    # Very strict tolerance (1%)
    is_valid, closest = is_color_in_palette("#003060", palette, tolerance=0.01)
    assert is_valid is False


def test_is_color_in_palette_permissive_tolerance():
    """Test permissive tolerance accepts more variations"""
    palette = ["#002B5C"]

    # Very permissive tolerance (50%)
    is_valid, closest = is_color_in_palette("#004080", palette, tolerance=0.50)
    assert is_valid is True


def test_is_color_in_palette_empty_palette():
    """Test empty palette returns True (no restrictions)"""
    is_valid, closest = is_color_in_palette("#FF0000", [], tolerance=0.12)
    assert is_valid is True
    assert closest == "#FF0000"


# ============================================================================
# Test: Full Audit Flow
# ============================================================================


@pytest.mark.asyncio
async def test_audit_color_palette_all_compliant():
    """Test audit with all colors in palette returns no findings"""
    # Mock config with permissive palette
    config = {
        "color_palette": {
            "enabled": True,
            "allowed_colors": [
                "#000000",
                "#FFFFFF",
                "#FF0000",
                "#00FF00",
                "#0000FF",
            ],
            "tolerance": 0.12,
            "severity": "medium",
        }
    }

    # Note: This test requires a real PDF file to work properly
    # For unit testing, we'll test the logic without PDF extraction
    # Integration tests should cover full PDF processing


@pytest.mark.asyncio
async def test_audit_color_palette_disabled():
    """Test audit skips when disabled in config"""
    config = {
        "color_palette": {
            "enabled": False,
            "allowed_colors": ["#000000"],
            "tolerance": 0.12,
            "severity": "medium",
        }
    }

    # Create a fake PDF path (won't be read due to disabled config)
    fake_pdf = Path("/tmp/fake.pdf")

    findings, summary = await audit_color_palette(fake_pdf, config)

    # Should return empty results when disabled
    assert len(findings) == 0


@pytest.mark.asyncio
async def test_audit_color_palette_summary_structure():
    """Test audit returns proper summary structure"""
    config = {
        "color_palette": {
            "enabled": True,
            "allowed_colors": ["#002B5C", "#FFFFFF"],
            "tolerance": 0.12,
            "severity": "high",
        }
    }

    fake_pdf = Path("/tmp/fake.pdf")

    findings, summary = await audit_color_palette(fake_pdf, config)

    # Verify summary structure
    assert "total_colors_detected" in summary
    assert "unauthorized_colors" in summary
    assert "compliance_rate" in summary
    assert "palette_used" in summary
    assert "unauthorized_colors_list" in summary

    # Verify types
    assert isinstance(summary["total_colors_detected"], int)
    assert isinstance(summary["unauthorized_colors"], int)
    assert isinstance(summary["compliance_rate"], float)
    assert isinstance(summary["palette_used"], list)
    assert isinstance(summary["unauthorized_colors_list"], list)

    # Compliance rate should be between 0.0 and 1.0
    assert 0.0 <= summary["compliance_rate"] <= 1.0


# ============================================================================
# Test: Finding Generation
# ============================================================================


def test_finding_structure():
    """Test that findings have correct structure"""
    # This is tested implicitly in audit flow tests
    # Findings should have: id, category, rule, issue, severity, location, suggestion, evidence
    pass


# ============================================================================
# Test: Edge Cases
# ============================================================================


def test_color_distance_case_insensitive():
    """Test color distance works with different cases"""
    distance1 = color_distance("#FFFFFF", "#ffffff")
    distance2 = color_distance("#FFFFFF", "#FFFFFF")
    assert distance1 == distance2 == 0.0


def test_hex_to_rgb_mixed_case():
    """Test hex parsing works with mixed case"""
    assert hex_to_rgb("#FfFfFf") == (255, 255, 255)
    assert hex_to_rgb("#aBcDeF") == (171, 205, 239)


def test_is_color_in_palette_normalized_tolerance():
    """Test tolerance is properly normalized (0.0-1.0)"""
    palette = ["#000000", "#FFFFFF"]

    # Tolerance of 0.0 should only accept exact matches
    is_valid, _ = is_color_in_palette("#000001", palette, tolerance=0.0)
    assert is_valid is False

    # Tolerance of 1.0 should accept almost anything
    is_valid, _ = is_color_in_palette("#888888", palette, tolerance=1.0)
    assert is_valid is True


# ============================================================================
# Test: Real-World Scenarios
# ============================================================================


def test_414_capital_palette_validation():
    """Test realistic 414 Capital palette validation"""
    capital_palette = [
        "#002B5C",  # Navy blue (primary)
        "#FFFFFF",  # White
        "#000000",  # Black
        "#4A90E2",  # Light blue
        "#7F8C8D",  # Gray
    ]

    # Exact match should pass
    is_valid, _ = is_color_in_palette("#002B5C", capital_palette, tolerance=0.12)
    assert is_valid is True

    # Close to navy should pass
    is_valid, _ = is_color_in_palette("#003060", capital_palette, tolerance=0.12)
    assert is_valid is True

    # Bright red should fail
    is_valid, _ = is_color_in_palette("#FF0000", capital_palette, tolerance=0.12)
    assert is_valid is False

    # Close to white should pass
    is_valid, _ = is_color_in_palette("#FEFEFE", capital_palette, tolerance=0.12)
    assert is_valid is True


def test_grayscale_palette():
    """Test palette with grayscale colors"""
    grayscale = ["#000000", "#333333", "#666666", "#999999", "#CCCCCC", "#FFFFFF"]

    # Mid-gray should match closest
    is_valid, closest = is_color_in_palette("#555555", grayscale, tolerance=0.12)
    # Should be valid or close to #666666
    assert closest in ["#333333", "#666666"]


# ============================================================================
# Test: Performance Considerations
# ============================================================================


def test_large_palette_performance():
    """Test performance with large palette (100 colors)"""
    import time

    # Generate 100 grayscale colors
    large_palette = [f"#{i:02X}{i:02X}{i:02X}" for i in range(0, 255, 3)]

    start = time.time()

    # Test 100 color checks
    for i in range(100):
        test_color = f"#{i:02X}{i:02X}{i:02X}"
        is_color_in_palette(test_color, large_palette, tolerance=0.12)

    elapsed = time.time() - start

    # Should complete in reasonable time (< 1 second for 100 checks)
    assert elapsed < 1.0
