"""
Quick integration test for Qdrant service.

Run from project root:
    python test_qdrant_integration.py
"""

import sys
import os

# Add src to path so we can import the service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api", "src"))

from services.qdrant_service import QdrantService


def test_qdrant_integration():
    """Test basic Qdrant service functionality."""

    print("=" * 60)
    print("QDRANT SERVICE INTEGRATION TEST")
    print("=" * 60)

    # 1. Initialize service
    print("\n1. Initializing Qdrant service...")
    service = QdrantService()
    print(f"   ✅ Connected to {service.host}:{service.port}")
    print(f"   Collection: {service.collection_name}")
    print(f"   Embedding dimension: {service.embedding_dim}")

    # 2. Ensure collection exists
    print("\n2. Ensuring collection exists...")
    try:
        service.ensure_collection()
        print("   ✅ Collection ready")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

    # 3. Health check
    print("\n3. Running health check...")
    health = service.health_check()
    print(f"   Status: {health['status']}")
    print(f"   Collection exists: {health['collection_exists']}")
    print(f"   Points count: {health['points_count']}")

    if health['status'] != 'healthy':
        print(f"   ❌ Unhealthy: {health.get('error')}")
        return False
    print("   ✅ Health check passed")

    # 4. Test upsert (with mock embeddings)
    print("\n4. Testing upsert...")
    try:
        import random

        # Create mock chunks with random embeddings
        test_chunks = [
            {
                "chunk_id": 0,
                "text": "Este es un chunk de prueba número 1",
                "embedding": [random.random() for _ in range(service.embedding_dim)],
                "page": 1,
                "metadata": {"test": True}
            },
            {
                "chunk_id": 1,
                "text": "Este es un chunk de prueba número 2",
                "embedding": [random.random() for _ in range(service.embedding_dim)],
                "page": 1,
                "metadata": {"test": True}
            }
        ]

        count = service.upsert_chunks(
            session_id="test-session-123",
            document_id="test-doc-456",
            chunks=test_chunks
        )
        print(f"   ✅ Upserted {count} chunks")

    except Exception as e:
        print(f"   ❌ Upsert failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5. Test search
    print("\n5. Testing search...")
    try:
        # Search with random query vector
        query_vector = [random.random() for _ in range(service.embedding_dim)]

        results = service.search(
            session_id="test-session-123",
            query_vector=query_vector,
            top_k=2,
            score_threshold=0.0  # Accept any score for test
        )

        print(f"   ✅ Search returned {len(results)} results")
        if results:
            print(f"   Top result score: {results[0]['score']:.4f}")
            print(f"   Top result text preview: {results[0]['text'][:50]}...")

    except Exception as e:
        print(f"   ❌ Search failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 6. Test cleanup
    print("\n6. Testing cleanup...")
    try:
        deleted_count = service.delete_session("test-session-123")
        print(f"   ✅ Deleted {deleted_count} points")

    except Exception as e:
        print(f"   ❌ Cleanup failed: {e}")
        return False

    # 7. Verify deletion
    print("\n7. Verifying deletion...")
    health_after = service.health_check()
    print(f"   Points count after cleanup: {health_after['points_count']}")

    if health_after['points_count'] == 0:
        print("   ✅ All test points deleted")
    else:
        print(f"   ⚠️  Warning: {health_after['points_count']} points remain")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_qdrant_integration()
    sys.exit(0 if success else 1)
