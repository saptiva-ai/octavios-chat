"""
Embedding Service for RAG - Text to Vector Conversion

Architecture Decision Record (ADR):
-----------------------------------
1. **Model Selection: paraphrase-multilingual-MiniLM-L12-v2**
   - Dimension: 384 (compact, fast)
   - Languages: 50+ including Spanish and English
   - Performance: ~50ms per chunk on CPU
   - Quality: Acceptable for production MVP
   - Alternative considered: multilingual-e5-large (1024 dims, slower, better quality)
   - Upgrade path: Easy to swap model, just change EMBEDDING_MODEL_NAME

2. **Chunking Strategy: Sliding Window with Overlap**
   - Chunk size: 500 tokens (~2000 chars)
   - Overlap: 100 tokens (~400 chars)
   - Rationale:
     - PDF documents with tables/graphs benefit from fixed chunks
     - Overlap prevents losing context at boundaries
     - 500 tokens balances context size vs LLM input limits
   - Alternative rejected: Semantic chunking (LangChain RecursiveTextSplitter)
     - Reason: Slower, unnecessary for structured PDFs

3. **Token Counting: Approximate (chars / 4)**
   - Rationale: Exact tokenization is slow (requires model tokenizer)
   - GPT-style approximation: 1 token ≈ 4 characters
   - Acceptable for chunking (doesn't need to be exact)

4. **Caching Strategy: Model in Memory (Singleton)**
   - Load model once on service initialization
   - Keep in memory for entire application lifetime
   - Rationale: Avoid ~2s model loading overhead per request
   - Memory cost: ~120 MB (acceptable)

Performance Expectations:
------------------------
- Model loading: ~2 seconds (first time only)
- Embedding generation: ~30-50ms per chunk (CPU)
- Batch processing: 100 chunks in ~2-3 seconds
- Memory: ~120 MB for model + ~50 MB during inference

Resource Usage:
--------------
For 100 PDFs (10 pages each):
- Chunks: 100 docs × 10 pages × 5 chunks/page = 5,000 chunks
- Processing time: 5,000 × 50ms = ~250 seconds = ~4 minutes (CPU)
- With GPU: 5,000 × 10ms = ~50 seconds
- Storage: 5,000 chunks × 3 KB = ~15 MB in Qdrant
"""

