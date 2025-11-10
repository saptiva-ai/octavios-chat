import sys
from types import ModuleType, SimpleNamespace

import pytest


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


sys.modules.setdefault("structlog", SimpleNamespace(get_logger=lambda *a, **k: _DummyLogger()))

if "beanie" not in sys.modules:
    beanie_module = ModuleType("beanie")
    beanie_module.Document = object

    def _indexed(field_type, **kwargs):
        return field_type

    class _DummyLink:
        @classmethod
        def __class_getitem__(cls, item):
            return item


    beanie_module.Indexed = _indexed
    beanie_module.Link = _DummyLink
    sys.modules["beanie"] = beanie_module

if "beanie.operators" not in sys.modules:
    operators_module = ModuleType("beanie.operators")
    operators_module.In = lambda *args, **kwargs: None
    sys.modules["beanie.operators"] = operators_module


from src.services.typography_auditor import audit_typography


def _make_fragment(
    fragment_id: str,
    page: int,
    text: str,
    bbox,
    font_size=None,
):
    return SimpleNamespace(
        fragment_id=fragment_id,
        page=page,
        text=text,
        bbox=bbox,
        font_size=font_size,
    )


@pytest.mark.asyncio
async def test_typography_flags_excessive_heading_levels():
    fragments = [
        _make_fragment(f"frag-{i}", 1, f"Heading {i}", [0, i * 10, 100, i * 10 + 8], font_size=size)
        for i, size in enumerate([32, 28, 24, 20, 18, 16, 14], start=1)
    ]

    config = {
        "enabled": True,
        "heading_font_threshold": 18,
        "max_heading_levels": 5,
        "severity_heading": "low",
        "min_line_spacing": 0.5,
        "max_line_spacing": 2.5,
    }

    findings, summary = await audit_typography(fragments, config)

    assert any(f.rule == "heading_hierarchy" for f in findings)
    assert summary["heading"]["heading_levels"] == 6  # sizes >= threshold


@pytest.mark.asyncio
async def test_typography_detects_overlap():
    fragments = [
        _make_fragment("para-1", 1, "Linea 1", [0, 10, 100, 20]),
        _make_fragment("para-2", 1, "Linea 2", [0, 18, 100, 28]),  # overlaps (18 < 20)
    ]

    config = {
        "enabled": True,
        "min_line_spacing": 0.5,
        "max_line_spacing": 2.5,
        "severity_spacing": "low",
    }

    findings, summary = await audit_typography(fragments, config)

    assert any(f.rule == "line_spacing" for f in findings)
    assert summary["spacing"]["overlaps_detected"] == 1


@pytest.mark.asyncio
async def test_typography_disabled_returns_empty():
    fragments = [_make_fragment("frag-1", 1, "Texto", [0, 0, 100, 10], font_size=20)]

    findings, summary = await audit_typography(fragments, {"enabled": False})

    assert findings == []
    assert summary["enabled"] is False
