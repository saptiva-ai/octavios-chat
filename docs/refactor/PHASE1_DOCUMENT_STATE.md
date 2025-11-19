# FASE 1: Estado de Documentos Estructurado

**Duración**: 5 días
**Owner**: Backend team
**Reviewers**: Arquitectura + 414 Capital stakeholder

---

## 🎯 Objetivos

1. Crear modelo `DocumentState` con ciclo de vida explícito
2. Migrar `ChatSession.attached_file_ids` → `ChatSession.documents`
3. Mantener backward compatibility durante transición
4. Validar en staging con datos de 414 Capital

---

## 📋 Tareas (Día 1-2)

### 1.1 Crear `DocumentState` model

**File**: `apps/api/src/models/document_state.py`

```python
"""
Document lifecycle state model for chat sessions.

Replaces simple List[str] with structured state machine.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    """Document processing lifecycle states"""
    UPLOADING = "uploading"      # File being uploaded to storage
    PROCESSING = "processing"    # OCR/extraction in progress
    SEGMENTING = "segmenting"    # Breaking into searchable chunks
    INDEXING = "indexing"        # Building embeddings (optional)
    READY = "ready"              # Available for RAG
    FAILED = "failed"            # Processing failed (with error message)
    ARCHIVED = "archived"        # Removed from active context


class DocumentState(BaseModel):
    """
    Structured state for a document within a conversation.

    Lifecycle:
    UPLOADING → PROCESSING → SEGMENTING → [INDEXING] → READY
                     ↓
                  FAILED
    """

    # Core identity
    doc_id: str = Field(..., description="Document ID (from Document model)")
    name: str = Field(..., description="Original filename")

    # Processing state
    status: ProcessingStatus = Field(
        default=ProcessingStatus.UPLOADING,
        description="Current processing status"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if status=FAILED"
    )

    # Document metadata
    pages: Optional[int] = Field(None, description="Number of pages (PDFs)")
    size_bytes: Optional[int] = Field(None, description="File size")
    mimetype: Optional[str] = Field(None, description="MIME type")

    # Processing results
    segments_count: int = Field(
        default=0,
        description="Number of text segments extracted"
    )
    indexed_at: Optional[datetime] = Field(
        None,
        description="When indexing completed (if status=READY)"
    )

    # RAG metadata (optional, for future vector search)
    has_embeddings: bool = Field(
        default=False,
        description="Whether embeddings were generated"
    )
    vector_store_ref: Optional[str] = Field(
        None,
        description="Reference to vector store collection/index"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When document was added to conversation"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last status update"
    )

    def mark_processing(self):
        """Transition to PROCESSING state"""
        self.status = ProcessingStatus.PROCESSING
        self.updated_at = datetime.utcnow()

    def mark_ready(self, segments_count: int):
        """Transition to READY state"""
        self.status = ProcessingStatus.READY
        self.segments_count = segments_count
        self.indexed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: str):
        """Transition to FAILED state"""
        self.status = ProcessingStatus.FAILED
        self.error = error[:500]  # Truncate long errors
        self.updated_at = datetime.utcnow()

    def is_ready(self) -> bool:
        """Check if document is ready for RAG"""
        return self.status == ProcessingStatus.READY
```

**Tests**: `apps/api/tests/unit/models/test_document_state.py`

```python
import pytest
from datetime import datetime
from src.models.document_state import DocumentState, ProcessingStatus


def test_document_state_creation():
    doc = DocumentState(
        doc_id="test-123",
        name="report.pdf",
        pages=10
    )

    assert doc.status == ProcessingStatus.UPLOADING
    assert doc.segments_count == 0
    assert doc.is_ready() is False


def test_document_lifecycle():
    doc = DocumentState(doc_id="test-123", name="test.pdf")

    # UPLOADING → PROCESSING
    doc.mark_processing()
    assert doc.status == ProcessingStatus.PROCESSING

    # PROCESSING → READY
    doc.mark_ready(segments_count=15)
    assert doc.status == ProcessingStatus.READY
    assert doc.segments_count == 15
    assert doc.indexed_at is not None
    assert doc.is_ready() is True


def test_document_failure():
    doc = DocumentState(doc_id="test-123", name="corrupted.pdf")

    doc.mark_failed("OCR extraction failed: invalid PDF structure")

    assert doc.status == ProcessingStatus.FAILED
    assert doc.error.startswith("OCR extraction failed")
    assert doc.is_ready() is False


def test_error_truncation():
    doc = DocumentState(doc_id="test-123", name="test.pdf")

    long_error = "x" * 1000
    doc.mark_failed(long_error)

    assert len(doc.error) == 500  # Truncated
```

