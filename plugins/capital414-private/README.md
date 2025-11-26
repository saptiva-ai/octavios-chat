# Capital 414 Private Plugin

MCP Server for COPILOTO_414 Document Compliance Validation.

## Overview

This plugin provides the COPILOTO_414 audit system as a standalone MCP (Model Context Protocol) service. It validates PDF documents against corporate compliance policies using 8 specialized auditors.

## Architecture

```
plugins/capital414-private/
├── src/
│   ├── main.py                    # FastMCP server entry point
│   ├── audit_engine/              # Core validation logic
│   │   ├── coordinator.py         # Orchestrates all 8 auditors
│   │   ├── policy_manager.py      # Policy configuration loader
│   │   └── auditors/              # 8 specialized validators
│   │       ├── compliance_auditor.py
│   │       ├── format_auditor.py
│   │       ├── typography_auditor.py
│   │       ├── grammar_auditor.py
│   │       ├── logo_auditor.py
│   │       ├── color_palette_auditor.py
│   │       ├── entity_consistency_auditor.py
│   │       └── semantic_consistency_auditor.py
│   ├── schemas/                   # Pydantic models
│   ├── reports/                   # PDF/Markdown report generation
│   ├── config/                    # YAML policy configurations
│   │   ├── compliance.yaml
│   │   └── policies.yaml
│   └── assets/                    # Static assets (logo template)
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

## Auditors

| Auditor | Description |
|---------|-------------|
| **Disclaimer** | Legal disclaimer presence and coverage (fuzzy matching) |
| **Format** | Number formatting, fonts, colors |
| **Typography** | Font hierarchy and spacing |
| **Grammar** | Spelling and grammar (via LanguageTool) |
| **Logo** | Corporate logo detection (via OpenCV) |
| **Color Palette** | Brand color compliance |
| **Entity Consistency** | Consistent naming |
| **Semantic Consistency** | Document coherence |

## MCP Tools

### `audit_document_full`

Validate a PDF document against compliance policies.

**Parameters:**
- `file_path` (str): Absolute path to the PDF file
- `policy_id` (str): Policy ID (default: "auto")
- `client_name` (str, optional): Client name for disclaimer validation
- `enable_*` (bool): Toggle individual auditors

**Returns:**
- Job ID
- Total findings with severity breakdown
- Executive summary in Markdown
- PDF report path

### `list_policies`

List available validation policies.

### `get_policy_details`

Get detailed configuration for a specific policy.

## Running

### Development

```bash
# Start with docker-compose
docker compose -f infra/docker-compose.yml up capital414-auditor -d

# Or run directly
cd plugins/capital414-private
pip install -r requirements.txt
python -m uvicorn src.main:app --host 0.0.0.0 --port 8002
```

### Docker

```bash
docker build -t capital414-auditor -f plugins/capital414-private/Dockerfile .
docker run -p 8002:8002 capital414-auditor
```

## Integration

### From OctaviOS Core

The Core connects to the plugin via SSE:

```
MCP Discovery URL: http://capital414-auditor:8002/sse
```

### Direct MCP Call

```python
from mcp import Client

async with Client("http://localhost:8002/sse") as client:
    result = await client.call_tool(
        "audit_document_full",
        {
            "file_path": "/path/to/document.pdf",
            "policy_id": "414-std",
            "enable_grammar": True,
        }
    )
    print(result["executive_summary_markdown"])
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `capital414-auditor` | Server name |
| `MCP_SERVER_PORT` | `8002` | Server port |
| `LANGUAGETOOL_URL` | `http://languagetool:8010/v2/check` | LanguageTool service URL |
| `LOG_LEVEL` | `INFO` | Logging level |

## License

Proprietary - 414 Capital
