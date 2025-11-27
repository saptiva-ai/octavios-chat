#!/usr/bin/env python3
"""
RAG Seeding Script for NL2SQL Collections

Seeds Qdrant vector database with:
1. Schema metadata (columns, tables, data types)
2. Metric definitions (formulas, aliases, descriptions)
3. Example NL→SQL pairs (few-shot learning)

Usage:
    python scripts/seed_nl2sql_rag.py [--clear] [--collections schema,metrics,examples]

Options:
    --clear              Clear existing collections before seeding
    --collections        Comma-separated list of collections to seed (default: all)
    --dry-run            Print what would be seeded without actually doing it

Requirements:
    - Qdrant running and accessible
    - Embedding service initialized
    - RAG bridge configured
"""

import asyncio
import argparse
from typing import List, Dict, Any
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import structlog
from bankadvisor.services.rag_bridge import get_rag_bridge
from bankadvisor.services.nl2sql_context_service import Nl2SqlContextService

logger = structlog.get_logger(__name__)


# ============================================================================
# SEED DATA DEFINITIONS
# ============================================================================

SCHEMA_SEED_DATA = [
    {
        "table_name": "monthly_kpis",
        "column_name": "fecha",
        "data_type": "date",
        "description": "Fecha del reporte mensual en formato YYYY-MM-DD. Columna obligatoria para series de tiempo.",
        "metric_tags": ["temporal", "required"],
        "example_sql": "SELECT fecha FROM monthly_kpis WHERE fecha >= '2024-01-01'",
        "is_nullable": False,
        "typical_range": None
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "banco_nombre",
        "data_type": "string",
        "description": "Nombre del banco o 'SISTEMA' para el promedio del sistema financiero. Valores: INVEX, SISTEMA",
        "metric_tags": ["dimension", "filter"],
        "example_sql": "SELECT * FROM monthly_kpis WHERE banco_nombre = 'INVEX'",
        "is_nullable": False,
        "typical_range": None
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "imor",
        "data_type": "float",
        "description": "Índice de Morosidad - Ratio de cartera vencida sobre cartera total. Indicador clave de calidad crediticia.",
        "metric_tags": ["quality", "risk", "ratio"],
        "example_sql": "SELECT fecha, imor FROM monthly_kpis WHERE banco_nombre = 'INVEX' ORDER BY fecha",
        "is_nullable": False,
        "typical_range": {"min": 0.0, "max": 10.0}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "icor",
        "data_type": "float",
        "description": "Índice de Cobertura - Ratio de reservas sobre cartera vencida. Mide la capacidad de absorción de pérdidas.",
        "metric_tags": ["quality", "reserves", "ratio"],
        "example_sql": "SELECT fecha, icor FROM monthly_kpis WHERE banco_nombre = 'SISTEMA'",
        "is_nullable": False,
        "typical_range": {"min": 50.0, "max": 200.0}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "cartera_total",
        "data_type": "float",
        "description": "Cartera de crédito total en millones de pesos. Suma de todas las líneas de crédito.",
        "metric_tags": ["portfolio", "volume", "aggregate"],
        "example_sql": "SELECT fecha, cartera_total FROM monthly_kpis WHERE banco_nombre = 'INVEX'",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 1000000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "cartera_comercial_total",
        "data_type": "float",
        "description": "Cartera comercial total en millones de pesos. Créditos empresariales y comerciales.",
        "metric_tags": ["portfolio", "commercial", "segment"],
        "example_sql": "SELECT fecha, cartera_comercial_total FROM monthly_kpis",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 500000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "cartera_consumo_total",
        "data_type": "float",
        "description": "Cartera de consumo total en millones de pesos. Créditos personales y tarjetas de crédito.",
        "metric_tags": ["portfolio", "consumer", "segment"],
        "example_sql": "SELECT fecha, cartera_consumo_total FROM monthly_kpis",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 200000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "cartera_vivienda_total",
        "data_type": "float",
        "description": "Cartera de vivienda total en millones de pesos. Créditos hipotecarios.",
        "metric_tags": ["portfolio", "mortgage", "segment"],
        "example_sql": "SELECT fecha, cartera_vivienda_total FROM monthly_kpis",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 300000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "cartera_vencida",
        "data_type": "float",
        "description": "Cartera vencida total en millones de pesos. Créditos con mora mayor a 90 días.",
        "metric_tags": ["quality", "risk", "delinquency"],
        "example_sql": "SELECT fecha, cartera_vencida FROM monthly_kpis WHERE banco_nombre = 'INVEX'",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 50000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "reservas_etapa_todas",
        "data_type": "float",
        "description": "Reservas para créditos incobrables totales en millones de pesos. Todas las etapas de deterioro.",
        "metric_tags": ["reserves", "provisions", "risk"],
        "example_sql": "SELECT fecha, reservas_etapa_todas FROM monthly_kpis",
        "is_nullable": False,
        "typical_range": {"min": 0, "max": 100000}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "icap_total",
        "data_type": "float",
        "description": "Índice de Capitalización total. Ratio de capital sobre activos ponderados por riesgo.",
        "metric_tags": ["capital", "solvency", "ratio"],
        "example_sql": "SELECT fecha, icap_total FROM monthly_kpis WHERE icap_total IS NOT NULL",
        "is_nullable": True,
        "typical_range": {"min": 10.0, "max": 30.0}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "tda_cartera_total",
        "data_type": "float",
        "description": "Tasa de Deterioro Anual de cartera total. Porcentaje de deterioro crediticio.",
        "metric_tags": ["quality", "deterioration", "ratio"],
        "example_sql": "SELECT fecha, tda_cartera_total FROM monthly_kpis WHERE tda_cartera_total IS NOT NULL",
        "is_nullable": True,
        "typical_range": {"min": 0.0, "max": 5.0}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "tasa_mn",
        "data_type": "float",
        "description": "Tasa de interés promedio en moneda nacional (MXN). Porcentaje anual.",
        "metric_tags": ["rates", "pricing", "revenue"],
        "example_sql": "SELECT fecha, tasa_mn FROM monthly_kpis WHERE tasa_mn IS NOT NULL",
        "is_nullable": True,
        "typical_range": {"min": 5.0, "max": 25.0}
    },
    {
        "table_name": "monthly_kpis",
        "column_name": "tasa_me",
        "data_type": "float",
        "description": "Tasa de interés promedio en moneda extranjera (USD). Porcentaje anual. NOTA: Actualmente sin datos.",
        "metric_tags": ["rates", "pricing", "forex"],
        "example_sql": "SELECT fecha, tasa_me FROM monthly_kpis WHERE tasa_me IS NOT NULL",
        "is_nullable": True,
        "typical_range": {"min": 2.0, "max": 15.0}
    },
]

