# Changelog

All notable changes to BankAdvisor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-30

### Added

#### Core Features
- **HU3 NLP Pipeline**: Natural language query interpretation for banking metrics
  - EntityService: Extract banks, dates, metrics from Spanish queries
  - IntentService: Hybrid classification (rules-first + LLM-fallback)
  - AnalyticsService: DB queries with smart formatting
  - PlotlyGenerator: Visualization configuration

- **ETL Pipeline**: Automated data loading from CNBV Excel files
  - Daily schedule via cron (2:00 AM)
  - Tracking in `etl_runs` table
  - Healthcheck endpoint with ETL status

- **9 Priority Visualizations**: Core banking metrics
  - IMOR (Índice de Morosidad)
  - ICAP (Índice de Capitalización)
  - ICOR (Índice de Cobertura)
  - Cartera Comercial Total
  - Cartera Comercial Sin Gobierno (calculated)
  - Cartera Vencida
  - Reservas Totales
  - Pérdida Esperada
  - Dual-mode charts (evolution/comparison)

#### Architecture
- **SOLID Principles**: Clean separation of concerns
  - Single Responsibility: One service per domain
  - Open/Closed: Extensible intent classification
  - Liskov Substitution: Smart defaults preserve behavior
  - Dependency Inversion: Runtime configuration

- **Runtime Configuration**: `config/bankadvisor.yaml`
  - PRIMARY_BANK configurable (default: INVEX)
  - Aggregate aliases (sistema, sector, mercado)
  - LLM fallback toggle and thresholds
  - Performance settings

#### Testing & Quality
- **Smoke Test**: 12 queries including adversarials
- **Unit Tests**: 9 priority visualizations
- **E2E Tests**: Full demo flows
- **NL Variants**: 32 query phrasings tested
- **LLM Fallback Tests**: Mock-based resilience tests
- **Performance Benchmark**: p50/p95/p99 metrics

#### Documentation
- `docs/ARCHITECTURE.md`: System diagram and component roles
- `docs/DEVELOPER_GUIDE.md`: How to extend the system
- `docs/LIMITATIONS.md`: Known constraints (estoic-honest)
- `docs/DEMO_SCRIPT_2025-12-03.md`: Demo runbook
- `docs/ETL_SCHEDULER_SETUP.md`: ETL operations guide

#### Operations
- `scripts/smoke_demo_bank_analytics.py`: Pre-demo validation
- `scripts/ops_validate_etl.py`: ETL health checker
- `scripts/benchmark_performance_http.py`: Performance testing
- GitHub Actions CI: `.github/workflows/bankadvisor-ci.yml`

### Performance Baseline

| Query Type | p50 | p95 | Notes |
|------------|-----|-----|-------|
| Ratios (IMOR, ICAP) | 16ms | 26ms | Rules-first, no LLM |
| Timelines | 112ms | 206ms | DB query |
| Calculated metrics | 1.6s | 1.7s | Requires LLM |

### Known Issues

See `docs/LIMITATIONS.md` for full details:

- **Banks**: Only INVEX and SISTEMA supported
- **Metrics**: 15 metrics in whitelist
- **Language**: Spanish only (Mexican banking terminology)
- **Time Range**: 2017-2025, monthly granularity
- **Schema**: Single denormalized table (not normalized dim/fact)

### Dependencies

- Python 3.11+
- FastAPI
- PostgreSQL
- Plotly
- structlog
- dateparser
- httpx (for LLM calls)

---

## [Unreleased]

### Planned
- Multi-client profiles (config/profiles/*.yaml)
- Normalized data model (fact/dim tables)
- /metrics endpoint for observability
- Additional banks support
- Visualizations 10-17 from PRD

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2025-11-30 | Initial release, INVEX MVP |
