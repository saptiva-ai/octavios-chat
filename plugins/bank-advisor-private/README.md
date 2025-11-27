# BankAdvisor MCP Server - Enterprise Banking Analytics

**Status:** ✅ Production Ready (Migrated from Monolith)
**Version:** 1.0.0
**Protocol:** MCP (Model Context Protocol) via SSE
**Type:** Private Enterprise Plugin

---

## 📋 Overview

BankAdvisor es un microservicio independiente que expone analytics bancarios vía MCP (Model Context Protocol). Este servicio fue desacoplado del monolito `octavios-core` para mantener la arquitectura limpia y permitir deploy independiente.

### Arquitectura

```
┌─────────────────┐          MCP/SSE          ┌─────────────────┐
│  octavios-core  │ ◄──────────────────────► │  bank-advisor   │
│  (Cliente MCP)  │  http://bank-advisor:8000 │  (Servidor MCP) │
└─────────────────┘                           └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌──────────────┐
                                              │  PostgreSQL  │
                                              │  (INVEX DB)  │
                                              └──────────────┘
```

**Flujo de datos:**
1. Usuario hace query en OctaviOS
2. Core detecta intent bancario → llama tool `bank_analytics` via MCP
3. BankAdvisor ejecuta SQL con security hardening
4. Retorna Plotly config + datos
5. Frontend renderiza dashboard

---

## 🔒 Security Hardening

Este servicio incluye **3 CVEs corregidos** (ver commit `f9dcb9e`):

- **CVE-001**: Whitelist `SAFE_METRIC_COLUMNS` (previene attribute injection)
- **CVE-002**: Fuzzy matching hardened (cutoff 0.8)
- **CVE-003**: 3-tier error handling (400/503/500)

**Test de Penetración:** 8/8 vectores de ataque bloqueados.

---

## 🚀 Quick Start

### Requisitos
- Docker & Docker Compose
- PostgreSQL 15 (auto-configurado en docker-compose)
- Python 3.11+ (si desarrollo local)

### Levantar el Servicio

```bash
# Desde la raíz del proyecto
docker compose -f infra/docker-compose.yml up -d postgres bank-advisor

# Verificar health
curl http://localhost:8002/health
# {"status":"healthy","service":"bank-advisor-mcp","version":"1.0.0"}
```

### Conectar desde OctaviOS Core

El core ya está configurado automáticamente con:

```yaml
# infra/docker-compose.yml (servicio API)
environment:
  - MCP_SERVERS_URLS=["http://bank-advisor:8000/sse"]
```

---

## 🛠️ API Reference

### MCP Tool: `bank_analytics`

**Endpoint:** `http://bank-advisor:8000/sse` (SSE Stream)

**Tool Name:** `bank_analytics`

**Parameters:**
```python
{
  "metric_or_query": str,  # "cartera comercial", "IMOR", etc.
  "mode": str              # "dashboard" | "timeline" (default: dashboard)
}
```

**Response:**
```json
{
  "data": {
    "months": [...],  // 103 meses de datos
    "metadata": {...}
  },
  "plotly_config": {...},  // Config para Plotly.js
  "title": "Cartera Comercial Total",
  "data_as_of": "01/07/2025"
}
```

**Error Handling:**
- `400` - Invalid metric (no está en whitelist)
- `503` - Database unavailable
- `500` - Internal server error

---

## 📊 Data Sources

### Raw Data Files (`data/raw/`)
- `CNBV_Cartera_Bancos_V2.xlsx` - Carteras por banco (CNBV)
- `CorporateLoan_CNBVDB.csv` - Préstamos corporativos (228MB)
- `ICAP_Bancos.xlsx` - Índice de Capitalización
- `TDA.xlsx` - Tasa de Descuento Anualizada
- `TE_Invex_Sistema.xlsx` - Tasas de Interés
- `Instituciones.xlsx` - Catálogo de instituciones
- `CASTIGOS.xlsx` - Castigos y recuperaciones

### Database Schema

**Table:** `monthly_kpis`