import os
import re
import hashlib
import unicodedata
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TextChunk:
    """
    Represents a chunk of text with its metadata.

    Attributes:
        chunk_id: Sequential index within document (0, 1, 2, ...)
        text: The actual chunk text
        start_char: Starting character position in original text
        end_char: Ending character position in original text
        page: Page number (if applicable, otherwise 0)
        metadata: Additional metadata (filename, etc.)
    """
    chunk_id: int
    text: str
    start_char: int
    end_char: int
    page: int = 0
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingService:
    """
    Service for generating embeddings and chunking text for RAG.

    Responsibilities:
    - Load and manage sentence-transformer model
    - Generate embeddings from text chunks
    - Chunk long text with sliding window strategy
    - Provide token estimation utilities

    Thread-safety: sentence-transformers is thread-safe after model loading.
    This service uses a singleton pattern to avoid loading model multiple times.
    """

    def __init__(self):
        """
        Initialize embedding service and load model.

        Environment variables:
        - EMBEDDING_MODEL_NAME: Model to use (default: paraphrase-multilingual-MiniLM-L12-v2)
        - EMBEDDING_DEVICE: Device for inference (default: cpu, options: cpu/cuda)
        """
        self.model_name = os.getenv(
            "EMBEDDING_MODEL_NAME",
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.device = os.getenv("EMBEDDING_DEVICE", "cpu")

        # Chunking parameters
        self.chunk_size_tokens = int(os.getenv("CHUNK_SIZE_TOKENS", "500"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "100"))

        # Approximate chars per token (GPT-style estimation)
        self.chars_per_token = 4

        logger.info(
            "Initializing embedding service",
            model=self.model_name,
            device=self.device,
            chunk_size=self.chunk_size_tokens,
            chunk_overlap=self.chunk_overlap_tokens,
        )

        # Load model (lazy - only when first needed)
        self._model = None
        self._embedding_dim = None

        # Query embedding cache (LRU cache for frequently used queries)
        # Cache size: 1000 queries = ~384 KB (1000 × 384 floats × 4 bytes)
        # Benefit: Reduces 50ms embedding latency to <1ms for cached queries
        self._query_cache_size = int(os.getenv("QUERY_EMBEDDING_CACHE_SIZE", "1000"))
        self._query_cache: Dict[str, List[float]] = {}

    def _load_model(self):
        """
        Load sentence-transformer model (lazy initialization).

        This is called automatically on first use.
        Loading takes ~2 seconds and uses ~120 MB RAM.
        """
        if self._model is not None:
            return  # Already loaded

        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model (this may take a few seconds)...")

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )

            # Get embedding dimension from model
            self._embedding_dim = self._model.get_sentence_embedding_dimension()

            logger.info(
                "Embedding model loaded successfully",
                model=self.model_name,
                dimension=self._embedding_dim,
                device=self.device,
            )

        except Exception as e:
            logger.error(
                "Failed to load embedding model",
                model=self.model_name,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Embedding model loading failed: {e}") from e

    @property
    def embedding_dim(self) -> int:
        """
        Get embedding dimension.

        Returns:
            Embedding dimension (e.g., 384 for MiniLM)
        """
        if self._embedding_dim is None:
            self._load_model()
        return self._embedding_dim

    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed
            batch_size: Batch size for processing (default: 32)

        Returns:
            List of embedding vectors (each is a list of floats)

        Raises:
            RuntimeError: If encoding fails

        Performance:
        - Single text: ~30-50ms (CPU)
        - Batch of 32: ~1-2 seconds (CPU)
        """
        if not texts:
            return []

        # Ensure model is loaded
        self._load_model()

        try:
            logger.debug(
                "Generating embeddings",
                text_count=len(texts),
                batch_size=batch_size,
            )

            # Generate embeddings
            embeddings = self._model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

            # Convert numpy arrays to lists
            embeddings_list = [emb.tolist() for emb in embeddings]

            logger.debug(
                "Embeddings generated",
                text_count=len(texts),
                embedding_dim=len(embeddings_list[0]) if embeddings_list else 0,
            )

            return embeddings_list

        except Exception as e:
            logger.error(
                "Failed to generate embeddings",
                text_count=len(texts),
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def encode_single(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text (convenience method).

        Args:
            text: Text to embed
            use_cache: Whether to use query cache (default: True)

        Returns:
            Embedding vector

        Performance:
        - Cache hit: <1ms (memory lookup)
        - Cache miss: ~50ms (CPU) or ~10ms (GPU)
        """
        # Check cache if enabled
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self._query_cache:
                logger.debug("Query embedding cache hit", query_preview=text[:50])
                return self._query_cache[cache_key]

        # Generate embedding
        embedding = self.encode([text])[0]

        # Store in cache if enabled
        if use_cache:
            self._update_cache(text, embedding)

        return embedding

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key for text.

        Uses SHA256 hash to ensure consistent keys regardless of text length.
        Normalization includes:
        - Remove accents (á→a, é→e, etc.)
        - Lowercase
        - Remove punctuation
        - Normalize whitespace

        Args:
            text: Input text

        Returns:
            SHA256 hex digest
        """
        # Step 1: Remove accents using Unicode normalization
        # NFD = decompose accented chars (á -> a + combining accent)
        # Then filter out combining characters
        text_nfd = unicodedata.normalize('NFD', text)
        text_no_accents = ''.join(
            char for char in text_nfd
            if unicodedata.category(char) != 'Mn'  # Mn = Mark, nonspacing (accents)
        )

        # Step 2: Lowercase, strip whitespace, remove punctuation
        normalized = re.sub(r'[^\w\s]', '', text_no_accents.lower().strip())

        # Step 3: Normalize whitespace (multiple spaces → single space)
        normalized = re.sub(r'\s+', ' ', normalized)

        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _update_cache(self, text: str, embedding: List[float]) -> None:
        """
        Update query embedding cache with LRU eviction.

        Args:
            text: Query text
            embedding: Generated embedding
        """
        cache_key = self._get_cache_key(text)

        # If cache is full, evict oldest entry (simple FIFO for now)
        if len(self._query_cache) >= self._query_cache_size:
            # Remove first key (oldest)
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]
            logger.debug("Query cache eviction", cache_size=len(self._query_cache))

        # Add new entry
        self._query_cache[cache_key] = embedding
        logger.debug(
            "Query embedding cached",
            cache_size=len(self._query_cache),
            query_preview=text[:50]
        )

    def clear_query_cache(self) -> None:
        """
        Clear query embedding cache.

        Useful for testing or memory management.
        """
        cache_size = len(self._query_cache)
        self._query_cache.clear()
        logger.info("Query embedding cache cleared", entries_removed=cache_size)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses GPT-style approximation: 1 token ≈ 4 characters.
        This is fast but not exact.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return len(text) // self.chars_per_token

    def chunk_text(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[TextChunk]:
        """
        Chunk text using sliding window with overlap.

        Strategy:
        1. Split text into chunks of ~chunk_size_tokens
        2. Use overlap of ~chunk_overlap_tokens between consecutive chunks
        3. Preserve word boundaries (don't split words)

        Args:
            text: Input text to chunk
            page: Page number (for metadata)
            metadata: Additional metadata to attach to chunks

        Returns:
            List of TextChunk objects

        Example:
            text = "A" * 10000  # 10,000 chars ≈ 2,500 tokens
            chunks = service.chunk_text(text)
            # Returns ~6 chunks:
            # - Chunk 0: chars 0-2000 (500 tokens)
            # - Chunk 1: chars 1600-3600 (overlap 400 chars = 100 tokens)
            # - Chunk 2: chars 3200-5200
            # ...
        """
        if not text or not text.strip():
            return []

        # Convert token sizes to character sizes (approximate)
        chunk_size_chars = self.chunk_size_tokens * self.chars_per_token
        overlap_chars = self.chunk_overlap_tokens * self.chars_per_token

        # Clean text: normalize whitespace
        text = re.sub(r'\s+', ' ', text.strip())

        chunks = []
        chunk_id = 0
        start = 0
        text_length = len(text)

        while start < text_length:
            # Calculate end position
            end = min(start + chunk_size_chars, text_length)

            # If not at the end, try to break at word boundary
            if end < text_length:
                # Look for last space in the chunk
                last_space = text.rfind(' ', start, end)
                if last_space > start:
                    end = last_space

            # Extract chunk text
            chunk_text = text[start:end].strip()

            # Only add non-empty chunks
            if chunk_text:
                chunks.append(TextChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                    page=page,
                    metadata=metadata or {},
                ))
                chunk_id += 1

            # Move start position with overlap
            # If we're at the end, break to avoid infinite loop
            if end >= text_length:
                break

            start = end - overlap_chars

            # Ensure we make progress (avoid infinite loop)
            if start <= chunks[-1].start_char if chunks else False:
                start = end

        logger.debug(
            "Text chunked",
            text_length=text_length,
            chunks_created=len(chunks),
            avg_chunk_size=sum(len(c.text) for c in chunks) // len(chunks) if chunks else 0,
        )

        return chunks

    def chunk_and_embed(
        self,
        text: str,
        page: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        batch_size: int = 32,
    ) -> List[Dict[str, Any]]:
        """
        Chunk text and generate embeddings in one step.

        This is the main method to use for document ingestion.

        Args:
            text: Input text to chunk and embed
            page: Page number
            metadata: Additional metadata
            batch_size: Batch size for embedding generation

        Returns:
            List of dicts with keys:
            - chunk_id: int
            - text: str
            - embedding: List[float]
            - page: int
            - metadata: dict

        Example:
            chunks = service.chunk_and_embed(
                text="Long document text...",
                page=1,
                metadata={"filename": "doc.pdf"}
            )
            # Returns: [
            #   {
            #     "chunk_id": 0,
            #     "text": "First chunk...",
            #     "embedding": [0.123, -0.456, ...],
            #     "page": 1,
            #     "metadata": {"filename": "doc.pdf"}
            #   },
            #   ...
            # ]
        """
        # Step 1: Chunk text
        chunks = self.chunk_text(text, page=page, metadata=metadata)

        if not chunks:
            logger.warning("No chunks generated from text", text_length=len(text))
            return []

        # Step 2: Generate embeddings for all chunks
        chunk_texts = [c.text for c in chunks]
        embeddings = self.encode(chunk_texts, batch_size=batch_size)

        # Step 3: Combine chunks with embeddings
        result = []
        for chunk, embedding in zip(chunks, embeddings):
            result.append({
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "embedding": embedding,
                "page": chunk.page,
                "metadata": chunk.metadata,
            })

        logger.info(
            "Text chunked and embedded",
            text_length=len(text),
            chunks_count=len(result),
            embedding_dim=len(embeddings[0]) if embeddings else 0,
        )

        return result


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get or create singleton embedding service instance.

    This is the preferred way to access EmbeddingService in the app.
    Model is loaded lazily on first use.

    Returns:
        EmbeddingService instance
    """
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = EmbeddingService()

    return _embedding_service
