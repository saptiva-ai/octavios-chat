import uuid
import hashlib
from typing import List, Optional
from domain.models.plan import ResearchPlan
from domain.models.evidence import Evidence, EvidenceSource
from adapters.tavily_search.tavily_client import TavilySearchAdapter

# Optional: Vector store for advanced RAG (only needed for multi-investigation scenarios)
try:
    from adapters.weaviate_vector.weaviate_adapter import WeaviateVectorAdapter
    from ports.vector_store_port import VectorStorePort
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False
    VectorStorePort = None
    WeaviateVectorAdapter = None

class ResearchService:
    def __init__(self, enable_vector_store: bool = False):
        # Initialize search adapter
        try:
            self.search_adapter = TavilySearchAdapter()
            self.search_enabled = True
        except ValueError as e:
            print(f"Disabling search functionality: {e}")
            self.search_enabled = False

        # Optional: Initialize vector store for RAG (only if explicitly enabled)
        self.vector_store: Optional[VectorStorePort] = None
        self.vector_store_enabled = False

        if enable_vector_store and VECTOR_STORE_AVAILABLE:
            self.vector_store = WeaviateVectorAdapter()
            if self.vector_store.health_check():
                print("Weaviate vector store is healthy and ready.")
                self.vector_store_enabled = True
            else:
                print("Weaviate not available - continuing without vector storage.")
        else:
            print("Vector store disabled - running in simplified mode.")

    def execute_plan(self, plan: ResearchPlan) -> List[Evidence]:
        """
        Executes the research plan by searching for evidence for each sub-task.
        Optionally stores evidence in vector database for future RAG if enabled.
        """
        if not self.search_enabled:
            print("ResearchService search is disabled due to missing API key.")
            return []

        all_evidence = []
        collection_name = None

        # Only create vector collection if vector store is enabled
        if self.vector_store_enabled:
            collection_name = f"research_{self._generate_collection_id(plan.main_query)}"
            self.vector_store.create_collection(collection_name)

        for task in plan.sub_tasks:
            if "web" in task.sources:
                print(f"--- Executing Research Sub-Task: {task.query} ---")
                search_results = self.search_adapter.search(query=task.query)

                for result in search_results:
                    # Create evidence object
                    evidence = Evidence(
                        id=f"ev_{uuid.uuid4()}",
                        source=EvidenceSource(
                            url=result.get("url", ""),
                            title=result.get("title", ""),
                        ),
                        excerpt=result.get("content", ""),
                        hash=self._generate_hash(result.get("content", "")),
                        tool_call_id=f"tavily:{task.id}"
                    )

                    # Optionally store in vector database for future queries
                    if self.vector_store_enabled and collection_name:
                        stored = self.vector_store.store_evidence(evidence, collection_name)
                        if stored:
                            print(f"Stored evidence {evidence.id} in vector store")

                    all_evidence.append(evidence)

        status_msg = f"Research completed with {len(all_evidence)} pieces of evidence"
        if collection_name:
            status_msg += f" (stored in collection {collection_name})"
        print(status_msg)
        return all_evidence

    def search_existing_evidence(self, query: str, collection_name: str = "default", limit: int = 5) -> List[Evidence]:
        """
        Search for existing evidence in the vector store using semantic similarity.
        Only available if vector store is enabled.
        """
        if not self.vector_store_enabled:
            print("Vector store not enabled - cannot search existing evidence")
            return []
        return self.vector_store.search_similar(query, collection_name, limit)

    def _generate_collection_id(self, main_query: str) -> str:
        """Generate a unique collection ID based on the main query."""
        hash_obj = hashlib.md5(main_query.encode())
        return hash_obj.hexdigest()[:8]

    def _generate_hash(self, content: str) -> str:
        """Generate a hash for content deduplication."""
        hash_obj = hashlib.sha256(content.encode())
        return hash_obj.hexdigest()
