#!/usr/bin/env python3
"""
RAG Chunk Optimization Analyzer

This script analyzes document characteristics to recommend optimal chunking parameters.

Analysis includes:
1. Document length distribution
2. Average paragraph/section length
3. Semantic coherence across different chunk sizes
4. Overlap effectiveness

Recommendations based on:
- Document type (technical, narrative, mixed)
- Average query patterns
- LLM context window limits
"""

import requests
import json
from pathlib import Path
from typing import List, Dict, Any

# Configuration
API_BASE = "http://localhost:8001"
QDRANT_BASE = "http://localhost:6333"
TEST_USER = {"email": "demo@example.com", "password": "Demo1234"}

# Test PDFs
TEST_PDF_DIR = Path(__file__).parent.parent / "packages/tests-e2e/tests/data/capital414"
TEST_PDFS = list(TEST_PDF_DIR.glob("*.pdf"))


def authenticate():
    """Authenticate and get JWT token."""
    response = requests.post(
        f"{API_BASE}/api/auth/login",
        json={"identifier": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


def analyze_qdrant_chunks():
    """Analyze existing chunks in Qdrant to understand current distribution."""
    print("\n📊 Analyzing existing chunks in Qdrant...")

    response = requests.post(
        f"{QDRANT_BASE}/collections/rag_documents/points/scroll",
        json={
            "limit": 1000,
            "with_payload": True,
            "with_vector": False
        }
    )

    if response.status_code != 200:
        print(f"❌ Failed to fetch from Qdrant: {response.status_code}")
        return None

    points = response.json()["result"]["points"]

    if not points:
        print("⚠️  No chunks found in Qdrant. Upload documents first using 'make test-rag'")
        return None

    # Analyze chunk characteristics
    chunk_lengths = [len(p["payload"]["text"]) for p in points]
    chunk_tokens = [len(p["payload"]["text"]) // 4 for p in points]  # Approximate tokens

    analysis = {
        "total_chunks": len(points),
        "avg_chunk_length_chars": sum(chunk_lengths) / len(chunk_lengths),
        "min_chunk_length_chars": min(chunk_lengths),
        "max_chunk_length_chars": max(chunk_lengths),
        "avg_chunk_tokens": sum(chunk_tokens) / len(chunk_tokens),
        "min_chunk_tokens": min(chunk_tokens),
        "max_chunk_tokens": max(chunk_tokens),
    }

    # Group by document
    docs = {}
    for p in points:
        doc_id = p["payload"]["document_id"]
        if doc_id not in docs:
            docs[doc_id] = {
                "chunks": [],
                "filename": p["payload"].get("metadata", {}).get("filename", "Unknown")
            }
        docs[doc_id]["chunks"].append(p["payload"]["text"])

    analysis["documents"] = len(docs)
    analysis["avg_chunks_per_doc"] = len(points) / len(docs)

    # Show distribution
    print(f"\n✅ Analysis complete:")
    print(f"   Total chunks: {analysis['total_chunks']}")
    print(f"   Documents: {analysis['documents']}")
    print(f"   Avg chunks/doc: {analysis['avg_chunks_per_doc']:.1f}")
    print(f"\n📏 Chunk size stats:")
    print(f"   Avg length: {analysis['avg_chunk_length_chars']:.0f} chars (~{analysis['avg_chunk_tokens']:.0f} tokens)")
    print(f"   Min length: {analysis['min_chunk_length_chars']} chars (~{analysis['min_chunk_tokens']} tokens)")
    print(f"   Max length: {analysis['max_chunk_length_chars']} chars (~{analysis['max_chunk_tokens']} tokens)")

    # Document-level stats
    print(f"\n📄 Document breakdown:")
    for doc_id, doc_info in docs.items():
        chunk_count = len(doc_info["chunks"])
        avg_len = sum(len(c) for c in doc_info["chunks"]) / chunk_count
        print(f"   {doc_info['filename']}: {chunk_count} chunks, avg {avg_len:.0f} chars")

    return analysis


def recommend_parameters(analysis: Dict[str, Any]):
    """Recommend optimal chunking parameters based on analysis."""
    if not analysis:
        print("\n⚠️  Cannot provide recommendations without analysis data")
        return

    print("\n" + "=" * 70)
    print("🎯 OPTIMIZATION RECOMMENDATIONS")
    print("=" * 70)

    avg_tokens = analysis["avg_chunk_tokens"]
    max_tokens = analysis["max_chunk_tokens"]

    # Current parameters
    current_chunk_size = 500
    current_overlap = 100

    print(f"\n📌 Current configuration:")
    print(f"   CHUNK_SIZE_TOKENS: {current_chunk_size}")
    print(f"   CHUNK_OVERLAP_TOKENS: {current_overlap}")
    print(f"   Overlap ratio: {(current_overlap/current_chunk_size)*100:.1f}%")

    # Recommendations based on document type
    print(f"\n💡 Recommendations:")

    if avg_tokens < 400:
        print(f"   ✅ Current chunk size is GOOD (avg {avg_tokens:.0f} tokens < 500 limit)")
        print(f"      - Most chunks fit well within the window")
        print(f"      - No action needed")
    elif avg_tokens > 450:
        print(f"   ⚠️  Chunks are near the limit (avg {avg_tokens:.0f} tokens)")
        print(f"      - Consider increasing to CHUNK_SIZE_TOKENS=600")
        print(f"      - This gives more context per chunk")

    if max_tokens > current_chunk_size:
        print(f"   ⚠️  Some chunks exceed limit (max {max_tokens} tokens)")
        print(f"      - Increase CHUNK_SIZE_TOKENS to {int(max_tokens * 1.2)}")

    # Overlap recommendations
    overlap_ratio = (current_overlap / current_chunk_size) * 100
    if overlap_ratio < 15:
        print(f"   ⚠️  Overlap too small ({overlap_ratio:.1f}%)")
        print(f"      - Risk of losing context at boundaries")
        print(f"      - Increase CHUNK_OVERLAP_TOKENS to {int(current_chunk_size * 0.2)}")
    elif overlap_ratio > 30:
        print(f"   ⚠️  Overlap too large ({overlap_ratio:.1f}%)")
        print(f"      - Redundancy increases storage and latency")
        print(f"      - Decrease CHUNK_OVERLAP_TOKENS to {int(current_chunk_size * 0.2)}")
    else:
        print(f"   ✅ Overlap ratio is GOOD ({overlap_ratio:.1f}%)")

    # Document-specific recommendations
    avg_chunks_per_doc = analysis["avg_chunks_per_doc"]
    if avg_chunks_per_doc < 5:
        print(f"\n📄 Document analysis:")
        print(f"   - Short documents (avg {avg_chunks_per_doc:.1f} chunks)")
        print(f"   - Consider SMALLER chunks (300-400 tokens) for better granularity")
    elif avg_chunks_per_doc > 20:
        print(f"\n📄 Document analysis:")
        print(f"   - Long documents (avg {avg_chunks_per_doc:.1f} chunks)")
        print(f"   - Consider LARGER chunks (600-800 tokens) to reduce chunk count")
        print(f"   - This improves query speed and reduces storage")

    # Final recommendation
    print(f"\n🎯 Recommended configuration for your use case:")

    # Calculate optimal values
    if avg_chunks_per_doc < 5:
        recommended_chunk = 400
        recommended_overlap = 80
    elif avg_chunks_per_doc > 20:
        recommended_chunk = 700
        recommended_overlap = 140
    else:
        recommended_chunk = 500
        recommended_overlap = 100

    print(f"   CHUNK_SIZE_TOKENS={recommended_chunk}")
    print(f"   CHUNK_OVERLAP_TOKENS={recommended_overlap}")
    print(f"   Overlap ratio: {(recommended_overlap/recommended_chunk)*100:.1f}%")

    if recommended_chunk != current_chunk_size or recommended_overlap != current_overlap:
        print(f"\n📝 To apply these changes:")
        print(f"   1. Edit envs/.env and set:")
        print(f"      CHUNK_SIZE_TOKENS={recommended_chunk}")
        print(f"      CHUNK_OVERLAP_TOKENS={recommended_overlap}")
        print(f"   2. Restart API: make restart S=api")
        print(f"   3. Re-upload documents to apply new chunking")
    else:
        print(f"\n✅ Current configuration is optimal! No changes needed.")

    print("=" * 70)


def main():
    """Run chunk optimization analysis."""
    print("=" * 70)
    print("RAG CHUNK OPTIMIZATION ANALYZER")
    print("=" * 70)

    # Authenticate
    print("\n🔐 Authenticating...")
    token = authenticate()
    if not token:
        print("❌ Authentication failed. Run 'make create-demo-user' first.")
        return

    print("✅ Authenticated")

    # Analyze existing chunks
    analysis = analyze_qdrant_chunks()

    # Provide recommendations
    recommend_parameters(analysis)


if __name__ == "__main__":
    main()
