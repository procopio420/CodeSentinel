from typing import Optional, AsyncGenerator
import json
import logging
from redis.asyncio import Redis, from_url
from .config import settings

logger = logging.getLogger(__name__)

_redis: Optional[Redis] = None


async def init_events(url: Optional[str] = None) -> Redis:
    """Initialize Redis connection for Pub/Sub events."""
    global _redis
    if _redis is None:
        # Use cache Redis URL for Pub/Sub (same Redis instance, different purpose)
        _redis = from_url(url or settings.CACHE_REDIS_URL, decode_responses=True)
    return _redis


async def get_events_redis() -> Redis:
    """Get Redis connection for events."""
    global _redis
    if _redis is None:
        await init_events()
    assert _redis is not None
    return _redis


async def close_events():
    """Close Redis connection for events."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _channel_name(submission_id: str) -> str:
    """Get Redis Pub/Sub channel name for a submission."""
    return f"submission:{submission_id}:status"


async def publish_status(submission_id: str, status: str, payload: Optional[dict] = None):
    """
    Publish a status change event for a submission.
    
    Args:
        submission_id: The submission ID
        status: Status value (pending, in_progress, completed, failed)
        payload: Optional additional data (e.g., review_id, error message)
    """
    try:
        r = await get_events_redis()
        channel = _channel_name(submission_id)
        message = {"status": status}
        if payload:
            message.update(payload)
        
        await r.publish(channel, json.dumps(message))
        logger.info(f"event_published submission_id={submission_id} status={status}")
    except Exception as e:
        logger.error(f"event_publish_failed submission_id={submission_id} error={str(e)}")


async def subscribe_status(submission_id: str) -> AsyncGenerator[dict, None]:
    """
    Subscribe to status change events for a submission.
    
    Yields:
        dict: Event data with 'status' and optional additional fields
    """
    r = await get_events_redis()
    channel = _channel_name(submission_id)
    pubsub = r.pubsub()
    
    try:
        await pubsub.subscribe(channel)
        logger.info(f"event_subscribed submission_id={submission_id} channel={channel}")
        
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield data
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"event_parse_error submission_id={submission_id} error={str(e)}")
                    continue
    except Exception as e:
        logger.error(f"event_subscribe_error submission_id={submission_id} error={str(e)}")
        raise
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()