---

### 1.2 Actualizar `ChatSession` model

**File**: `apps/api/src/models/chat.py` (modificar líneas 137-139)

```python
# ANTES (línea 137-138):
# MVP-FILE-CONTEXT: Store file IDs attached to this session for persistent document context
attached_file_ids: List[str] = Field(default_factory=list, description="File IDs attached to this conversation")

# DESPUÉS:
from .document_state import DocumentState

# MVP-FILE-CONTEXT: Structured document states for this conversation
documents: List[DocumentState] = Field(
    default_factory=list,
    description="Documents with processing state attached to this conversation"
)

# DEPRECATED: Legacy field for backward compatibility (remove in v2.0)
attached_file_ids: List[str] = Field(
    default_factory=list,
    description="DEPRECATED: Use 'documents' field instead. Kept for migration."
)
```

**Helper methods** (agregar a `ChatSession` class):

```python
def add_document(self, doc_id: str, name: str, **kwargs) -> DocumentState:
    """Add a new document to the conversation"""
    doc_state = DocumentState(doc_id=doc_id, name=name, **kwargs)
    self.documents.append(doc_state)

    # Keep legacy field in sync during migration
    if doc_id not in self.attached_file_ids:
        self.attached_file_ids.append(doc_id)

    return doc_state

def get_document(self, doc_id: str) -> Optional[DocumentState]:
    """Get document state by ID"""
    return next((d for d in self.documents if d.doc_id == doc_id), None)

def get_ready_documents(self) -> List[DocumentState]:
    """Get all documents ready for RAG"""
    return [d for d in self.documents if d.is_ready()]

def update_document_status(self, doc_id: str, status: ProcessingStatus, **kwargs):
    """Update document processing status"""
    doc = self.get_document(doc_id)
    if doc:
        doc.status = status
        doc.updated_at = datetime.utcnow()

        for key, value in kwargs.items():
            setattr(doc, key, value)
```

---

## 📋 Tareas (Día 3-4)

### 1.3 Migration Script

**File**: `scripts/migrate_attached_files_to_documents.py`