**Columns (15 métricas):**
- `cartera_total`, `cartera_comercial_total`, `cartera_consumo_total`
- `cartera_vivienda_total`, `entidades_gubernamentales_total`
- `entidades_financieras_total`, `empresarial_total`
- `cartera_vencida`, `imor`, `icor`
- `reservas_etapa_todas`, `tasa_mn`, `tasa_me`
- `icap_total`, `tda_cartera_total`

**Period:** 2017-01 → 2025-07 (103 meses)

---

## 🧪 Testing

### E2E Test (Local)

```bash
cd plugins/bank-advisor-private

# Asegurarse de que PostgreSQL esté corriendo
docker compose -f ../../infra/docker-compose.yml up -d postgres

# Ejecutar tests E2E (usa el script del monolito original)
# Los tests están en: apps/api/scripts/test_bankadvisor_e2e.py
# Necesitan ser adaptados para apuntar al servicio MCP
```

### Security Penetration Test

```bash
# Test que valida que los 8 vectores de ataque son bloqueados
python -c "
import asyncio
import httpx

async def test():
    malicious_inputs = [
        '__class__', 'metadata', '__dict__',
        'DROP TABLE monthly_kpis', '../../../etc/passwd'
    ]

    async with httpx.AsyncClient() as client:
        for inp in malicious_inputs:
            resp = await client.post(
                'http://localhost:8002/tools/bank_analytics',
                json={'metric_or_query': inp, 'mode': 'dashboard'}
            )
            print(f'{inp}: {resp.status_code} - {resp.json().get(\"error\")}')

asyncio.run(test())
"
```

---

## 🔧 Development

### Local Development (sin Docker)

```bash
cd plugins/bank-advisor-private

# Crear virtualenv
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar env vars
export DATABASE_URL="postgresql+asyncpg://octavios:password@localhost:5432/bankadvisor"
export LOG_LEVEL=DEBUG

# Ejecutar servidor
python -m src.main
```

### Hot Reload (Development)

```bash
# Modificar Dockerfile para habilitar reload
uvicorn.run(
    "src.main:mcp",
    host="0.0.0.0",
    port=8000,
    reload=True  # Cambiar a True
)
```

---

## 📝 Maintenance

### ETL Re-Execution

El servicio ejecuta ETL automáticamente si la base de datos está vacía (ver `src/main.py:ensure_data_populated()`).

Para forzar re-ejecución:

```bash
docker exec octavios-chat-bajaware_invex-postgres psql \
  -U octavios -d bankadvisor \
  -c "TRUNCATE TABLE monthly_kpis;"

docker restart octavios-chat-bajaware_invex-bank-advisor
```

### Logs

```bash
# Ver logs del servicio
docker logs -f octavios-chat-bajaware_invex-bank-advisor

# Ver logs de PostgreSQL
docker logs -f octavios-chat-bajaware_invex-postgres
```

---

## 🚨 Troubleshooting

### Error: "Connection refused"
**Causa:** PostgreSQL no está saludable.
**Fix:**
```bash
docker compose -f infra/docker-compose.yml restart postgres
```

### Error: "No data found"
**Causa:** ETL no se ejecutó.
**Fix:**
```bash
docker exec octavios-chat-bajaware_invex-bank-advisor python -m src.bankadvisor.etl_loader
```

### Error: "Métrica no autorizada"
**Causa:** Query usa métrica fuera del whitelist.
**Fix:** Verificar que la métrica esté en `SAFE_METRIC_COLUMNS` (src/bankadvisor/services/analytics_service.py:31-54)

---

## 📚 Documentation

- **Security Audit Report:** `../../docs/bankadvisor/DEPLOYMENT.md`
- **Architecture Decision:** ADR-001 (este README)
- **MCP Protocol Spec:** https://spec.modelcontextprotocol.io/

---

## 👥 Contributors

- **Security Hardening:** Commit `f9dcb9e` (24 Nov 2025)
- **Microservice Migration:** Commit `<current>` (25 Nov 2025)

---

## 📄 License

**Private Enterprise Plugin** - Confidencial INVEX
