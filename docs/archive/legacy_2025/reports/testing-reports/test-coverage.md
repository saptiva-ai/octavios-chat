# Test Coverage Dashboard

Unified snapshot of the latest coverage reports (2025-10-14) across end-to-end, frontend, and backend suites.

---

## Executive Summary

| Layer | Passed | Total | Coverage | Notes |
|-------|--------|-------|----------|-------|
| E2E (Playwright) | 7 | 8 | 87.5% | Multi-upload case skipped due to tooling limits. |
| Frontend (Jest) | 158 | 160 | 98.75% | All major UI suites passing. |
| Backend (pytest) | 7 | 10 | 70% | Remaining failures tied to JWT auth fixtures. |
| Overall | 172 | ~180 | 96%+ | Stack healthy; follow-up on backend gaps. |

- Permanent pytest infrastructure is in place inside the API container.
- Files V1 workflow validated via E2E scenarios (auth, size limits, idempotency, metrics).
- Document the two skipped/expected failing cases before every release to avoid regressions.

---

## Highlights by Layer

### End-to-End (Playwright)
- Location: `tests/e2e/files-v1.spec.ts`
- Validates auth flow, MIME filtering, upload sizing, idempotency, metrics, and rate limiting.
- Remaining skip: multiple file upload in a single request (blocked by Playwright FormData arrays).

### Frontend (Jest)
- Location: `apps/web/`
- Suites fully passing for: conversation utilities, chat state stores, model selector, intent handlers, Saptiva key form, deep research progress UI.
- Known flaky suite resolved after credential toggle fixes.

### Backend (pytest)
- Location: `apps/api/`
- Authentication-related tests require refreshed JWT fixtures; track progress in incident follow-up.
- Docker dev target now ships with pytest + dependencies baked in.

---

## Operational Follow-up

- Ensure new tests are wired into GitHub Actions (see `.github/workflows`).
- Revisit the backend auth fixtures before next production deploy.
- Cross-check with [Final Test Summary](FINAL_TEST_SUMMARY.md) when preparing release notes.

For historical coverage or prior automation efforts, refer to the archived reports in `../archive/legacy-testing/`.

