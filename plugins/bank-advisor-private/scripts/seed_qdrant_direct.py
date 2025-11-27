#!/usr/bin/env python3
"""
Direct Qdrant Seeding Script - No backend dependencies
Seeds NL2SQL collections directly using qdrant-client and sentence-transformers.

Usage:
    python scripts/seed_qdrant_direct.py
"""

import hashlib
import uuid
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Collection names
COLLECTION_SCHEMA = "bankadvisor_schema"
COLLECTION_METRICS = "bankadvisor_metrics"
COLLECTION_EXAMPLES = "bankadvisor_examples"

# ============================================================================
# SEED DATA
# ============================================================================

SCHEMA_SEED_DATA = [
    {"column_name": "fecha", "data_type": "date", "description": "Fecha del reporte mensual en formato YYYY-MM-DD. Columna obligatoria para series de tiempo.", "metric_tags": ["temporal", "required"]},
    {"column_name": "banco_nombre", "data_type": "string", "description": "Nombre del banco o 'SISTEMA' para el promedio del sistema financiero.", "metric_tags": ["dimension", "filter"]},
    {"column_name": "imor", "data_type": "float", "description": "Índice de Morosidad - Ratio de cartera vencida sobre cartera total.", "metric_tags": ["quality", "risk", "ratio"]},
    {"column_name": "icor", "data_type": "float", "description": "Índice de Cobertura - Ratio de reservas sobre cartera vencida.", "metric_tags": ["quality", "reserves", "ratio"]},
    {"column_name": "cartera_total", "data_type": "float", "description": "Cartera de crédito total en millones de pesos.", "metric_tags": ["portfolio", "volume"]},
    {"column_name": "cartera_comercial_total", "data_type": "float", "description": "Cartera comercial total - Créditos empresariales.", "metric_tags": ["portfolio", "commercial"]},
    {"column_name": "cartera_consumo_total", "data_type": "float", "description": "Cartera de consumo - Créditos personales y tarjetas.", "metric_tags": ["portfolio", "consumer"]},
    {"column_name": "cartera_vivienda_total", "data_type": "float", "description": "Cartera de vivienda - Créditos hipotecarios.", "metric_tags": ["portfolio", "mortgage"]},
    {"column_name": "cartera_vencida", "data_type": "float", "description": "Cartera vencida total - Créditos con mora > 90 días.", "metric_tags": ["quality", "risk"]},
    {"column_name": "reservas_etapa_todas", "data_type": "float", "description": "Reservas para créditos incobrables totales.", "metric_tags": ["reserves", "provisions"]},
    {"column_name": "icap_total", "data_type": "float", "description": "Índice de Capitalización - Ratio de capital sobre activos.", "metric_tags": ["capital", "solvency"]},
    {"column_name": "tda_cartera_total", "data_type": "float", "description": "Tasa de Deterioro Anual de cartera total.", "metric_tags": ["quality", "deterioration"]},
    {"column_name": "tasa_mn", "data_type": "float", "description": "Tasa de interés promedio en moneda nacional (MXN).", "metric_tags": ["rates", "pricing"]},
    {"column_name": "tasa_me", "data_type": "float", "description": "Tasa de interés promedio en moneda extranjera (USD).", "metric_tags": ["rates", "forex"]},
]

METRICS_SEED_DATA = [
    {"metric_name": "IMOR", "aliases": ["morosidad", "npm", "non-performing"], "description": "Índice de Morosidad - cartera_vencida / cartera_total", "preferred_columns": ["imor"]},
    {"metric_name": "ICOR", "aliases": ["cobertura", "coverage ratio"], "description": "Índice de Cobertura - reservas / cartera_vencida", "preferred_columns": ["icor"]},
    {"metric_name": "CARTERA_TOTAL", "aliases": ["cartera", "portfolio total"], "description": "Volumen total de créditos otorgados", "preferred_columns": ["cartera_total"]},
    {"metric_name": "CARTERA_COMERCIAL", "aliases": ["comercial", "empresarial"], "description": "Créditos a empresas y negocios", "preferred_columns": ["cartera_comercial_total"]},
    {"metric_name": "CARTERA_CONSUMO", "aliases": ["consumo", "retail"], "description": "Créditos personales y tarjetas", "preferred_columns": ["cartera_consumo_total"]},
    {"metric_name": "ICAP", "aliases": ["capitalización", "capital ratio"], "description": "Índice de Capitalización - solvencia del banco", "preferred_columns": ["icap_total"]},
    {"metric_name": "TDA", "aliases": ["deterioro", "tasa deterioro"], "description": "Tasa de Deterioro Anual", "preferred_columns": ["tda_cartera_total"]},
    {"metric_name": "TASA_MN", "aliases": ["tasa pesos", "interés mn"], "description": "Tasa de interés promedio en MXN", "preferred_columns": ["tasa_mn"]},
]

