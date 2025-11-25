# MCP Security & Observability Checklist

This document outlines security requirements, observability practices, and operational guidelines for the Model Context Protocol (MCP) integration.

---

## Security Checklist

### Authentication & Authorization

- [x] **JWT Authentication Required**
  - All MCP endpoints require valid JWT token via `Depends(get_current_user)`
  - Token validation in `AuthMiddleware`
  - Unauthorized access returns 401

- [x] **User Context Injection**
  - `user_id` automatically injected into tool execution context
  - Tools validate document ownership before processing
  - No cross-user data access

- [ ] **Role-Based Access Control (RBAC)** *(Future)*
  - Define roles: `user`, `admin`, `auditor`
  - Per-tool permissions: `TOOL_<name>_ALLOWED_ROLES`
  - Enforce in `create_mcp_router()` with custom dependency

- [ ] **Scoped API Keys** *(Future)*
  - Allow API keys with limited tool access
  - Scope format: `mcp:audit_file:read`, `mcp:*:write`
  - Key rotation policy (90 days)

### Input Validation

- [x] **Schema Validation**
  - All tools implement `validate_input()` method
  - Pydantic models for request/response
  - JSON Schema in ToolSpec for API docs

- [x] **Payload Size Limits**
  - `max_payload_size_kb` enforced per tool
  - Default: 1MB, configurable per tool
  - HTTP 413 Payload Too Large if exceeded

- [ ] **Content Type Validation** *(Enhancement)*
  - Validate file MIME types match declared types
  - Reject executable files (.exe, .sh, .bat)
  - Scan for embedded scripts in PDFs

- [ ] **SQL Injection Protection** *(For SQL tool)*
  - Use parameterized queries only
  - Whitelist allowed tables/columns
  - Enforce READ-ONLY mode (no INSERT/UPDATE/DELETE)

### Rate Limiting

- [x] **Per-Tool Rate Limits**
  - Defined in `ToolSpec.rate_limit`
  - Example: `{"calls_per_minute": 10}`
  - Enforced via Redis sliding window

- [x] **Per-User Rate Limits**
  - Existing file upload limiter: 5 uploads/min
  - Apply to MCP invoke: 30 requests/min per user
  - HTTP 429 Too Many Requests if exceeded

- [ ] **Global Rate Limits** *(Production)*
  - API-wide: 1000 req/s
  - Per-tool: configurable in env
  - Example: `TOOL_AUDIT_FILE_MAX_RPS=5`

### Timeout Enforcement

- [x] **Per-Tool Timeouts**
  - Defined in `ToolSpec.timeout_ms`
  - Example: `audit_file` → 60s, `excel_analyzer` → 30s
  - Tool execution wrapped with `asyncio.wait_for()`

- [ ] **Circuit Breaker** *(Enhancement)*
  - Open circuit if error rate >50% (5min window)
  - Half-open after 30s cooldown
  - Fail fast with 503 Service Unavailable

### Data Privacy

- [x] **PII Scrubbing**
  - Sanitize LLM responses with `text_sanitizer.py`
  - Remove emails, phone numbers, SSNs

- [ ] **Audit Logging** *(Production)*
  - Log all MCP invocations (tool, user, payload hash, result status)
  - Store in MongoDB `mcp_audit_log` collection
  - Retention: 90 days

- [ ] **GDPR Compliance** *(Future)*
  - User data deletion: cascade to MCP invocation logs
  - Data export: include MCP activity
  - Consent management: opt-out of analytics

### Secrets Management

- [x] **Environment Variables**
  - All secrets in `envs/.env`
  - Never committed to git
  - Loaded via `pydantic.BaseSettings`

- [ ] **Secret Rotation** *(Production)*
  - Rotate Saptiva API key every 90 days
  - Rotate DB passwords every 180 days
  - Automated via CI/CD pipeline

- [ ] **Vault Integration** *(Enterprise)*
  - Use HashiCorp Vault for secrets
  - Dynamic database credentials
  - Encryption at rest

### Network Security

- [x] **HTTPS Only**
  - Enforce TLS 1.2+ in production
  - HSTS header: `Strict-Transport-Security: max-age=31536000`

