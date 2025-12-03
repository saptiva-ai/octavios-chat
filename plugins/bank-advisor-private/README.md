# BankAdvisor MCP Server

[![Status](https://img.shields.io/badge/Status-Production%20Ready-success)]()
[![Version](https://img.shields.io/badge/Version-1.2.0-blue)]()
[![Protocol](https://img.shields.io/badge/Protocol-MCP-orange)]()

**BankAdvisor** es un sistema de analítica bancaria avanzada que permite consultar métricas de la CNBV mediante lenguaje natural, generando visualizaciones interactivas en tiempo real.

---

## 🚀 Capacidades Principales

### 📊 5 Preguntas de Negocio Críticas (Production Ready)
El sistema responde con precisión y visualizaciones específicas a las siguientes preguntas de negocio (y sus variantes):

1.  **IMOR INVEX vs Mercado**: *"¿Cuál es el IMOR de INVEX vs el mercado?"*
    *   ✅ Gráfica comparativa dual (Líneas + Sombreado).
    *   ✅ Cálculo de spread (puntos porcentuales) y análisis de tendencia.
2.  **Market Share (PDM)**: *"¿Cómo está mi PDM medido por cartera total?"*
    *   ✅ Gráfica de Pay (Pie Chart) + Evolución temporal.
    *   ✅ Ranking automático en el sistema.
3.  **Evolución Cartera Consumo**: *"¿Cómo ha evolucionado la cartera de consumo en el último trimestre?"*
    *   ✅ Gráfica de Cascada (Waterfall) mostrando variaciones mensuales.
    *   ✅ Análisis de crecimiento porcentual QoQ (Quarter-over-Quarter).
4.  **IMOR Automotriz**: *"¿Cómo está mi IMOR en cartera automotriz frente al mercado?"*
    *   ✅ Detección de segmentos específicos.
    *   ✅ Manejo inteligente de datos faltantes (ej. INVEX no tiene cartera automotriz).
5.  **Ranking por Activos**: *"¿Cuál es el tamaño de los bancos por activos?"*
    *   ✅ Gráfica de Barras Horizontales (Top 20).
    *   ✅ Cálculo de % del sistema y % del mercado privado.

### 🧠 Inteligencia Híbrida NL2SQL
*   **Clasificación Híbrida**: 80% de las queries se resuelven con reglas determinísticas (<20ms), usando LLM solo para desambiguación.
*   **RAG Feedback Loop**: Sistema de aprendizaje continuo que indexa queries exitosas en Qdrant para mejorar la precisión futura.
*   **Multilingual Support**: Entiende consultas en español e inglés ("IMOR de INVEX", "Show me the IMOR").

### 🏭 Arquitectura de Datos Robusta
*   **Dual ETL System**:
    *   **Legacy Pipeline**: Procesa históricos 2017-2025 para métricas tradicionales (`monthly_kpis`).
    *   **Normalized Pipeline**: Procesa reportes complejos (BE_BM_202509) para balances, estados de resultados y segmentación detallada.
*   **Data Quality**: Validaciones automáticas de integridad referencial y rangos de valores.

---

## 🛠️ Quick Start

### Prerrequisitos
*   Docker & Docker Compose
*   Make (opcional, para comandos rápidos)

### 1. Construir e Iniciar
```bash
make dev-rebuild
# O manualmente:
# docker-compose build bank-advisor && docker-compose up -d bank-advisor
```

### 2. Inicializar Datos (Migraciones + ETL)
Este comando ejecuta las migraciones de base de datos, carga los históricos (Legacy) y procesa los reportes detallados (Normalized).

```bash
make init-bank-advisor
```

*Tiempo estimado: ~3-4 minutos (procesa >100 meses de historia bancaria)*

### 3. Verificar Estado
```bash
curl http://localhost:8002/health | jq
```
Debe retornar `status: "healthy"` y detalles de la última ejecución del ETL.

### 4. Ejecutar Smoke Test
Valida que las 5 preguntas de negocio y las visualizaciones estén funcionando correctamente:

```bash
cd plugins/bank-advisor-private
./test_5_questions.sh
```

---

## 📚 Documentación

La documentación ha sido reorganizada para facilitar la navegación:

### 🔹 Core (Arquitectura y Diseño)
*   [Architecture Overview](docs/core/ARCHITECTURE.md): Principios SOLID, diagrama de sistema.
*   [NL2SQL Design](docs/core/nl2sql_design.md): Diseño del motor de lenguaje natural.
*   [RAG Design](docs/core/nl2sql_rag_design.md): Arquitectura del sistema de feedback loop.

### 🔹 Features (Funcionalidades)
*   [5 Business Questions](docs/features/DISEÑO_INTEGRACION_5_PREGUNTAS.md): Diseño detallado de las preguntas principales.
*   [9 Priority Visualizations](docs/features/9_PRIORITY_VISUALIZATIONS.md): Catálogo de visualizaciones implementadas.
*   [Frontend Integration](docs/features/FRONTEND_INTEGRATION.md): Integración con OctaviOS UI.
*   [ETL Consolidation](docs/features/ETL_CONSOLIDATION.md): Explicación del sistema de datos dual.

### 🔹 Reports (Validación y Status)
*   [Implementation Summary](docs/reports/IMPLEMENTATION_SUMMARY.md): Estado actual de implementación.
*   [Data Validation](docs/reports/VALIDACION_COMPLETA.md): Evidencia de precisión de datos (INVEX vs CNBV).
*   [QA Results](docs/reports/QA_TEST_RESULTS.md): Resultados de pruebas de calidad.

---

## 🧪 Testing

El proyecto cuenta con una suite de pruebas exhaustiva:

| Tipo | Comando | Propósito |
|------|---------|-----------|
| **Smoke Test** | `./test_5_questions.sh` | Valida las 5 preguntas críticas de negocio. |
| **Demo Test** | `python scripts/smoke_demo_bank_analytics.py` | Valida las 12 queries del demo general. |
| **Adversarial** | `pytest -m nl2sql_dirty` | Prueba inyecciones SQL y queries maliciosas. |
| **Unit** | `pytest src/bankadvisor/tests/` | Pruebas unitarias de servicios. |
| **ETL Ops** | `python scripts/ops_validate_etl.py` | Valida la integridad de los datos cargados. |

---

## 🏗️ Project Structure

```text
plugins/bank-advisor-private/
├── config/                 # Configuraciones (synonyms, profiles)
├── data/                   # Datos raw (CNBV Excel/CSV)
├── docs/                   # Documentación organizada (core, features, reports)
├── etl/                    # Scripts de ETL (Extract, Transform, Load)
├── migrations/             # Scripts SQL de migración
├── scripts/                # Herramientas de operación y testing
├── src/                    # Código fuente de la aplicación
│   ├── bankadvisor/        # Lógica de negocio
│   │   ├── services/       # Analytics, Intent, SQL Generation
│   │   └── models/         # Modelos Pydantic/SQLAlchemy
│   └── main.py             # Entrypoint FastAPI / MCP
└── tests/                  # Tests de integración y E2E
```

---

## 🛡️ Security & Performance

*   **Read-Only**: El usuario de base de datos para consultas NL2SQL es de solo lectura.
*   **SQL Sanitization**: Validación estricta de queries generadas para prevenir inyección.
*   **Performance**:
    *   p50 Latency: **16ms** (Ratios/Reglas).
    *   p95 Latency: **200ms** (Timelines/DB).
    *   Consultas complejas: ~1.5s (requieren LLM reasoning).

---

**Maintainers:** OctaviOS Team
**License:** Private / Proprietary