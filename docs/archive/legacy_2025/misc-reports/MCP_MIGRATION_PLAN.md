## MCP Migration Plan - Phased Rollout Strategy

This document outlines the phased approach to integrate the Model Context Protocol (MCP) layer into Saptiva OctaviOS Chat without disrupting existing functionality.

---

## Phase 1: MVP Deployment (Week 1) - ✅ Ready

**Goal**: Deploy MCP infrastructure with 3 example tools, fully backwards compatible.

### Tasks

1. **Backend Deployment** ✅
   - Deploy MCP module (`apps/api/src/mcp/`)
   - Register 3 tools in main.py: `audit_file`, `excel_analyzer`, `viz_tool`
   - Enable MCP routes: `GET /api/mcp/tools`, `POST /api/mcp/invoke`
   - Verify no impact on existing endpoints

2. **Frontend SDK** ✅
   - Deploy TypeScript MCP client (`apps/web/src/lib/mcp/`)
   - Integrate with existing apiClient
   - No UI changes (headless integration)

3. **Testing** ⏳
   - Unit tests for each tool
   - Integration tests for `/mcp/invoke`
   - Contract tests (input/output schemas)
   - Smoke test: audit_file with existing document

4. **Documentation** ✅
   - `MCP_ARCHITECTURE.md` - Architecture and design decisions
   - `MCP_MIGRATION_PLAN.md` - This file
   - `MCP_SECURITY_OBS_CHECKLIST.md` - Security and observability
   - OpenAPI schema auto-generated

5. **Deployment** ⏳
   - Deploy to staging
   - Run full regression suite
   - Monitor metrics (no degradation expected)
   - Deploy to production with feature flag `MCP_ENABLED=true`

### Success Criteria

- ✅ All 3 tools registered and discoverable via `GET /mcp/tools`
- ✅ Audit file tool returns same results as `POST /api/review/validate`
- ✅ No breaking changes to existing endpoints
- ⏳ Test coverage >80% for MCP module
- ⏳ Zero increase in P95 latency for existing endpoints
- ⏳ MCP health check passes: `GET /api/mcp/health`

### Rollback Plan

If issues arise:
1. Set feature flag `MCP_ENABLED=false` in env
2. Restart API containers (hot reload)
3. MCP routes return 503 Service Unavailable
4. Legacy endpoints unaffected

---

## Phase 2: Migrate Legacy Endpoints (Week 2-3) - 🔜 Next

**Goal**: Refactor existing endpoints to use MCP internally (backwards compatible).

### Tasks

1. **Audit Endpoint Migration**
   - Update `POST /api/review/validate` to call `audit_file` tool internally
   - Keep response format identical (no client changes)
   - Add A/B testing: 10% traffic → MCP, 90% → legacy
   - Monitor error rates and latency

2. **Excel Upload Enhancement**
   - Add Excel file type detection in file ingest pipeline
   - Automatically invoke `excel_analyzer` on upload (background)
   - Store analysis results in Document metadata
   - Expose via `GET /api/documents/{doc_id}/analysis`

3. **Visualization API (New)**
   - Create `POST /api/viz/generate` endpoint
   - Delegates to `viz_tool` internally
   - Returns chart spec for frontend rendering
   - Support inline data, Excel, SQL sources

4. **Testing**
   - Validate audit endpoint parity (old vs new)
   - Load testing for Excel analysis pipeline
   - E2E test: upload Excel → analyze → visualize

5. **Deployment**
   - Gradual rollout with A/B testing
   - Monitor MCP tool metrics (success rate, duration)
   - Full migration after 48h of stable metrics

### Success Criteria

- Audit endpoint produces identical results (diff=0)
- Excel analysis completes <10s for files <5MB
- Visualization rendering <2s for datasets <1000 rows
- No increase in error rate

### Rollback Plan

- Feature flag per endpoint: `AUDIT_USE_MCP`, `EXCEL_USE_MCP`
- Revert to legacy implementation if error rate >1%
- Automated rollback if latency P95 >5s

---

## Phase 3: Add New Tools (Week 4-5) - 🚀 Future

**Goal**: Extend MCP with new capabilities (no legacy equivalent).

### New Tools

1. **Deep Research Tool** (`deep_research`)
   - Wraps Aletheia research coordinator
   - Input: research query + context
   - Output: research report + artifacts
   - Integration: Replace `POST /api/deep-research` internals

2. **SQL Query Tool** (`sql_query`)
   - Executes read-only SQL queries
   - Input: SQL query + database connection
   - Output: Result set + metadata
   - Security: Whitelist allowed tables, enforce SELECT-only

