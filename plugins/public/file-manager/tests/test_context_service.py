import sys
import types
from pathlib import Path

import pytest

# Stub external deps (minio, redis) to avoid heavy installs in unit tests
minio_mod = types.ModuleType("minio")
error_mod = types.ModuleType("minio.error")

class DummyMinio:  # pragma: no cover - used only for import resolution
    pass

class DummyS3Error(Exception):
    pass

minio_mod.Minio = DummyMinio
error_mod.S3Error = DummyS3Error
minio_mod.error = error_mod
sys.modules["minio"] = minio_mod
sys.modules["minio.error"] = error_mod

redis_mod = types.ModuleType("redis")
redis_asyncio_mod = types.ModuleType("redis.asyncio")

class DummyRedisClient:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()

    async def ping(self):
        return True

redis_asyncio_mod.Redis = DummyRedisClient
redis_mod.asyncio = redis_asyncio_mod
sys.modules["redis"] = redis_mod
sys.modules["redis.asyncio"] = redis_asyncio_mod

pypdf_mod = types.ModuleType("pypdf")

class DummyPdfReader:  # pragma: no cover - import stub
    def __init__(self, *_args, **_kwargs):
        self.pages = []

pypdf_mod.PdfReader = DummyPdfReader
sys.modules["pypdf"] = pypdf_mod

BASE_PATH = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_PATH))

from src.services import context_service  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)


class FakeCache:
    def __init__(self, data):
        self.data = data

    async def get(self, file_id):
        return self.data.get(file_id)


@pytest.mark.asyncio
async def test_prepare_context_respects_budgets(monkeypatch):
    fake_redis = FakeRedis()
    cache_data = {
        "a": {"text": "123456789", "metadata": {"filename": "a.txt", "content_type": "text/plain"}, "pages": 1},
        "b": {"text": "abcdefghij", "metadata": {"filename": "b.txt", "content_type": "text/plain"}, "pages": 2},
        "c": {"text": "short", "metadata": {"filename": "c.txt", "content_type": "text/plain"}, "pages": 1},
    }
    fake_cache = FakeCache(cache_data)

    monkeypatch.setattr(context_service, "get_extraction_cache", lambda: fake_cache)
    monkeypatch.setattr(context_service, "get_redis_client", lambda: fake_redis)

    result = await context_service.prepare_context_payload(
        user_id="user1",
        session_id="sess1",
        request_file_ids=["a", "a", "b", "c"],
        previous_file_ids=[],
        max_docs=2,
        max_chars_per_doc=5,
        max_total_chars=8,
    )

    # Should remove duplicates; current list keeps order, documents capped to max_docs=2
    assert result["current_file_ids"] == ["a", "b", "c"]
    assert len(result["documents"]) == 2

    # Texts should be truncated by per-doc and total budgets
    assert result["documents"][0]["text"] == "12345"
    assert result["documents"][1]["text"] == "abc"
    assert result["stats"]["used_chars"] == 8
    assert set(result["stats"]["truncated_docs"]) == {"a", "b"}
    assert result["stats"]["omitted_docs"] == ["c"]

    # Session mapping persisted in Redis
    assert fake_redis.data.get("session:files:sess1") == "a,b,c"
