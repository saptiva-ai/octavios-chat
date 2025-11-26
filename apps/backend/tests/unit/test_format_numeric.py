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
sys.modules.setdefault("beanie", beanie_module)

operators_module = ModuleType("beanie.operators")
operators_module.In = lambda *args, **kwargs: None
sys.modules.setdefault("beanie.operators", operators_module)


from src.services.format_auditor import audit_numeric_format


@pytest.mark.asyncio
async def test_numeric_format_valid_numbers_pass():
    fragments = [
        SimpleNamespace(
            fragment_id="frag-1",
            page=1,
            text="Ingresos totales: 1,234,567.89 MXN",
            bbox=None,
        )
    ]

    config = {
        "enabled": True,
        "style": "MX",
        "thousand_sep": ",",
        "decimal_sep": ".",
        "min_decimals": 2,
        "max_decimals": 2,
        "severity": "high",
    }

    findings, summary = await audit_numeric_format(fragments, config)

    assert summary["checked"] == 1
    assert summary["invalid"] == 0
    assert findings == []


@pytest.mark.asyncio
async def test_numeric_format_flags_us_style_when_eu_expected():
    fragments = [
        SimpleNamespace(
            fragment_id="frag-2",
            page=3,
            text="El valor de cartera asciende a 10,000.00 USD.",
            bbox=None,
        )
    ]

    config = {
        "enabled": True,
        "style": "EU",
        "thousand_sep": ".",
        "decimal_sep": ",",
        "min_decimals": 2,
        "max_decimals": 2,
        "severity": "high",
    }

    findings, summary = await audit_numeric_format(fragments, config)

    assert summary["checked"] == 1
    assert summary["invalid"] == 1
    assert findings
    assert "no permitido" in findings[0].issue.lower()
    assert findings[0].location.page == 3


@pytest.mark.asyncio
async def test_numeric_format_flags_missing_decimals():
    fragments = [
        SimpleNamespace(
            fragment_id="frag-3",
            page=2,
            text="Margen operativo: 1,234 MXN",
            bbox=None,
        )
    ]

    config = {
        "enabled": True,
        "style": "MX",
        "thousand_sep": ",",
        "decimal_sep": ".",
        "min_decimals": 2,
        "max_decimals": 2,
        "severity": "medium",
    }

    findings, summary = await audit_numeric_format(fragments, config)

    assert summary["checked"] == 1
    assert summary["invalid"] == 1
    assert findings[0].severity == "medium"