- [x] **CORS Configuration**
  - Whitelist origins in `CORS_ORIGINS`
  - No wildcard (`*`) in production

- [ ] **API Gateway** *(Production)*
  - AWS API Gateway / Kong
  - Rate limiting, WAF, DDoS protection

---

## Observability Checklist

### Logging

- [x] **Structured Logging**
  - JSON format via `structlog`
  - Fields: `timestamp`, `level`, `tool`, `user_id`, `invocation_id`, `duration_ms`
  - Log levels: DEBUG (dev), INFO (prod), ERROR (always)

- [x] **Log Correlation**
  - `trace_id` propagated across services
  - `invocation_id` unique per tool call
  - Link to Saptiva LLM request IDs

- [ ] **Log Aggregation** *(Production)*
  - Ship to Elasticsearch/Loki
  - Centralized search and alerts
  - Retention: 30 days

### Metrics

- [x] **Tool Invocation Counter**
  ```python
  increment_tool_invocation(tool_name)
  ```
  - Metric: `mcp_tool_invocations_total{tool, version, status}`
  - Labels: `tool`, `version`, `status=success|error`

- [x] **Tool Latency Histogram**
  ```python
  record_tool_duration(tool_name, duration_ms)
  ```
  - Metric: `mcp_tool_duration_seconds{tool, version, quantile}`
  - Quantiles: P50, P95, P99

- [x] **Tool Error Counter**
  ```python
  increment_tool_error(tool_name, error_code)
  ```
  - Metric: `mcp_tool_errors_total{tool, version, error_code}`
  - Codes: `INVALID_INPUT`, `EXECUTION_ERROR`, `TIMEOUT`, `NOT_FOUND`

- [ ] **Cache Metrics** *(Future)*
  - `mcp_cache_hits_total{tool}`
  - `mcp_cache_misses_total{tool}`
  - `mcp_cache_size_bytes`

### Tracing

- [x] **OpenTelemetry Integration**
  - Spans created for tool invocation
  - Parent span: HTTP request
  - Child spans: validation, execution, response building

- [ ] **Distributed Tracing** *(Production)*
  - Export to Jaeger/Zipkin
  - Trace across API → Saptiva → Aletheia
  - Visualization in APM tool

### Health Checks

- [x] **MCP Health Endpoint**
  - `GET /api/mcp/health`
  - Returns: `{status, mcp_version, tools_registered}`
  - Kubernetes liveness probe

- [ ] **Deep Health Checks** *(Production)*
  - Check MongoDB connectivity
  - Check Redis connectivity
  - Check Saptiva API availability
  - Return degraded status if subsystem fails

### Alerting

- [ ] **Critical Alerts**
  - **MCP Service Down**: `up{job="mcp"} == 0` → PagerDuty
  - **High Error Rate**: `mcp_tool_errors_total > 10/5min` → Slack
  - **Slow Tool**: `mcp_tool_duration_seconds{quantile="0.95"} > 10s` → Email

- [ ] **Warning Alerts**
  - **Rate Limit Hit**: `rate_limit_exceeded_total > 5/1min` → Slack
  - **Cache Misses**: `cache_miss_rate > 80%` → Email
  - **Tool Not Used**: `mcp_tool_invocations_total{tool="X"} == 0/24h` → Slack

### Dashboards

- [ ] **MCP Overview Dashboard**
  - Tool invocation rate (7d trend)
  - P95 latency by tool (heatmap)
  - Error rate by tool (stacked area)
  - Active tools (table)

- [ ] **Tool-Specific Dashboards**
  - `audit_file`: Findings distribution, policy usage
  - `excel_analyzer`: File size distribution, operation breakdown
  - `viz_tool`: Chart type popularity, library usage

---

## Operational Guidelines

### Deployment

1. **Pre-Deployment Checks**
   - Run full test suite: `make test-all`
   - Generate OpenAPI schema: `make generate-openapi`
   - Update CHANGELOG.md
   - Tag release: `git tag v1.0.0-mcp`

2. **Canary Deployment**
   - Deploy to 10% of production pods
   - Monitor metrics for 1 hour
   - If error rate <1%, roll out to 100%

