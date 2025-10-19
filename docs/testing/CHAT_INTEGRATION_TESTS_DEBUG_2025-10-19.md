# Chat Integration Tests Debugging Report
**Date:** October 19, 2025
**Session:** Chat File Context Integration Tests
**Final Status:** ✅ **5/5 tests passing (100%)**
**Execution Time:** ~0.6 seconds

---

## Executive Summary

Successfully debugged and fixed all 5 chat integration tests for the file context persistence feature. These tests verify that documents attached to conversations persist across multiple messages within a chat session.

### Test Coverage
The suite covers the complete file context lifecycle:
1. **File attachment**: First message stores file_ids in session
2. **Context persistence**: Subsequent messages maintain file context
3. **Multi-turn conversations**: File context persists through 5+ messages
4. **Multiple files**: Adding second file merges with existing context
5. **New conversations**: Fresh sessions start with empty file context

---

## Issues Resolved

### Issue 1: Event Loop Scope Conflicts
**Error:**
```
RuntimeError: Event loop is closed
```

**Root Cause:** Session-scoped fixture `app_lifespan` created different event loop than function-scoped tests.

**Fix:** Removed session-scoped lifespan fixture. The `initialize_db` fixture from `conftest.py` already handles database initialization correctly with function scope.

**Code Change:**
```python
# REMOVED:
@pytest_asyncio.fixture(scope="session", autouse=True)
async def app_lifespan():
    """Initialize app for integration tests"""
    await app.router.startup()
    yield
    await app.router.shutdown()

# Now relies on conftest.py's initialize_db fixture
```

---

### Issue 2: Document ID Validation
**Error:**
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Document
id
  Value error, Id must be of type PydanticObjectId
```

**Root Cause:** Tests manually set `id="test-doc-context-persist"` as string, but Beanie requires PydanticObjectId.

**Fix:** Remove manual ID assignment and let Beanie auto-generate ObjectIds.

**Code Change:**
```python
# BEFORE:
document = Document(
    id="test-doc-context-persist",  # ❌ String ID not allowed
    filename="test.pdf",
    ...
)

# AFTER:
document = Document(
    # Let Beanie generate ID automatically ✅
    filename="test.pdf",
    ...
)
await document.insert()
# Now use: document.id (auto-generated ObjectId)
```

---

### Issue 3: Import Path Issues
**Error:**
```
ModuleNotFoundError: No module named 'apps.api.src'
```

**Root Cause:** Tests used `apps.api.src` prefix which doesn't work when running from the `api` directory.

**Fix:** Update all imports to use `src.*` directly.

**Code Changes:**
```python
# BEFORE:
from apps.api.src.main import app
from apps.api.src.models.chat import ChatSession
from apps.api.src.services.saptiva_client import SaptivaClient

# AFTER:
from src.main import app
from src.models.chat import ChatSession as ChatSessionModel
from src.services.saptiva_client import SaptivaClient
```

**Mock paths also updated:**
```python
# BEFORE:
with patch('apps.api.src.services.saptiva_client.SaptivaClient.chat_completion', ...):

# AFTER:
with patch('src.services.saptiva_client.SaptivaClient.chat_completion', ...):
```

---

### Issue 4: Missing Redis Document Cache (Critical)
**Error:**
```
[warning] Document text not in Redis cache (expired?) doc_id=68f496248c6a62add5bee82d
[warning] Skipping expired document
```

**Root Cause:** Tests created documents in MongoDB but didn't cache their text content in Redis. The application's document service expects document text to be in Redis cache (1-hour TTL) and skips documents not found there.

**Architecture Understanding:**
- **MongoDB**: Stores document metadata (filename, status, user_id, pages structure)
- **Redis**: Caches extracted document text for fast retrieval
- **Key format**: `doc:text:{doc_id}` with 3600 second TTL
- **Cache miss behavior**: Document service returns "[Documento expirado de cache]" message

**Fix:** Update test fixtures to cache document text in Redis after creating MongoDB documents.

**Code Changes:**
```python
# test_document fixture - AFTER:
@pytest_asyncio.fixture
async def test_document(test_user_chat: Dict[str, str]):
    """Create a test document for file context tests"""
    from src.services.cache_service import get_redis_client

    document_text = "# Test Document\n\nThis is a test PDF document..."

    # 1. Create in MongoDB
    document = Document(
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        minio_key="test-key",
        minio_bucket="test",
        status=DocumentStatus.READY,
        user_id=test_user_chat["user_id"],
        pages=[{
            "page": 1,
            "text_md": document_text,
            "has_table": False
        }]
    )
    await document.insert()

    # 2. Cache text in Redis ✅
    try:
        redis_client = await get_redis_client()
        if redis_client:
            redis_key = f"doc:text:{str(document.id)}"
            await redis_client.set(redis_key, document_text, ex=3600)  # 1 hour TTL
    except Exception as e:
        print(f"Warning: Could not cache document in Redis: {e}")

    yield document

    # 3. Cleanup both MongoDB and Redis
    try:
        doc_to_delete = await Document.find_one(Document.id == document.id)
        if doc_to_delete:
            await doc_to_delete.delete()
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.delete(f"doc:text:{str(document.id)}")
    except Exception:
        pass