```python
#!/usr/bin/env python3
"""
Migration script: attached_file_ids → documents

Converts legacy List[str] to structured DocumentState objects.

Usage:
    python scripts/migrate_attached_files_to_documents.py --dry-run
    python scripts/migrate_attached_files_to_documents.py --execute
"""

import asyncio
import argparse
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from src.core.config import get_settings
from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import DocumentState, ProcessingStatus


async def migrate_session(session: ChatSession, dry_run: bool = True) -> dict:
    """Migrate a single session's attached_file_ids to documents"""

    stats = {
        "session_id": session.id,
        "legacy_count": len(session.attached_file_ids),
        "migrated_count": 0,
        "failed_count": 0,
        "already_migrated": len(session.documents) > 0
    }

    # Skip if already has documents field populated
    if session.documents:
        print(f"⏭️  Session {session.id[:8]} already migrated ({len(session.documents)} docs)")
        return stats

    # Skip empty sessions
    if not session.attached_file_ids:
        print(f"⏭️  Session {session.id[:8]} has no attached files")
        return stats

    print(f"🔄 Migrating session {session.id[:8]} with {len(session.attached_file_ids)} files...")

    # Convert each file_id to DocumentState
    for file_id in session.attached_file_ids:
        try:
            # Try to fetch document metadata from Document collection
            doc = await Document.get(file_id)

            if doc:
                doc_state = DocumentState(
                    doc_id=file_id,
                    name=doc.filename,
                    pages=doc.metadata.get("pages") if doc.metadata else None,
                    size_bytes=doc.size_bytes,
                    mimetype=doc.content_type,
                    status=ProcessingStatus.READY,  # Assume legacy docs are processed
                    segments_count=1,  # Assume at least 1 segment
                    indexed_at=doc.created_at,
                    created_at=doc.created_at
                )
            else:
                # Document not found - create minimal DocumentState
                print(f"  ⚠️  Document {file_id[:8]} not found, creating minimal state")
                doc_state = DocumentState(
                    doc_id=file_id,
                    name=f"document_{file_id[:8]}",
                    status=ProcessingStatus.READY,
                    created_at=datetime.utcnow()
                )

            session.documents.append(doc_state)
            stats["migrated_count"] += 1

        except Exception as e:
            print(f"  ❌ Failed to migrate {file_id[:8]}: {e}")
            stats["failed_count"] += 1

    # Save changes
    if not dry_run:
        await session.save()
        print(f"✅ Migrated {stats['migrated_count']} documents for session {session.id[:8]}")
    else:
        print(f"🔍 [DRY RUN] Would migrate {stats['migrated_count']} documents")

    return stats


async def migrate_all_sessions(dry_run: bool = True):
    """Migrate all sessions with attached_file_ids"""

    settings = get_settings()

    # Initialize Beanie
    client = AsyncIOMotorClient(settings.mongodb_url)
    await init_beanie(
        database=client.octavios,
        document_models=[ChatSession, Document]
    )

    # Find all sessions with attached files
    sessions = await ChatSession.find(
        {"attached_file_ids": {"$exists": True, "$ne": []}}
    ).to_list()

    print(f"\n📊 Found {len(sessions)} sessions with attached files\n")

    total_stats = {
        "total_sessions": len(sessions),
        "migrated": 0,
        "failed": 0,
        "skipped": 0
    }

    for session in sessions:
        stats = await migrate_session(session, dry_run=dry_run)

        if stats["already_migrated"]:
            total_stats["skipped"] += 1
        elif stats["migrated_count"] > 0:
            total_stats["migrated"] += 1

        total_stats["failed"] += stats["failed_count"]

    # Summary
    print("\n" + "="*60)
    print("📈 MIGRATION SUMMARY")
    print("="*60)
    print(f"Total sessions: {total_stats['total_sessions']}")
    print(f"✅ Migrated: {total_stats['migrated']}")
    print(f"⏭️  Skipped (already migrated): {total_stats['skipped']}")
    print(f"❌ Failed documents: {total_stats['failed']}")
    print("="*60)

    if dry_run:
        print("\n⚠️  This was a DRY RUN. Run with --execute to apply changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate attached_file_ids to documents")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute migration (default is dry-run)"
    )

    args = parser.parse_args()

    asyncio.run(migrate_all_sessions(dry_run=not args.execute))
```

**Execution**:
```bash
# 1. Dry run first
python scripts/migrate_attached_files_to_documents.py --dry-run

# 2. Review output, then execute
python scripts/migrate_attached_files_to_documents.py --execute

# 3. Verify in MongoDB
docker exec -it octavios-mongodb mongosh octavios --eval '
  db.chat_sessions.findOne(
    {documents: {$exists: true, $ne: []}},
    {documents: 1, attached_file_ids: 1}
  )
'
```

---

## 📋 Tareas (Día 5)

### 1.4 Validation & Rollout

**Checklist**:

- [ ] Run migration script in staging
- [ ] Verify `documents` field populated correctly
- [ ] Check `attached_file_ids` still present (backward compatibility)
- [ ] Test with 414 Capital session data
- [ ] Validate no data loss (compare counts)
- [ ] Update API docs to reflect new field

**Rollback plan**:
```python
# If migration fails, documents field is just empty - no data lost
# attached_file_ids remains intact
```

---

## ✅ Acceptance Criteria

1. [ ] `DocumentState` model created with all lifecycle states
2. [ ] Unit tests pass (>=95% coverage)
3. [ ] `ChatSession.documents` field functional
4. [ ] Migration script tested in staging (dry-run + execute)
5. [ ] Zero data loss verified
6. [ ] Backward compatibility maintained (old API clients still work)
7. [ ] Documentation updated

---

## 📊 Metrics

**Success metrics**:
- Migration success rate: >= 99%
- API response time: No degradation
- Database size increase: < 10% (structured metadata overhead)

**Monitoring**:
```python
# Add to startup logging
logger.info(
    "Session document stats",
    total_sessions=await ChatSession.count(),
    with_documents=await ChatSession.find({"documents.0": {"$exists": True}}).count(),
    with_legacy_only=await ChatSession.find({
        "attached_file_ids.0": {"$exists": True},
        "documents": []
    }).count()
)
```

---

## 🔗 Next Phase

Once Phase 1 is complete:
→ **Phase 2**: Create MCP tools `ingest_files` and `get_relevant_segments`