METRICS_SEED_DATA = [
    {
        "metric_name": "IMOR",
        "aliases": ["morosidad", "npm", "non-performing", "cartera vencida ratio"],
        "formula": "cartera_vencida / cartera_total * 100",
        "description": "Índice de Morosidad - Mide el porcentaje de créditos vencidos sobre el total de la cartera",
        "preferred_columns": ["imor"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "IMOR de INVEX últimos 6 meses",
            "Compara morosidad INVEX vs Sistema 2024",
            "Tendencia de IMOR histórica"
        ],
        "data_status": "populated",
        "interpretation": "Menor es mejor. >5% es alto riesgo, <2% es excelente"
    },
    {
        "metric_name": "ICOR",
        "aliases": ["cobertura", "coverage ratio", "reservas ratio"],
        "formula": "reservas_etapa_todas / cartera_vencida * 100",
        "description": "Índice de Cobertura - Mide el porcentaje de reservas sobre cartera vencida",
        "preferred_columns": ["icor"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "ICOR de INVEX últimos 3 meses",
            "Cobertura histórica del sistema",
            "Compara ICOR INVEX vs Sistema"
        ],
        "data_status": "populated",
        "interpretation": "Mayor es mejor. >100% es saludable, <80% requiere atención"
    },
    {
        "metric_name": "CARTERA_TOTAL",
        "aliases": ["cartera", "portfolio total", "créditos totales"],
        "formula": "SUM(all credit lines)",
        "description": "Cartera de crédito total - Volumen total de créditos otorgados",
        "preferred_columns": ["cartera_total"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "Cartera total de INVEX",
            "Evolución de cartera últimos 12 meses",
            "Compara volumen INVEX vs Sistema"
        ],
        "data_status": "populated",
        "interpretation": "Indicador de tamaño y actividad crediticia"
    },
    {
        "metric_name": "CARTERA_COMERCIAL",
        "aliases": ["comercial", "empresarial", "corporate loans"],
        "formula": "Commercial credit portfolio",
        "description": "Cartera comercial - Créditos a empresas y negocios",
        "preferred_columns": ["cartera_comercial_total"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "Cartera comercial de INVEX",
            "Evolución comercial 2024",
            "Compara cartera empresarial"
        ],
        "data_status": "populated",
        "interpretation": "Segmento clave para análisis crediticio"
    },
    {
        "metric_name": "CARTERA_CONSUMO",
        "aliases": ["consumo", "consumer loans", "retail"],
        "formula": "Consumer credit portfolio",
        "description": "Cartera de consumo - Créditos personales y tarjetas",
        "preferred_columns": ["cartera_consumo_total"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "Cartera de consumo de INVEX",
            "Evolución retail últimos 6 meses"
        ],
        "data_status": "populated",
        "interpretation": "Indicador de penetración retail"
    },
    {
        "metric_name": "ICAP",
        "aliases": ["capitalización", "capital ratio", "solvencia"],
        "formula": "capital / risk_weighted_assets * 100",
        "description": "Índice de Capitalización - Solvencia del banco",
        "preferred_columns": ["icap_total"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "ICAP de INVEX últimos 3 meses",
            "Capitalización histórica"
        ],
        "data_status": "populated",
        "interpretation": "Regulatorio mínimo 10.5%, >15% es robusto"
    },
    {
        "metric_name": "TDA",
        "aliases": ["deterioro", "tasa deterioro", "credit deterioration"],
        "formula": "Annualized deterioration rate",
        "description": "Tasa de Deterioro Anual - Velocidad de deterioro crediticio",
        "preferred_columns": ["tda_cartera_total"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "TDA de INVEX en 2024",
            "Deterioro histórico del sistema"
        ],
        "data_status": "populated",
        "interpretation": "Menor es mejor. >3% indica deterioro acelerado"
    },
    {
        "metric_name": "TASA_MN",
        "aliases": ["tasa pesos", "interés mn", "rate mxn"],
        "formula": "Weighted average lending rate (MXN)",
        "description": "Tasa de interés promedio en moneda nacional",
        "preferred_columns": ["tasa_mn"],
        "requires_banks": False,
        "typical_viz": "line",
        "example_queries": [
            "TASA_MN de INVEX últimos 12 meses",
            "Evolución de tasas 2024"
        ],
        "data_status": "populated",
        "interpretation": "Indicador de pricing y rentabilidad"
    },
]

