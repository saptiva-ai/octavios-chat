import sys
import types
import asyncio

import pytest

# ---------------------------------------------------------------------------
# Lightweight stubs to avoid heavy dependencies (beanie, minio, etc.)
# ---------------------------------------------------------------------------
beanie_mod = types.ModuleType("beanie")
operators_mod = types.ModuleType("beanie.operators")
operators_mod.Set = lambda *args, **kwargs: {"$set": args or kwargs}
operators_mod.In = lambda *args, **_kwargs: None
beanie_mod.Document = object
beanie_mod.PydanticObjectId = str
sys.modules["beanie"] = beanie_mod
sys.modules["beanie.operators"] = operators_mod

redis_cache_mod = types.ModuleType("src.core.redis_cache")
redis_cache_mod.RedisCache = object

async def dummy_get_redis_cache():
    return None

redis_cache_mod.get_redis_cache = dummy_get_redis_cache
sys.modules["src.core.redis_cache"] = redis_cache_mod

chat_helpers_mod = types.ModuleType("src.services.chat_helpers")

async def wait_for_documents_ready(*_args, **_kwargs):
    return None

chat_helpers_mod.wait_for_documents_ready = wait_for_documents_ready
sys.modules["src.services.chat_helpers"] = chat_helpers_mod

doc_module = types.ModuleType("src.models.document")


class _StubStatus:
    READY = "ready"


class _StubDocument:
    def __init__(self, *args, **kwargs):
        self.id = kwargs.get("id")
        self.status = kwargs.get("status", _StubStatus.READY)
        self.filename = kwargs.get("filename", "")
        self.content_type = kwargs.get("content_type", "")
        self.ocr_applied = kwargs.get("ocr_applied", False)

    @classmethod
    def find(cls, *_args, **_kwargs):
        raise RuntimeError("Not implemented in stub")

    @classmethod
    def find_many(cls, *_args, **_kwargs):
        class _Cursor:
            async def to_list(self, *_args, **_kwargs):
                return []

        return _Cursor()


doc_module.DocumentStatus = _StubStatus
doc_module.Document = _StubDocument
sys.modules["src.models.document"] = doc_module

chat_module = types.ModuleType("src.models.chat")
class _StubChatSession:
    pass
chat_module.ChatSession = _StubChatSession
sys.modules["src.models.chat"] = chat_module

bson_mod = types.ModuleType("bson")

class _DummyObjectId(str):
    @staticmethod
    def is_valid(value):
        return True

bson_mod.ObjectId = _DummyObjectId
sys.modules["bson"] = bson_mod

from src.services import session_context_manager
from src.services import document_service
from src.clients.file_manager import PreparedContext


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class DummySession:
    def __init__(self, attached=None):
        self.id = "sess-123"
        self.attached_file_ids = attached or []

    async def update(self, payload):
        new_ids = payload["$set"]["attached_file_ids"]
        self.attached_file_ids = new_ids


class FakeFMClient:
    def __init__(self, *_args, **_kwargs):
        pass

    async def prepare_context(self, **_kwargs):
        return PreparedContext(
            current_file_ids=["doc-1", "doc-2"],
            documents=[],
            warnings=[],
            stats={},
            combined_text="",
            session_id="sess-123",
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_session_context_manager_delegates_to_plugin(monkeypatch):
    monkeypatch.setattr(session_context_manager.settings, "attachments_v2", True)
    monkeypatch.setattr(session_context_manager, "FileManagerClient", FakeFMClient)

    chat_session = DummySession(attached=["old-doc"])

    result = await session_context_manager.SessionContextManager.prepare_session_context(
        chat_session=chat_session,
        request_file_ids=["doc-1"],
        user_id="user-1",
        redis_cache=None,
        request_id="req-abc",
    )

    assert result == ["doc-1", "doc-2"]
    assert chat_session.attached_file_ids == ["doc-1", "doc-2"]


class FakeFMClientForDocs:
    def __init__(self, *_args, **_kwargs):
        pass

    async def prepare_context(self, **_kwargs):
        return PreparedContext(
            current_file_ids=["doc-a"],
            documents=[
                {
                    "file_id": "doc-a",
                    "text": "hello world",
                    "filename": "a.txt",
                    "content_type": "text/plain",
                    "metadata": {"ocr_applied": True},
                }
            ],
            warnings=[],
            stats={},
            combined_text="hello world",
            session_id=None,
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_document_service_gets_text_via_plugin(monkeypatch):
    monkeypatch.setattr(document_service.settings, "attachments_v2", True)
    monkeypatch.setattr(document_service, "FileManagerClient", FakeFMClientForDocs)

    result = await document_service.DocumentService.get_document_text_from_cache(
        document_ids=["doc-a"],
        user_id="user-1",
    )

    assert result["doc-a"]["text"] == "hello world"
    assert result["doc-a"]["filename"] == "a.txt"