```

**Applied to:** Both `test_document` fixture and inline `document2` creation in `test_adding_second_file_merges_with_existing`.

---

### Issue 5: Test User Fixture Dependencies
**Error:** Fixture dependency ordering issues causing event loop conflicts.

**Fix:** Created dedicated `test_user_chat` fixture that depends on `clean_db` and returns user credentials. Updated `auth_token` and `test_document` to depend on this fixture.

**Code Change:**
```python
@pytest_asyncio.fixture
async def test_user_chat(clean_db) -> Dict[str, str]:
    """Create a test user for chat tests and return credentials."""
    username = "test-file-context"
    email = "test-file-context@example.com"
    password = "Demo1234"

    auth_response = await register_user(
        UserCreate(username=username, email=email, password=password)
    )

    return {
        "username": username,
        "email": email,
        "password": password,
        "user_id": auth_response.user.id
    }

@pytest_asyncio.fixture
async def auth_token(test_user_chat: Dict[str, str]) -> str:
    """Create auth token for test user"""
    settings = get_settings()

    payload = {
        "sub": test_user_chat["user_id"],  # Use real user ID
        "type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "username": test_user_chat["username"],
        "email": test_user_chat["email"],
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
```

---

## Test Suite Coverage

### Test 1: `test_first_message_stores_file_ids_in_session`
**Purpose:** Verify first message with file_ids stores them in ChatSession.

**Test Flow:**
1. Send message with `file_ids: ["doc-id-1"]`
2. Verify response includes `chat_id`
3. Query ChatSession from MongoDB
4. Assert `session.attached_file_ids` contains document ID

**Validation:**
- ✅ File IDs stored in session
- ✅ Session persisted to MongoDB
- ✅ Document text retrieved from Redis cache

---

### Test 2: `test_second_message_includes_session_file_ids`
**Purpose:** Verify subsequent messages WITHOUT file_ids still include session's files.

**Test Flow:**
1. **Message 1:** Send with `file_ids: ["doc-id"]`
2. **Message 2:** Send to same chat_id WITHOUT file_ids
3. Verify LLM received document context in second message
4. Check system message includes document content

**Validation:**
- ✅ Session file_ids merged with request
- ✅ Document context included in LLM payload
- ✅ System message contains document text

---

### Test 3: `test_multi_turn_conversation_maintains_file_context`
**Purpose:** Verify file context persists through multiple messages (5 messages).

**Test Flow:**
1. **Message 1:** Upload file
2. **Messages 2-5:** No file_ids
3. Verify all 5 LLM calls had document context
4. Verify session still has file_ids after 5 messages

**Validation:**
- ✅ Context persists across 5 messages
- ✅ All LLM calls include system message
- ✅ Session `attached_file_ids` unchanged

---

### Test 4: `test_adding_second_file_merges_with_existing`
**Purpose:** Verify adding second file mid-conversation merges with existing files.

**Test Flow:**
1. **Message 1:** Attach first file
2. **Message 2:** Attach second file
3. **Message 3:** No file_ids (should have both)
4. Verify session has both file IDs
5. Verify third LLM call included both documents

**Validation:**
- ✅ Session contains both file IDs
- ✅ No duplicates in `attached_file_ids`
- ✅ Both documents in LLM context

---

### Test 5: `test_new_conversation_has_empty_attached_files`
**Purpose:** Verify new conversations start with empty file context.

**Test Flow:**
1. Send message without files
2. Verify response successful
3. Check session has `attached_file_ids: []`

**Validation:**
- ✅ New session created
- ✅ Empty file list
- ✅ No file context in LLM call

---

## Performance Metrics

```
Platform: Linux 6.6.87.2-microsoft-standard-WSL2 (WSL2)
Python: 3.11.13
Pytest: 8.4.2

Test Execution:
- Total tests: 5
- Passed: 5 (100%)
- Failed: 0
- Skipped: 0
- Execution time: ~0.6 seconds

Per-test average: ~120ms
```

---

## Configuration Requirements

### Environment Variables (from conftest.py)
```bash
# MongoDB (host-mapped ports for testing outside Docker)
MONGODB_USER=copilotos_user
MONGODB_PASSWORD=secure_password_change_me
MONGODB_DATABASE=copilotos
MONGODB_URL=mongodb://user:pass@localhost:27018/copilotos?authSource=admin

# Redis (host-mapped port)
REDIS_PASSWORD=ProdRedis2024!SecurePass
REDIS_URL=redis://:ProdRedis2024!SecurePass@localhost:6380

# JWT
JWT_SECRET_KEY=<your-secret-key>
JWT_ALGORITHM=HS256
```

### Docker Services
```bash
# Start required services:
docker-compose up -d mongodb redis

# Port mappings:
# - mongodb:27017 (Docker) → localhost:27018 (Host)
# - redis:6379 (Docker) → localhost:6380 (Host)
```

---

## Key Learnings

### 1. Document Caching Architecture
**Insight:** The application uses a two-tier storage approach:
- **MongoDB**: Permanent document metadata storage
- **Redis**: Fast text cache with TTL (1 hour)

**Implication for tests:** Must cache document text in Redis, not just create MongoDB documents. Otherwise, documents are treated as "expired" and skipped.

### 2. Event Loop Management
**Insight:** Mixing session-scoped and function-scoped async fixtures causes event loop conflicts.

**Best Practice:** Use consistent scope (function) for all async fixtures in integration tests. Let the `initialize_db` fixture handle database initialization per test.

### 3. Beanie ObjectId Handling
**Insight:** Beanie Document models with auto-generated IDs require letting Beanie create them - cannot manually assign string IDs.

**Best Practice:** Never set `id` field manually in tests. Insert document first, then use the auto-generated `document.id`.

### 4. Mock Path Consistency
**Insight:** Mock paths must match actual import structure when tests run.

**Best Practice:** Use relative imports (`src.*`) consistently in both application code and tests to avoid path issues.

### 5. Redis Cleanup for Test Isolation
**Insight:** Document cache keys persist between tests if not cleaned up.

**Best Practice:** Clean both MongoDB documents AND Redis cache keys in fixture teardown:
```python
# Cleanup
await document.delete()  # MongoDB
await redis_client.delete(f"doc:text:{doc_id}")  # Redis
```

---

## Files Modified

### 1. `tests/integration/test_chat_file_context.py`
**Changes:**
- ✅ Removed session-scoped `app_lifespan` fixture
- ✅ Updated imports from `apps.api.src.*` to `src.*`
- ✅ Created `test_user_chat` fixture with proper dependencies
- ✅ Updated `auth_token` fixture to use test_user_chat
- ✅ Removed manual Document ID assignment (let Beanie generate)
- ✅ Added Redis caching in `test_document` fixture
- ✅ Added Redis caching for `document2` in merge test
- ✅ Added Redis cleanup in teardown for both fixtures
- ✅ Fixed all mock import paths

**Lines changed:** ~50 lines across fixtures and test setup

---

## Future Improvements

### 1. Shared Redis Cache Helper
Create a helper function for document caching to reduce code duplication:
```python
async def cache_document_text(doc_id: str, text: str, ttl: int = 3600):
    """Cache document text in Redis for tests."""
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.set(f"doc:text:{doc_id}", text, ex=ttl)
```

### 2. Fixture Factory for Documents
Create a factory fixture that handles both MongoDB insertion and Redis caching:
```python
@pytest_asyncio.fixture
async def document_factory(test_user_chat):
    """Factory to create documents with Redis caching."""
    documents = []

    async def create(filename: str, text: str):
        doc = Document(...)
        await doc.insert()
        await cache_document_text(str(doc.id), text)
        documents.append(doc)
        return doc

    yield create

    # Cleanup all created documents
    for doc in documents:
        await doc.delete()
        await cleanup_document_cache(str(doc.id))
```

### 3. Add Tests for Cache Expiration
Test behavior when Redis cache expires mid-conversation:
```python
async def test_expired_cache_warning():
    """Verify user gets warning when document cache expires."""
    # Create document without caching
    # Send message
    # Assert warning message about expired document
```

### 4. Add Tests for Document Ownership
Verify users cannot access documents from other users:
```python
async def test_document_ownership_validation():
    """Verify users can only access their own documents."""
    # User A creates document
    # User B tries to use it in chat
    # Assert document not included in context
```

### 5. Performance Testing
Add tests for large document sets:
```python
async def test_large_document_set_performance():
    """Verify system handles multiple large documents efficiently."""
    # Create 5 documents with 10k chars each
    # Send message with all 5 documents
    # Assert respects character limits and truncation
```

---

## References

- **Auth Tests Debug Report:** `docs/testing/INTEGRATION_TESTS_DEBUG_2025-10-19.md`
- **Test Configuration:** `apps/api/tests/integration/conftest.py`
- **Document Service:** `apps/api/src/services/document_service.py`
- **Cache Service:** `apps/api/src/services/cache_service.py`
- **Chat Session Model:** `apps/api/src/models/chat.py`

---

## Conclusion

Successfully achieved **100% pass rate** for chat integration tests by:
1. Fixing event loop scope conflicts
2. Correcting Document ID handling (auto-generation)
3. Updating import paths for test environment
4. **Adding Redis document text caching** (critical fix)
5. Ensuring proper fixture dependencies and cleanup

The test suite now reliably validates the file context persistence feature, ensuring documents attached to conversations remain accessible throughout multi-turn chat sessions. Combined with the 13 passing auth tests, we now have **18/18 integration tests passing** for core authentication and chat functionality.

**Total Integration Test Coverage:**
- ✅ Authentication: 13/13 tests (100%)
- ✅ Chat File Context: 5/5 tests (100%)
- ✅ Combined: 18/18 tests (100%)
- ⏱️ Execution time: ~2.6 seconds