EXAMPLES_SEED_DATA = [
    {
        "natural_language": "IMOR de INVEX últimos 3 meses",
        "query_spec": {
            "metric": "IMOR",
            "bank_names": ["INVEX"],
            "time_range": {"type": "last_n_months", "n": 3},
            "granularity": "month",
            "visualization_type": "line"
        },
        "sql": """SELECT fecha, imor
FROM monthly_kpis
WHERE banco_nombre = 'INVEX'
  AND fecha >= (CURRENT_DATE - INTERVAL '3 months')
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "Standard time-series query with single bank filter",
        "complexity": "simple"
    },
    {
        "natural_language": "Compara IMOR INVEX vs Sistema 2024",
        "query_spec": {
            "metric": "IMOR",
            "bank_names": ["INVEX", "SISTEMA"],
            "time_range": {"type": "year", "start_date": "2024-01-01", "end_date": "2024-12-31"},
            "comparison_mode": True
        },
        "sql": """SELECT fecha, banco_nombre, imor
FROM monthly_kpis
WHERE banco_nombre IN ('INVEX', 'SISTEMA')
  AND fecha >= '2024-01-01'
  AND fecha <= '2024-12-31'
ORDER BY fecha ASC, banco_nombre
LIMIT 1000""",
        "notes": "Comparison query with year filter",
        "complexity": "simple"
    },
    {
        "natural_language": "cartera comercial de INVEX",
        "query_spec": {
            "metric": "CARTERA_COMERCIAL",
            "bank_names": ["INVEX"],
            "time_range": {"type": "all"}
        },
        "sql": """SELECT fecha, cartera_comercial_total
FROM monthly_kpis
WHERE banco_nombre = 'INVEX'
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "All-time query for single metric",
        "complexity": "simple"
    },
    {
        "natural_language": "ICOR promedio de INVEX en 2024",
        "query_spec": {
            "metric": "ICOR",
            "bank_names": ["INVEX"],
            "time_range": {"type": "year", "start_date": "2024-01-01", "end_date": "2024-12-31"}
        },
        "sql": """SELECT AVG(icor) as promedio,
       MIN(icor) as minimo,
       MAX(icor) as maximo,
       COUNT(*) as meses
FROM monthly_kpis
WHERE banco_nombre = 'INVEX'
  AND fecha >= '2024-01-01'
  AND fecha <= '2024-12-31'""",
        "notes": "Aggregate query with year filter",
        "complexity": "simple"
    },
    {
        "natural_language": "ICAP de INVEX últimos 6 meses",
        "query_spec": {
            "metric": "ICAP",
            "bank_names": ["INVEX"],
            "time_range": {"type": "last_n_months", "n": 6}
        },
        "sql": """SELECT fecha, icap_total
FROM monthly_kpis
WHERE banco_nombre = 'INVEX'
  AND fecha >= (CURRENT_DATE - INTERVAL '6 months')
  AND icap_total IS NOT NULL
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "Nullable column query with IS NOT NULL filter",
        "complexity": "simple"
    },
    {
        "natural_language": "Cartera total histórica de INVEX",
        "query_spec": {
            "metric": "CARTERA_TOTAL",
            "bank_names": ["INVEX"],
            "time_range": {"type": "all"}
        },
        "sql": """SELECT fecha, cartera_total
FROM monthly_kpis
WHERE banco_nombre = 'INVEX'
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "Historical query without time filter",
        "complexity": "simple"
    },
    {
        "natural_language": "TDA del sistema financiero en 2024",
        "query_spec": {
            "metric": "TDA",
            "bank_names": ["SISTEMA"],
            "time_range": {"type": "year", "start_date": "2024-01-01", "end_date": "2024-12-31"}
        },
        "sql": """SELECT fecha, tda_cartera_total
FROM monthly_kpis
WHERE banco_nombre = 'SISTEMA'
  AND fecha >= '2024-01-01'
  AND fecha <= '2024-12-31'
  AND tda_cartera_total IS NOT NULL
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "System-level query with nullable column",
        "complexity": "simple"
    },
    {
        "natural_language": "TASA_MN últimos 12 meses",
        "query_spec": {
            "metric": "TASA_MN",
            "bank_names": [],
            "time_range": {"type": "last_n_months", "n": 12}
        },
        "sql": """SELECT fecha, tasa_mn
FROM monthly_kpis
WHERE fecha >= (CURRENT_DATE - INTERVAL '12 months')
  AND tasa_mn IS NOT NULL
ORDER BY fecha ASC
LIMIT 1000""",
        "notes": "Query without bank filter (all banks)",
        "complexity": "simple"
    },
]


# ============================================================================
# SEEDING FUNCTIONS
# ============================================================================

async def seed_schema_collection(
    context_service: Nl2SqlContextService,
    clear: bool = False,
    dry_run: bool = False
) -> int:
    """
    Seed schema collection with column metadata.

    Args:
        context_service: Nl2SqlContextService with RAG enabled
        clear: Whether to clear existing data
        dry_run: If True, print what would be seeded without actually doing it

    Returns:
        Number of points seeded
    """
    collection_name = context_service.COLLECTION_SCHEMA

    logger.info("seed_schema.start", collection=collection_name, items=len(SCHEMA_SEED_DATA), clear=clear, dry_run=dry_run)

    if dry_run:
        logger.info("seed_schema.dry_run", items_would_seed=len(SCHEMA_SEED_DATA))
        for item in SCHEMA_SEED_DATA[:3]:  # Show first 3
            logger.info("seed_schema.dry_run_item", item=item)
        return len(SCHEMA_SEED_DATA)

    # Clear collection if requested
    if clear:
        try:
            context_service.qdrant.client.delete_collection(collection_name=collection_name)
            logger.info("seed_schema.cleared", collection=collection_name)
            # Recreate
            context_service.ensure_collections()
        except Exception as e:
            logger.warning("seed_schema.clear_failed", error=str(e))

    # Generate embeddings for all items
    texts = [
        f"{item['column_name']} {item['description']} {' '.join(item['metric_tags'])}"
        for item in SCHEMA_SEED_DATA
    ]

    logger.info("seed_schema.generating_embeddings", count=len(texts))
    embeddings = context_service.embedding.encode(texts)

    # Prepare points
    from qdrant_client.models import PointStruct
    import uuid
    import hashlib

    points = []
    for i, (item, embedding) in enumerate(zip(SCHEMA_SEED_DATA, embeddings)):
        # Generate deterministic ID
        unique_str = f"{collection_name}_{item['column_name']}"
        point_id = str(uuid.UUID(hashlib.md5(unique_str.encode()).hexdigest()))

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload=item
        ))

    # Upsert to Qdrant
    context_service.qdrant.client.upsert(
        collection_name=collection_name,
        points=points
    )

    logger.info("seed_schema.complete", collection=collection_name, points_seeded=len(points))
    return len(points)


async def seed_metrics_collection(
    context_service: Nl2SqlContextService,
    clear: bool = False,
    dry_run: bool = False
) -> int:
    """Seed metrics collection with metric definitions."""
    collection_name = context_service.COLLECTION_METRICS

    logger.info("seed_metrics.start", collection=collection_name, items=len(METRICS_SEED_DATA), clear=clear, dry_run=dry_run)

    if dry_run:
        logger.info("seed_metrics.dry_run", items_would_seed=len(METRICS_SEED_DATA))
        for item in METRICS_SEED_DATA[:3]:
            logger.info("seed_metrics.dry_run_item", item=item)
        return len(METRICS_SEED_DATA)

    if clear:
        try:
            context_service.qdrant.client.delete_collection(collection_name=collection_name)
            logger.info("seed_metrics.cleared", collection=collection_name)
            context_service.ensure_collections()
        except Exception as e:
            logger.warning("seed_metrics.clear_failed", error=str(e))

    # Generate embeddings
    texts = [
        f"{item['metric_name']} {' '.join(item['aliases'])} {item['description']}"
        for item in METRICS_SEED_DATA
    ]

    logger.info("seed_metrics.generating_embeddings", count=len(texts))
    embeddings = context_service.embedding.encode(texts)

    # Prepare points
    from qdrant_client.models import PointStruct
    import uuid
    import hashlib

    points = []
    for i, (item, embedding) in enumerate(zip(METRICS_SEED_DATA, embeddings)):
        unique_str = f"{collection_name}_{item['metric_name']}"
        point_id = str(uuid.UUID(hashlib.md5(unique_str.encode()).hexdigest()))

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload=item
        ))

    # Upsert
    context_service.qdrant.client.upsert(
        collection_name=collection_name,
        points=points
    )

    logger.info("seed_metrics.complete", collection=collection_name, points_seeded=len(points))
    return len(points)


async def seed_examples_collection(
    context_service: Nl2SqlContextService,
    clear: bool = False,
    dry_run: bool = False
) -> int:
    """Seed examples collection with NL→SQL pairs."""
    collection_name = context_service.COLLECTION_EXAMPLES

    logger.info("seed_examples.start", collection=collection_name, items=len(EXAMPLES_SEED_DATA), clear=clear, dry_run=dry_run)

    if dry_run:
        logger.info("seed_examples.dry_run", items_would_seed=len(EXAMPLES_SEED_DATA))
        for item in EXAMPLES_SEED_DATA[:3]:
            logger.info("seed_examples.dry_run_item", item=item)
        return len(EXAMPLES_SEED_DATA)

    if clear:
        try:
            context_service.qdrant.client.delete_collection(collection_name=collection_name)
            logger.info("seed_examples.cleared", collection=collection_name)
            context_service.ensure_collections()
        except Exception as e:
            logger.warning("seed_examples.clear_failed", error=str(e))

    # Generate embeddings from natural language
    texts = [item['natural_language'] for item in EXAMPLES_SEED_DATA]

    logger.info("seed_examples.generating_embeddings", count=len(texts))
    embeddings = context_service.embedding.encode(texts)

    # Prepare points
    from qdrant_client.models import PointStruct
    import uuid
    import hashlib

    points = []
    for i, (item, embedding) in enumerate(zip(EXAMPLES_SEED_DATA, embeddings)):
        unique_str = f"{collection_name}_{item['natural_language']}"
        point_id = str(uuid.UUID(hashlib.md5(unique_str.encode()).hexdigest()))

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload=item
        ))

    # Upsert
    context_service.qdrant.client.upsert(
        collection_name=collection_name,
        points=points
    )

    logger.info("seed_examples.complete", collection=collection_name, points_seeded=len(points))
    return len(points)


# ============================================================================
# MAIN
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Seed NL2SQL RAG collections")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing collections before seeding"
    )
    parser.add_argument(
        "--collections",
        type=str,
        default="schema,metrics,examples",
        help="Comma-separated list of collections to seed (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without actually doing it"
    )

    args = parser.parse_args()

    # Parse collections
    collections_to_seed = [c.strip() for c in args.collections.split(',')]

    logger.info(
        "seed_nl2sql_rag.start",
        collections=collections_to_seed,
        clear=args.clear,
        dry_run=args.dry_run
    )

    # Initialize RAG bridge
    from bankadvisor.services.rag_bridge import get_rag_bridge

    rag_bridge = get_rag_bridge()
    if not rag_bridge.inject_from_main_backend():
        logger.error("seed_nl2sql_rag.rag_unavailable", message="RAG services not available")
        sys.exit(1)

    # Initialize context service with RAG
    context_service = Nl2SqlContextService(
        qdrant_service=rag_bridge.get_qdrant_service(),
        embedding_service=rag_bridge.get_embedding_service()
    )

    # Ensure collections exist
    context_service.ensure_collections()

    # Seed collections
    total_seeded = 0

    if "schema" in collections_to_seed:
        count = await seed_schema_collection(context_service, clear=args.clear, dry_run=args.dry_run)
        total_seeded += count

    if "metrics" in collections_to_seed:
        count = await seed_metrics_collection(context_service, clear=args.clear, dry_run=args.dry_run)
        total_seeded += count

    if "examples" in collections_to_seed:
        count = await seed_examples_collection(context_service, clear=args.clear, dry_run=args.dry_run)
        total_seeded += count

    logger.info(
        "seed_nl2sql_rag.complete",
        total_points_seeded=total_seeded,
        dry_run=args.dry_run
    )

    if args.dry_run:
        print(f"\n✅ DRY RUN complete. Would seed {total_seeded} points.")
    else:
        print(f"\n✅ Seeding complete! {total_seeded} points added to Qdrant.")
        print("\nNext steps:")
        print("  1. Restart plugin to use seeded data")
        print("  2. Test query: 'IMOR de INVEX últimos 3 meses'")
        print("  3. Check logs for RAG retrieval scores")


if __name__ == "__main__":
    asyncio.run(main())