EXAMPLES_SEED_DATA = [
    {"natural_language": "IMOR de INVEX últimos 3 meses", "sql": "SELECT fecha, imor FROM monthly_kpis WHERE banco_nombre = 'INVEX' AND fecha >= (CURRENT_DATE - INTERVAL '3 months') ORDER BY fecha ASC LIMIT 1000"},
    {"natural_language": "Compara IMOR INVEX vs Sistema 2024", "sql": "SELECT fecha, banco_nombre, imor FROM monthly_kpis WHERE banco_nombre IN ('INVEX', 'SISTEMA') AND fecha >= '2024-01-01' AND fecha <= '2024-12-31' ORDER BY fecha ASC, banco_nombre LIMIT 1000"},
    {"natural_language": "cartera comercial de INVEX", "sql": "SELECT fecha, cartera_comercial_total FROM monthly_kpis WHERE banco_nombre = 'INVEX' ORDER BY fecha ASC LIMIT 1000"},
    {"natural_language": "ICOR promedio de INVEX en 2024", "sql": "SELECT AVG(icor) as promedio, MIN(icor) as minimo, MAX(icor) as maximo FROM monthly_kpis WHERE banco_nombre = 'INVEX' AND fecha >= '2024-01-01' AND fecha <= '2024-12-31'"},
    {"natural_language": "ICAP de INVEX últimos 6 meses", "sql": "SELECT fecha, icap_total FROM monthly_kpis WHERE banco_nombre = 'INVEX' AND fecha >= (CURRENT_DATE - INTERVAL '6 months') AND icap_total IS NOT NULL ORDER BY fecha ASC LIMIT 1000"},
    {"natural_language": "Cartera total histórica de INVEX", "sql": "SELECT fecha, cartera_total FROM monthly_kpis WHERE banco_nombre = 'INVEX' ORDER BY fecha ASC LIMIT 1000"},
    {"natural_language": "TDA del sistema financiero en 2024", "sql": "SELECT fecha, tda_cartera_total FROM monthly_kpis WHERE banco_nombre = 'SISTEMA' AND fecha >= '2024-01-01' AND fecha <= '2024-12-31' AND tda_cartera_total IS NOT NULL ORDER BY fecha ASC LIMIT 1000"},
    {"natural_language": "TASA_MN últimos 12 meses", "sql": "SELECT fecha, tasa_mn FROM monthly_kpis WHERE fecha >= (CURRENT_DATE - INTERVAL '12 months') AND tasa_mn IS NOT NULL ORDER BY fecha ASC LIMIT 1000"},
]


def generate_point_id(collection: str, unique_key: str) -> str:
    """Generate deterministic UUID from collection + key."""
    unique_str = f"{collection}_{unique_key}"
    return str(uuid.UUID(hashlib.md5(unique_str.encode()).hexdigest()))


def seed_collection(
    client: QdrantClient,
    model: SentenceTransformer,
    collection_name: str,
    data: List[Dict[str, Any]],
    text_field: str
) -> int:
    """Seed a single collection."""

    # Create collection if not exists
    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )
        print(f"  Created collection: {collection_name}")
    else:
        print(f"  Collection exists: {collection_name}")

    # Generate embeddings
    if text_field == "schema":
        texts = [f"{d['column_name']} {d['description']} {' '.join(d['metric_tags'])}" for d in data]
        unique_keys = [d['column_name'] for d in data]
    elif text_field == "metrics":
        texts = [f"{d['metric_name']} {' '.join(d['aliases'])} {d['description']}" for d in data]
        unique_keys = [d['metric_name'] for d in data]
    else:  # examples
        texts = [d['natural_language'] for d in data]
        unique_keys = [d['natural_language'] for d in data]

    print(f"  Generating embeddings for {len(texts)} items...")
    embeddings = model.encode(texts)

    # Create points
    points = []
    for i, (item, embedding, key) in enumerate(zip(data, embeddings, unique_keys)):
        point_id = generate_point_id(collection_name, key)
        points.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload=item
        ))

    # Upsert
    client.upsert(collection_name=collection_name, points=points)
    print(f"  Upserted {len(points)} points")

    return len(points)


def main():
    print("=" * 60)
    print("NL2SQL RAG Seeding - Direct Qdrant Access")
    print("=" * 60)

    # Connect to Qdrant
    print(f"\nConnecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Verify connection
    collections = client.get_collections()
    print(f"Connected! Existing collections: {[c.name for c in collections.collections]}")

    # Load embedding model
    print(f"\nLoading embedding model: {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Model loaded! Embedding dim: {model.get_sentence_embedding_dimension()}")

    # Seed collections
    total = 0

    print(f"\n[1/3] Seeding {COLLECTION_SCHEMA}...")
    total += seed_collection(client, model, COLLECTION_SCHEMA, SCHEMA_SEED_DATA, "schema")

    print(f"\n[2/3] Seeding {COLLECTION_METRICS}...")
    total += seed_collection(client, model, COLLECTION_METRICS, METRICS_SEED_DATA, "metrics")

    print(f"\n[3/3] Seeding {COLLECTION_EXAMPLES}...")
    total += seed_collection(client, model, COLLECTION_EXAMPLES, EXAMPLES_SEED_DATA, "examples")

    # Verify
    print("\n" + "=" * 60)
    print("SEEDING COMPLETE")
    print("=" * 60)
    print(f"Total points seeded: {total}")

    # Show collection stats
    print("\nCollection stats:")
    for coll_name in [COLLECTION_SCHEMA, COLLECTION_METRICS, COLLECTION_EXAMPLES]:
        info = client.get_collection(coll_name)
        print(f"  - {coll_name}: {info.points_count} points")

    print("\n✅ RAG collections ready for NL2SQL!")
    print("\nNext steps:")
    print("  1. Restart bank-advisor service")
    print("  2. Test query: curl http://localhost:8002/rpc ...")


if __name__ == "__main__":
    main()