3. **BI Dashboard Tool** (`bi_dashboard`)
   - Generates multi-chart dashboards
   - Input: Dashboard spec (JSON)
   - Output: Dashboard config for frontend
   - Composed of multiple `viz_tool` invocations

4. **Document Compare Tool** (`doc_compare`)
   - Compares two PDFs and highlights differences
   - Input: doc_id_a, doc_id_b
   - Output: Diff report + visual overlay
   - Use case: Version comparison, change detection

### Testing

- Unit tests for each new tool
- Integration tests with existing workflows
- Performance testing (tools should complete <30s)

### Deployment

- Feature flags per tool: `TOOL_<NAME>_ENABLED`
- Gradual rollout per user cohort
- Beta program for power users

### Success Criteria

- New tools registered and discoverable
- Usage metrics tracked in telemetry
- User feedback collected via in-app surveys

---

## Phase 4: Scale & Optimize (Week 6+) - 🔮 Long-term

**Goal**: Optimize performance and prepare for out-of-process extraction (if needed).

### Tasks

1. **Caching Layer**
   - Cache tool results in Redis (if `cacheable=true`)
   - TTL based on tool type (audit: 1h, viz: 5min)
   - Cache invalidation on document update

2. **Background Jobs**
   - Move long-running tools (>5s) to Celery/RQ
   - Return job_id immediately, poll for results
   - SSE streaming for progress updates

3. **Rate Limiting**
   - Per-tool rate limits (enforce `rate_limit` from ToolSpec)
   - Per-user quotas (e.g., 100 audits/day)
   - Graceful degradation (queue vs reject)

4. **Monitoring & Alerting**
   - Grafana dashboards for MCP metrics
   - Alerts: error_rate >5%, latency P95 >10s, tool crashes
   - On-call runbook for MCP incidents

5. **Out-of-Process Extraction (if needed)**
   - Extract heavy tools to separate service (e.g., Excel analyzer)
   - HTTP/gRPC interface (same contract)
   - Service mesh (Istio/Linkerd) for routing
   - Preserve in-process tools for low latency

### Success Criteria

- Cache hit rate >50% for cacheable tools
- Background jobs complete within SLA (95% <60s)
- Zero downtime during deployments
- Automated canary deployments

---

## Testing Strategy

### Unit Tests

```bash
# Backend
cd apps/api
pytest tests/mcp/ -v --cov=src/mcp --cov-report=html

# Frontend
cd apps/web
pnpm test src/lib/mcp
```

### Integration Tests

```python
# tests/integration/test_mcp_invoke.py

async def test_audit_file_e2e():
    # Upload PDF
    doc_id = await upload_test_pdf("sample.pdf")

    # Invoke audit_file tool
    response = await client.post("/api/mcp/invoke", json={
        "tool": "audit_file",
        "payload": {"doc_id": doc_id, "policy_id": "auto"}
    })

    assert response.status_code == 200
    assert response.json()["success"] == True
    assert "findings" in response.json()["result"]
```

### Contract Tests

```python
# tests/contract/test_tool_schemas.py

async def test_audit_file_input_schema():
    spec = await mcp_registry.get_tool("audit_file").get_spec()

    # Validate against JSON Schema
    jsonschema.validate(
        instance={"doc_id": "abc123", "policy_id": "auto"},
        schema=spec.input_schema
    )
```

### Smoke Tests

```bash
# Smoke test script
make test-mcp-smoke

# Checks:
# 1. GET /api/mcp/health returns 200
# 2. GET /api/mcp/tools returns 3+ tools
# 3. POST /api/mcp/invoke with audit_file succeeds
# 4. Backwards compatibility: POST /api/review/validate still works
```

---

## Feature Flags

Use environment variables for feature flags:

```bash
# Enable/disable MCP globally
MCP_ENABLED=true

# Enable/disable specific tools
TOOL_AUDIT_FILE_ENABLED=true
TOOL_EXCEL_ANALYZER_ENABLED=true
TOOL_VIZ_TOOL_ENABLED=true
TOOL_DEEP_RESEARCH_ENABLED=false  # Phase 3

# Enable internal MCP usage in legacy endpoints
AUDIT_ENDPOINT_USE_MCP=true
EXCEL_INGEST_USE_MCP=true

# A/B testing
MCP_AUDIT_ROLLOUT_PERCENTAGE=10  # 10% traffic
```

Configure in `apps/api/src/core/config.py`:

```python
class Settings(BaseSettings):
    mcp_enabled: bool = Field(default=True)
    tool_audit_file_enabled: bool = Field(default=True)
    tool_excel_analyzer_enabled: bool = Field(default=True)
    tool_viz_tool_enabled: bool = Field(default=True)
    audit_endpoint_use_mcp: bool = Field(default=False)
    mcp_audit_rollout_percentage: int = Field(default=0)
```

