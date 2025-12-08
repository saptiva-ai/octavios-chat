from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from domain.models.evidence import Evidence

class VectorStorePort(ABC):
    """Port for vector storage operations (RAG)."""
    
    @abstractmethod
    def store_evidence(self, evidence: Evidence, collection_name: str = "default") -> bool:
        """
        Store evidence in the vector database.
        
        Args:
            evidence: Evidence object to store
            collection_name: Name of the collection/index
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def search_similar(self, query: str, collection_name: str = "default", limit: int = 5) -> List[Evidence]:
        """
        Search for similar evidence based on semantic similarity.
        
        Args:
            query: Search query text
            collection_name: Name of the collection/index to search
            limit: Maximum number of results to return
            
        Returns:
            List of Evidence objects ordered by similarity
        """
        pass
    
    @abstractmethod
    def create_collection(self, collection_name: str) -> bool:
        """
        Create a new collection/index.
        
        Args:
            collection_name: Name of the collection to create
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection/index.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the vector store is available and healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        pass