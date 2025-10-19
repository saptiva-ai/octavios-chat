# Production Deployment Playbook

This runbook consolidates everything needed to ship Copilotos Bridge to production safely. It unifies the previous quick deploy cheat-sheet, the extended production guide, the pre-deployment checklist, and the rollback/versioning notes into a single source of truth.

---

## Security & Readiness Baseline

- Run `make security-audit` before every deploy.
- Ensure `envs/.env.prod` exists with production values only (no dev keys).
- Confirm backups are healthy (`make backup-status`); see [backup setup](backup-setup.md).
- Work from a clean `main` branch (`git status` must be clean).
- All tests must pass locally (`make test-all`).

> **Tip:** If anything in this section fails, stop the deployment and fix the issue first.

---

## Deployment Options at a Glance

| Command | Duration | When to Use | Notes |
|---------|----------|-------------|-------|
| `make deploy-tar` (alias `make deploy`) | 8-12 min | Flujo principal con build completo | Versionado + health checks automáticos. |
| `make deploy-fast` | 2-3 min | Reusar imágenes ya construidas | Sin rebuild, ideal para hotfix UI. |
| `make deploy-registry` | 3-5 min | Infra con registry configurado | Descarga imágenes publicadas previamente. |
| `make deploy-prod` | 4-6 min | Build local + push + deploy remoto | Requiere credenciales del registry. |

All commands run the same health checks and rollback hooks described below.

---

## Pre-Deployment Checklist (10 min)

1. **Git hygiene**
   - `git status` -> clean.
   - `git log --oneline -5` -> review pending commits.
2. **Local validation**
   - `make test-all`.
   - `docker compose -f infra/docker-compose.yml build`.
3. **Secrets & credentials**
   - `make generate-credentials` if rotating secrets.
   - Verify `SAPTIVA_API_KEY`, `MONGODB_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET_KEY` in `envs/.env.prod`.
4. **Backups**
   - `make backup-mongodb-prod` (manual snapshot).
   - Confirm backup artifacts under `~/backups/mongodb`.
5. **Server readiness**
   - `ssh <user>@<host> "df -h && free -h"` -> check disk/RAM.
   - `ssh <user>@<host> "docker ps"` -> services healthy.

Every item must be OK before promoting code.

---

## Standard Deployment Flow (`make deploy-tar`)

1. **Trigger deploy**
   ```bash
   make deploy
   ```
   - Builds versioned images (`api:web:<git-sha>-<timestamp>`).
   - Transfers tar package.
   - Brings services up with `docker compose`.
   - Runs automated health checks (API + web).

2. **Monitor console output**
   - Look for OK health check confirmation.
   - On failure you will see an automatic rollback (details below).

3. **Post deploy verification**
   ```bash
   make deploy-status
   ssh <user>@<host> "docker ps && curl -s http://localhost:8001/api/health | jq '.'"
   ```

4. **Smoke test**
   - Open production web.
   - Upload sample file.
   - Check logs: `ssh <user>@<host> "docker logs -f copilotos-api"`.

---

## Registry Workflow (Optional)

When pushing images to GitHub Container Registry:

```bash
# Local machine
./scripts/push-to-registry.sh

# Production server
ssh <user>@<host>
cd ~/copilotos-bridge
./scripts/deploy-from-registry.sh
```

The script handles login, tagging (`latest` + commit SHA) and service restarts. Use `make deploy-registry` if you prefer the Makefile wrapper.

---

## Rollback & Version Pinning

Deployments are versioned automatically (`<git-sha>-<timestamp>`). Use these commands when things break:

```bash
# manual rollback to previous version
make rollback

# rollback to a specific version
./scripts/rollback.sh <version-id>
```

Rollback flow:
1. Stop services.
2. Restore previous image bundle.
3. Restart containers.
4. Re-run health checks.

If health checks fail after a deploy, the automation runs this flow without manual intervention. Always review `logs/deploy/*.log` afterward and create an incident report if applicable.

---

## Common Pitfalls & Fixes

- **Credentials rotated but services still failing:** ensure you ran `docker compose down` + `up -d` rather than `restart`. See `credentials.md`.
- **Old UI after deploy:** clear cache `make clear-cache` or run `ssh <user>@host "./scripts/clear-server-cache.sh"`.
- **Type errors blocking build:** reproduce el build con `./scripts/deploy.sh tar --dry-run` y corrige antes de volver a desplegar.
- **Persistent 500s post deploy:** check recent incidents in `operations/incidents/`.

---

## Related Runbooks

- [Credential rotation & secrets management](credentials.md)
- [Backup & disaster recovery](backup-setup.md) - [Disaster recovery drills](disaster-recovery.md)
- [Incident archive](incidents/)
- [Troubleshooting cookbook](troubleshooting.md)