---

## Monitoring & Metrics

### Key Metrics

1. **Tool Invocation Rate**
   - `mcp_tool_invocations_total{tool, version, status}`
   - Counter: Total invocations per tool

2. **Tool Latency**
   - `mcp_tool_duration_seconds{tool, version, quantile}`
   - Histogram: P50, P95, P99 latency

3. **Tool Error Rate**
   - `mcp_tool_errors_total{tool, version, error_code}`
   - Counter: Errors by type (INVALID_INPUT, EXECUTION_ERROR, TIMEOUT)

4. **Cache Hit Rate**
   - `mcp_cache_hits_total{tool}`
   - Counter: Cache hits vs misses

### Dashboards

Create Grafana dashboard with panels:
- Tool invocation rate (7d trend)
- P95 latency by tool (heatmap)
- Error rate by tool (stacked area)
- Cache hit rate (gauge)
- Active tools (table)

### Alerts

```yaml
# alerts.yaml
alerts:
  - name: MCP High Error Rate
    condition: mcp_tool_errors_total > 10/5min
    severity: warning

  - name: MCP Slow Tool
    condition: mcp_tool_duration_seconds{quantile="0.95"} > 10s
    severity: warning

  - name: MCP Tool Unavailable
    condition: up{job="mcp"} == 0
    severity: critical
```

---

## Acceptance Criteria (Overall)

### Phase 1 (MVP)
- ✅ MCP module deployed and discoverable
- ✅ 3 tools registered: audit_file, excel_analyzer, viz_tool
- ⏳ Test coverage >80%
- ⏳ Zero impact on existing endpoints (latency, error rate)

### Phase 2 (Migration)
- Legacy audit endpoint uses MCP internally
- Identical response format (backwards compatible)
- A/B testing shows <5% error delta

### Phase 3 (New Tools)
- 4+ new tools added (deep_research, sql_query, bi_dashboard, doc_compare)
- Feature flags control per-tool availability
- User feedback >4/5 stars

### Phase 4 (Scale)
- Cache hit rate >50%
- Background jobs enabled for long-running tools
- Zero downtime deployments
- Out-of-process extraction (if needed)

---

## Risk Mitigation

### Risks

1. **Breaking Changes**
   - Mitigation: Strict backwards compatibility, contract tests, feature flags

2. **Performance Degradation**
   - Mitigation: A/B testing, gradual rollout, automated rollback triggers

3. **Tool Failures**
   - Mitigation: Error handling, retries, circuit breaker, graceful degradation

4. **Security Vulnerabilities**
   - Mitigation: Input validation, auth/authz, rate limiting, audit logs

### Rollback Triggers

Automatically roll back if:
- Error rate >5% (vs baseline <1%)
- Latency P95 >2x baseline
- Tool crashes >10/hour
- Manual intervention required

---

## Timeline

| Phase | Duration | Start | End | Status |
|-------|----------|-------|-----|--------|
| Phase 1: MVP | 1 week | Week 1 | Week 1 | ✅ In Progress |
| Phase 2: Migration | 2 weeks | Week 2 | Week 3 | 🔜 Next |
| Phase 3: New Tools | 2 weeks | Week 4 | Week 5 | 🚀 Future |
| Phase 4: Scale | Ongoing | Week 6 | - | 🔮 Long-term |

---

## Communication Plan

### Stakeholders

- **Engineering Team**: Daily standups, Slack updates
- **Product Team**: Weekly progress reports, demo sessions
- **Users**: In-app announcements, beta program invitations

### Milestones

1. **Week 1**: MVP deployed to staging ✅
2. **Week 2**: MVP deployed to production (feature flag)
3. **Week 3**: Audit endpoint migrated to MCP
4. **Week 4**: Beta program launched for new tools
5. **Week 6**: Full MCP adoption, legacy endpoints deprecated

---

## Appendix

### Useful Commands

```bash
# Check MCP health
curl https://api.octavios.com/api/mcp/health

# List tools
curl https://api.octavios.com/api/mcp/tools

# Invoke audit_file
curl -X POST https://api.octavios.com/api/mcp/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "audit_file", "payload": {"doc_id": "abc123"}}'

# Run tests
make test-mcp

# Generate OpenAPI schema
make generate-openapi
```

### References

- [MCP Architecture](./MCP_ARCHITECTURE.md)
- [Security Checklist](./MCP_SECURITY_OBS_CHECKLIST.md)
- [OpenAPI Schema](../openapi.json)
