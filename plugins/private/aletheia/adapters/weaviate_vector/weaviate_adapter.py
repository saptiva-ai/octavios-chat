import os
import weaviate
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional
import hashlib
import json
from datetime import datetime

from ports.vector_store_port import VectorStorePort
from domain.models.evidence import Evidence, EvidenceSource


class WeaviateVectorAdapter(VectorStorePort):
    """Weaviate implementation of VectorStorePort."""
    
    def __init__(self):
        self.host = os.getenv("WEAVIATE_HOST", "http://localhost:8080")
        self.mock_mode = False
        
        try:
            # Try to connect to Weaviate
            self.client = weaviate.connect_to_local(host=self.host.replace("http://", ""))
            # Test connection
            if not self.health_check():
                print(f"Warning: Could not connect to Weaviate at {self.host}. Using mock mode.")
                self.mock_mode = True
                self.client = None
        except Exception as e:
            print(f"Warning: Weaviate connection failed: {e}. Using mock mode.")
            self.mock_mode = True
            self.client = None
            
        # Mock storage for when Weaviate is not available
        self.mock_store: Dict[str, List[Dict]] = {}
    
    def store_evidence(self, evidence: Evidence, collection_name: str = "default") -> bool:
        """Store evidence in Weaviate or mock storage."""
        if self.mock_mode:
            return self._mock_store_evidence(evidence, collection_name)
        
        try:
            # Create collection if it doesn't exist
            self.create_collection(collection_name)
            
            # Get collection
            collection = self.client.collections.get(collection_name)
            
            # Prepare data object
            data_object = {
                "id": evidence.id,
                "excerpt": evidence.excerpt,
                "source_url": evidence.source.url,
                "source_title": evidence.source.title,
                "fetched_at": evidence.source.fetched_at.isoformat(),
                "hash": evidence.hash or "",
                "tool_call_id": evidence.tool_call_id or "",
                "score": evidence.score or 0.0,
                "tags": evidence.tags,
                "cit_key": evidence.cit_key or ""
            }
            
            # Insert object with vector (Weaviate will auto-vectorize based on excerpt)
            collection.data.insert(
                properties=data_object
            )
            
            print(f"Stored evidence {evidence.id} in Weaviate collection {collection_name}")
            return True
            
        except Exception as e:
            print(f"Error storing evidence in Weaviate: {e}")
            return False
    
    def search_similar(self, query: str, collection_name: str = "default", limit: int = 5) -> List[Evidence]:
        """Search for similar evidence using semantic search."""
        if self.mock_mode:
            return self._mock_search_similar(query, collection_name, limit)
        
        try:
            # Get collection
            collection = self.client.collections.get(collection_name)
            
            # Perform semantic search
            response = collection.query.near_text(
                query=query,
                limit=limit,
                return_metadata=wvc.query.MetadataQuery(score=True)
            )
            
            # Convert results to Evidence objects
            results = []
            for obj in response.objects:
                props = obj.properties
                evidence = Evidence(
                    id=props["id"],
                    source=EvidenceSource(
                        url=props["source_url"],
                        title=props["source_title"],
                        fetched_at=datetime.fromisoformat(props["fetched_at"])
                    ),
                    excerpt=props["excerpt"],
                    hash=props.get("hash") or None,
                    tool_call_id=props.get("tool_call_id") or None,
                    score=obj.metadata.score if obj.metadata.score else props.get("score", 0.0),
                    tags=props.get("tags", []),
                    cit_key=props.get("cit_key") or None
                )
                results.append(evidence)
            
            print(f"Found {len(results)} similar evidence items for query: {query}")
            return results
            
        except Exception as e:
            print(f"Error searching in Weaviate: {e}")
            return []
    
    def create_collection(self, collection_name: str) -> bool:
        """Create a Weaviate collection/class."""
        if self.mock_mode:
            self.mock_store[collection_name] = []
            return True
        
        try:
            # Check if collection already exists
            if self.client.collections.exists(collection_name):
                return True
            
            # Create collection with schema
            self.client.collections.create(
                name=collection_name,
                description=f"Evidence collection for research task: {collection_name}",
                properties=[
                    wvc.config.Property(name="id", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="excerpt", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="source_url", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="source_title", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="fetched_at", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="hash", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="tool_call_id", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="score", data_type=wvc.config.DataType.NUMBER),
                    wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                    wvc.config.Property(name="cit_key", data_type=wvc.config.DataType.TEXT),
                ],
                # Use default vectorizer (text2vec-transformers or similar)
                vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_transformers()
            )
            
            print(f"Created Weaviate collection: {collection_name}")
            return True
            
        except Exception as e:
            print(f"Error creating Weaviate collection: {e}")
            return False
    
    def delete_collection(self, collection_name: str) -> bool:
        """Delete a Weaviate collection."""
        if self.mock_mode:
            if collection_name in self.mock_store:
                del self.mock_store[collection_name]
            return True
        
        try:
            if self.client.collections.exists(collection_name):
                self.client.collections.delete(collection_name)
                print(f"Deleted Weaviate collection: {collection_name}")
            return True
            
        except Exception as e:
            print(f"Error deleting Weaviate collection: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if Weaviate is available."""
        if self.mock_mode:
            return False
        
        try:
            if self.client is None:
                return False
            return self.client.is_ready()
        except Exception:
            return False
    
    # Mock methods for when Weaviate is not available
    def _mock_store_evidence(self, evidence: Evidence, collection_name: str) -> bool:
        """Mock storage for testing without Weaviate."""
        if collection_name not in self.mock_store:
            self.mock_store[collection_name] = []
        
        # Convert evidence to dict for storage
        evidence_dict = {
            "id": evidence.id,
            "excerpt": evidence.excerpt,
            "source_url": evidence.source.url,
            "source_title": evidence.source.title,
            "fetched_at": evidence.source.fetched_at.isoformat(),
            "hash": evidence.hash,
            "tool_call_id": evidence.tool_call_id,
            "score": evidence.score,
            "tags": evidence.tags,
            "cit_key": evidence.cit_key
        }
        
        self.mock_store[collection_name].append(evidence_dict)
        print(f"[MOCK] Stored evidence {evidence.id} in collection {collection_name}")
        return True
    
    def _mock_search_similar(self, query: str, collection_name: str, limit: int) -> List[Evidence]:
        """Mock search for testing without Weaviate."""
        if collection_name not in self.mock_store:
            return []
        
        # Simple keyword matching for mock
        results = []
        query_lower = query.lower()
        
        for evidence_dict in self.mock_store[collection_name]:
            if query_lower in evidence_dict["excerpt"].lower():
                evidence = Evidence(
                    id=evidence_dict["id"],
                    source=EvidenceSource(
                        url=evidence_dict["source_url"],
                        title=evidence_dict["source_title"],
                        fetched_at=datetime.fromisoformat(evidence_dict["fetched_at"])
                    ),
                    excerpt=evidence_dict["excerpt"],
                    hash=evidence_dict["hash"],
                    tool_call_id=evidence_dict["tool_call_id"],
                    score=evidence_dict["score"],
                    tags=evidence_dict["tags"],
                    cit_key=evidence_dict["cit_key"]
                )
                results.append(evidence)
                
                if len(results) >= limit:
                    break
        
        print(f"[MOCK] Found {len(results)} similar evidence items for query: {query}")
        return results