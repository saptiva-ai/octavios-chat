# BankAdvisor MCP Server

**Version:** 1.0.0
**Status:** Production Ready
**Protocol:** MCP (Model Context Protocol) via JSON-RPC 2.0

---

## Overview

BankAdvisor is a natural language banking analytics service. Ask questions in Spanish about CNBV metrics and get interactive visualizations.

```
User: "IMOR de INVEX en 2024"
→ Returns: Line chart showing IMOR evolution for INVEX in 2024
```

### Key Features

- **Natural Language Queries**: Spanish banking terminology
- **9 Priority Visualizations**: IMOR, ICAP, ICOR, Cartera, Reservas, etc.
- **Hybrid Intent Classification**: Rules-first (80% queries in <20ms) + LLM fallback
- **Automated ETL**: Daily data refresh from CNBV sources
- **SOLID Architecture**: Clean separation of concerns

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- PostgreSQL 15

### Run the Service

```bash
# From project root
docker compose up -d bank-advisor

# Verify health
curl http://localhost:8002/health

# Run smoke test (12 queries)
cd plugins/bank-advisor-private
python scripts/smoke_demo_bank_analytics.py --port 8002
```

### Expected Output

```
🟢 ALL CHECKS PASSED - SAFE TO DEMO
Total Queries:  12
✅ Passed:       12
Success Rate:   100.0%
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health + ETL status |
| `/metrics` | GET | Observability metrics |
| `/rpc` | POST | JSON-RPC 2.0 tool invocation |

### JSON-RPC Example

```bash
curl -X POST http://localhost:8002/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "bank_analytics",
      "arguments": {"metric_or_query": "IMOR de INVEX en 2024"}
    },
    "id": 1
  }'
```

---

## Performance

| Query Type | p50 | p95 | Notes |
|------------|-----|-----|-------|
| Ratios (IMOR, ICAP) | 16ms | 26ms | Rules-first |
| Timelines | 112ms | 206ms | DB query |
| Calculated metrics | 1.6s | 1.7s | LLM required |

See `docs/performance_baseline.json` for full benchmark.

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | Required |
| `PRIMARY_BANK` | Default bank | `INVEX` |
| `SAPTIVA_API_KEY` | LLM API key | Optional |
| `LLM_FALLBACK_ENABLED` | Enable LLM | `true` |

### Multi-Client Profiles

```yaml
# config/bankadvisor.yaml
active_profile: "invex"  # Loads config/profiles/invex.yaml
```

To add a new client, copy `config/profiles/template.yaml` to `config/profiles/<client>.yaml`.

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | System design, SOLID principles |
| `docs/DEVELOPER_GUIDE.md` | How to extend (add metrics, intents) |
| `docs/LIMITATIONS.md` | Known constraints |
| `docs/DEMO_SCRIPT_2025-12-03.md` | Demo runbook |
| `docs/DATA_MODEL_EVOLUTION.md` | Future schema plans |

---

## Testing

```bash
# Smoke test (pre-demo validation)
python scripts/smoke_demo_bank_analytics.py --port 8002

# ETL health check
python scripts/ops_validate_etl.py --port 8002

# Performance benchmark
python scripts/benchmark_performance_http.py --port 8002

# Unit tests
pytest tests/ -v
```

---

## Project Structure

```
plugins/bank-advisor-private/
├── src/
│   └── bankadvisor/
│       ├── services/           # Core services (intent, analytics, plotly)
│       ├── entity_service.py   # NL entity extraction
│       ├── config_service.py   # Metric/visualization config
│       └── runtime_config.py   # Runtime settings
├── config/
│   ├── bankadvisor.yaml        # Main config
│   ├── profiles/               # Client profiles
│   └── synonyms.yaml           # Metric aliases
├── scripts/
│   ├── smoke_demo_bank_analytics.py
│   ├── ops_validate_etl.py
│   └── benchmark_performance_http.py
├── tests/
│   ├── test_nl_variants.py     # 32 NL phrase variants
│   ├── test_llm_fallback.py    # LLM resilience tests
│   └── test_9_priority_visualizations.py
├── docs/                       # All documentation
├── CHANGELOG.md
└── README.md
```

---

## Supported Queries

### Evolution (Timeline)
```
"IMOR de INVEX en 2024"
"Cartera vencida últimos 12 meses"
"Evolución del ICAP de INVEX"
```

### Comparison
```
"IMOR de INVEX vs sistema"
"Compara cartera comercial INVEX contra sistema"
```

### Calculated Metrics
```
"Cartera comercial sin gobierno"
"Reservas totales de INVEX"
```

---

## ETL Operations

ETL runs daily at 2:00 AM via cron.

```bash
# Check ETL status
curl http://localhost:8002/health | jq .etl

# Manual ETL execution
docker exec bank-advisor-mcp python -m bankadvisor.etl_runner

# Validate ETL health
python scripts/ops_validate_etl.py --port 8002
```

---

## Troubleshooting

### "No data returned"
1. Check ETL ran: `curl http://localhost:8002/health | jq .etl`
2. Check date range has data in DB

### "Metric not found"
1. Verify alias in `config/synonyms.yaml`
2. Check whitelist in `config_service.py`

### "LLM timeout"
- System falls back to rules-based classification
- Check `SAPTIVA_API_KEY` if LLM required

---

## Version History

See `CHANGELOG.md` for full release notes.

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2025-11-30 | Initial release, INVEX MVP |

---

## License

Private Enterprise Plugin - Confidential INVEX
