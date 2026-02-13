import uuid
import pytest
import redis.asyncio as aioredis
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

from app.main import app
from app import db as dbmod
from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def _switch_to_temp_db():
    import motor.motor_asyncio

    client = motor.motor_asyncio.AsyncIOMotorClient(
        settings.MONGODB_URI, uuidRepresentation="standard"
    )
    db_name = f"ai_code_review_test_{uuid.uuid4().hex[:8]}"

    dbmod.client = client
    dbmod.db = client[db_name]
    dbmod.submissions = dbmod.db["submissions"]
    dbmod.reviews = dbmod.db["reviews"]

    yield

    import pymongo

    c = pymongo.MongoClient(settings.MONGODB_URI)
    try:
        c.drop_database(db_name)
    finally:
        c.close()
    try:
        client.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def _isolate_env_and_counters():
    settings.RATE_LIMIT_PER_HOUR = 3

    settings.RATE_LIMIT_REDIS_URL = getattr(
        settings, "RATE_LIMIT_REDIS_URL", "redis://localhost:6379/1"
    )
    settings.CACHE_REDIS_URL = getattr(
        settings, "CACHE_REDIS_URL", "redis://localhost:6379/2"
    )

    # Events use CACHE_REDIS_URL, so flush it
    for url in {settings.RATE_LIMIT_REDIS_URL, settings.CACHE_REDIS_URL}:
        r = aioredis.from_url(url, decode_responses=True)
        try:
            await r.flushdb()
        finally:
            await r.aclose()

    import app.rate_limit as ratelimit
    import app.cache as cache
    import app.events as events

    try:
        if getattr(ratelimit, "_rate", None) is not None:
            await ratelimit._rate.aclose()
    except Exception:
        pass
    ratelimit._rate = None

    try:
        if getattr(cache, "_redis", None) is not None:
            await cache._redis.aclose()
    except Exception:
        pass
    cache._redis = None

    try:
        if getattr(events, "_redis", None) is not None:
            await events._redis.aclose()
    except Exception:
        pass
    events._redis = None

    yield


@pytest.fixture
async def client():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def run_worker():
    async def _go(submission_id: str):
        from worker import _run as worker_run
        from app.cache import init_cache, close_cache

        await init_cache()
        try:
            await worker_run(submission_id)
        finally:
            await close_cache()

    return _go


@pytest.fixture
def stub_ai_review(monkeypatch):
    from app import ai as ai_mod

    def fake_sync(language: str, code: str):
        return {
            "score": 7,
            "issues": [
                {
                    "title": "demo",
                    "detail": "ok",
                    "severity": "low",
                    "category": "style",
                }
            ],
            "security": [],
            "performance": [],
            "suggestions": ["do X"],
        }

    monkeypatch.setattr(ai_mod, "review_code_sync", fake_sync)
    return True
