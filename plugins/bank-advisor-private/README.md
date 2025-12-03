# BankAdvisor MCP Server

**Version:** 1.1.0
**Status:** Production Ready
**Protocol:** MCP (Model Context Protocol) via JSON-RPC 2.0
**ETL Engine:** Polars (high-performance DataFrame)

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
- **Unified ETL with Polars**: 11x faster loading (1.3M records in 4s), 5x less memory
- **SOLID Architecture**: Clean separation of concerns

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- PostgreSQL 15
- Python 3.11+ (for scripts)

### 1. Build and Start Services

```bash
# From project root
make dev-rebuild  # Builds containers with latest changes
```

### 2. Initialize Data (Required on First Run)

**Consolidated initialization** (migrations + ETL):
```bash
make init-bank-advisor
```

This single command:
- ✅ Applies database schema migrations (normalized + legacy)
- ✅ Runs Legacy ETL → `monthly_kpis` table (3660 records, 2017-2025)
- ✅ Runs Normalized ETL → `instituciones`, `metricas_financieras`, `segmentos_cartera`
- ✅ Verifies data integrity across both schemas
- ✅ Performs health checks

**Alternative commands**:
```bash
make init-bank-advisor-migrations  # Only migrations
make init-bank-advisor-etl         # Only ETL (both pipelines)

# Or use the script directly:
./scripts/init_bank_advisor_data.sh
./scripts/init_bank_advisor_data.sh --etl-only
```

**Expected output**:
```
✓ Container verification passed
✓ Migrations completed (normalized + legacy schemas)
✓ Schema verification passed
✓ Legacy ETL completed (3660 records)
⚠ Normalized ETL completed (or skipped if no BE_BM data)
✓ Data verification: 2017-01 to 2025-07, 37 banks
✓ Bank Advisor service is healthy
```

### 3. Verify Installation

```bash
# Check service health
curl http://localhost:8002/health

# Run smoke test (12 queries)
cd plugins/bank-advisor-private
python scripts/smoke_demo_bank_analytics.py --port 8002
```

### Expected Test Output

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
| `ETL_CONSOLIDATION.md` | **Dual ETL architecture, consolidation guide** |
| `docs/ARCHITECTURE.md` | System design, SOLID principles |
| `docs/DEVELOPER_GUIDE.md` | How to extend (add metrics, intents) |
| `docs/LIMITATIONS.md` | Known constraints |
| `docs/DEMO_SCRIPT_2025-12-03.md` | Demo runbook |
| `docs/DATA_MODEL_EVOLUTION.md` | Future schema plans |

---

## Testing

```bash
# ETL equivalence tests (13 tests, data loading + transformations)
BANK_ADVISOR_DATA_ROOT=./data/raw pytest etl/tests/test_etl_equivalence.py -v

# Smoke test (pre-demo validation)
python scripts/smoke_demo_bank_analytics.py --port 8002

# ETL health check
python scripts/ops_validate_etl.py --port 8002

# Performance benchmark
python scripts/benchmark_performance_http.py --port 8002

# Unit tests (services)
pytest src/bankadvisor/tests/ -v
```

---

## Project Structure

```
plugins/bank-advisor-private/
├── src/
│   ├── main.py                 # MCP server entry point
│   └── bankadvisor/
│       ├── services/           # Core services (intent, analytics, plotly)
│       ├── entity_service.py   # NL entity extraction
│       ├── config_service.py   # Metric/visualization config
│       └── runtime_config.py   # Runtime settings
├── etl/                        # Unified ETL Pipeline (Polars)
│   ├── etl_unified.py          # Main orchestrator
│   ├── loaders_polars.py       # Data loaders (8 sources)
│   ├── transforms_polars.py    # IFRS9 transformations
│   └── tests/
│       └── test_etl_equivalence.py  # 13 equivalence tests
├── config/
│   ├── bankadvisor.yaml        # Main config
│   ├── profiles/               # Client profiles
│   └── synonyms.yaml           # Metric aliases
├── scripts/
│   ├── smoke_demo_bank_analytics.py
│   ├── ops_validate_etl.py
│   └── benchmark_performance_http.py
├── data/raw/                   # Source data files (gitignored)
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

### Unified ETL Architecture (Polars)

Bank Advisor uses a **unified Polars-based ETL pipeline** that consolidates all data sources:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ETL UNIFICADO (etl_unified.py)               │
├─────────────────────────────────────────────────────────────────┤
│  8 Data Sources → loaders_polars.py → transforms_polars.py     │
│                                                                 │
│  Sources:                          Output Tables:               │
│  ├─ CNBV_Cartera_Bancos_V2.xlsx   ├─ monthly_kpis (3660 rows)  │
│  ├─ BE_BM_202509.xlsx (16 sheets) ├─ cnbv_enriched (32K rows)  │
│  ├─ ICAP_Bancos.xlsx              ├─ segments (2.4K rows)      │
│  ├─ TDA.xlsx                      └─ instituciones (37 banks)  │
│  ├─ TE_Invex_Sistema.xlsx                                       │
│  ├─ CorporateLoan_CNBVDB.csv      Performance:                  │
│  ├─ CASTIGOS.xlsx                 ├─ CSV 219MB: 45s → 4s (11x) │
│  └─ Instituciones.xlsx            ├─ Memory: 800MB → 150MB (5x)│
│                                   └─ Total ETL: ~8 seconds      │
└─────────────────────────────────────────────────────────────────┘
```

**Key Components:**
- `etl/loaders_polars.py` - Unified data loading with lazy evaluation
- `etl/transforms_polars.py` - IFRS9-compliant transformations
- `etl/etl_unified.py` - Orchestrator for all pipelines

See [`ETL_CONSOLIDATION.md`](ETL_CONSOLIDATION.md) for complete architecture documentation.

### Check ETL Status

```bash
# Check both ETL statuses
curl http://localhost:8002/health | jq .etl

# Verify data integrity
make init-bank-advisor  # Re-runs verification without re-processing
```

### Manual ETL Execution

```bash
# Full initialization (migrations + unified ETL)
make init-bank-advisor

# Run unified ETL directly (with dry-run option)
cd plugins/bank-advisor-private
python -m etl.etl_unified --dry-run  # Test without DB writes
python -m etl.etl_unified            # Full execution to DB

# Run ETL equivalence tests
BANK_ADVISOR_DATA_ROOT=./data/raw pytest etl/tests/test_etl_equivalence.py -v

# Validate ETL health
python scripts/ops_validate_etl.py --port 8002
```

### Data Loaded

After successful initialization:
- **3660 monthly records** (enero 2017 - julio 2025)
- **37 instituciones bancarias**
- **Métricas**: ICAP (2815), TDA (3660), TASA_MN (2707), TASA_ME (2142)
- **Segmentos**: Normalized portfolio segments catalog
- **Balance Sheet**: Sept 2025 data (if BE_BM_202509.xlsx available)

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
| 1.1.0 | 2025-12-03 | Unified ETL with Polars (11x faster), 13 equivalence tests |
| 1.0.0 | 2025-11-30 | Initial release, INVEX MVP |

---

## License

Private Enterprise Plugin - Confidential INVEX