3. **Rollback Procedure**
   - Revert git commit: `git revert <commit>`
   - Redeploy previous version
   - Set feature flag: `MCP_ENABLED=false`
   - Investigate root cause in staging

### Incident Response

1. **Severity Levels**
   - **P0 (Critical)**: MCP service down, all tools unavailable
   - **P1 (High)**: Single tool down, error rate >10%
   - **P2 (Medium)**: Slow performance, latency P95 >5s
   - **P3 (Low)**: Non-functional issue, cosmetic bug

2. **Incident Workflow**
   - P0/P1: Page on-call engineer immediately
   - P2: Create ticket, resolve within 24h
   - P3: Create ticket, resolve within 1 week

3. **Postmortem Template**
   - **Incident Summary**: What happened?
   - **Root Cause**: Why did it happen?
   - **Resolution**: How was it fixed?
   - **Action Items**: Prevent recurrence

### Capacity Planning

- **Tool Usage Projections**
  - Audit file: 1000 calls/day (current baseline)
  - Excel analyzer: 500 calls/day (estimated)
  - Viz tool: 200 calls/day (estimated)

- **Resource Allocation**
  - CPU: 2 vCPU per API pod
  - Memory: 4 GB per API pod
  - Horizontal scaling: 3-10 pods based on load

- **Database Sizing**
  - MongoDB: 100 GB storage (6 months retention)
  - Redis: 4 GB memory (1 hour TTL for cache)

### Backup & Recovery

- **Database Backups**
  - MongoDB: Daily snapshots, retain 30 days
  - Redis: No backups (ephemeral cache)

- **Disaster Recovery**
  - RTO (Recovery Time Objective): 1 hour
  - RPO (Recovery Point Objective): 24 hours
  - Failover to backup region (AWS us-west-2 → us-east-1)

---

## Compliance & Audit

### Regulatory Requirements

- [ ] **SOC 2 Type II**
  - Annual audit by third party
  - Evidence: Access logs, change logs, incident reports

- [ ] **GDPR**
  - Right to data deletion
  - Right to data export
  - Consent management

- [ ] **HIPAA** *(If handling healthcare data)*
  - Encrypt data at rest (AES-256)
  - Encrypt data in transit (TLS 1.2+)
  - Access controls (RBAC)

### Audit Trails

- [ ] **User Activity Logs**
  - Track: `user_id`, `tool`, `payload_hash`, `timestamp`, `result_status`
  - Store: MongoDB `mcp_audit_log` collection
  - Export: CSV for compliance audits

- [ ] **Admin Activity Logs**
  - Track: Feature flag changes, tool registration/unregistration
  - Store: Separate `admin_audit_log` collection
  - Alerts: Email on critical changes

### Penetration Testing

- [ ] **Annual Pentest**
  - Hire external security firm
  - Scope: API endpoints, auth flows, data access
  - Remediate findings within 30 days

- [ ] **Bug Bounty Program**
  - Launch on HackerOne/Bugcrowd
  - Rewards: $100-$5000 based on severity
  - In-scope: Authentication, authorization, injection

---

## Acceptance Criteria

### Security

- [x] All MCP endpoints require authentication
- [x] User context validated for document access
- [x] Input validation implemented per tool
- [x] Rate limiting configured per tool
- [x] Timeout enforcement per tool
- [ ] Audit logging enabled *(Future)*
- [ ] RBAC implemented *(Future)*

### Observability

- [x] Structured logging with `structlog`
- [x] Metrics exported (invocation count, latency, errors)
- [x] OpenTelemetry spans created
- [x] Health check endpoint available
- [ ] Dashboards created in Grafana *(Future)*
- [ ] Alerts configured in PagerDuty *(Future)*

### Operations

- [ ] Canary deployment process documented
- [ ] Rollback procedure tested
- [ ] Incident response playbook created
- [ ] Capacity planning reviewed quarterly
- [ ] Database backups tested monthly

---

## References

- [MCP Architecture](./MCP_ARCHITECTURE.md)
- [Migration Plan](./MCP_MIGRATION_PLAN.md)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [OpenTelemetry Best Practices](https://opentelemetry.io/docs/concepts/observability-primer/)
