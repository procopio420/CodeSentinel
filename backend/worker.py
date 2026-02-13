import asyncio
import time
import logging
from datetime import datetime
from bson import ObjectId
from celery.signals import worker_process_init, worker_shutdown

from app.queue import celery
from app.ai import review_code_sync
from app import db as dbmod
from app.db import init_db_sync, close_db_sync
from app.cache import init_cache, close_cache, cache_set_review_id
from app.events import init_events, close_events, publish_status

logger = logging.getLogger(__name__)

_LOOP: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def _on_worker_process_init(**_):
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        init_db_sync()
        _LOOP.run_until_complete(init_cache())
        _LOOP.run_until_complete(init_events())


@worker_shutdown.connect
def _on_worker_shutdown(**_):
    global _LOOP
    try:
        if _LOOP is not None:
            _LOOP.run_until_complete(close_events())
            _LOOP.run_until_complete(close_cache())
        close_db_sync()
    finally:
        if _LOOP is not None:
            _LOOP.close()
            _LOOP = None


@celery.task(name="process_review")
def process_review(submission_id: str):
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
        init_db_sync()
        _LOOP.run_until_complete(init_cache())
        _LOOP.run_until_complete(init_events())
    return _LOOP.run_until_complete(_run(submission_id))


async def _run(submission_id: str):
    start_time = time.time()
    
    sub = await dbmod.submissions.find_one({"_id": ObjectId(submission_id)})
    if not sub:
        logger.error(f"submission_not_found submission_id={submission_id}")
        return None

    await dbmod.submissions.update_one(
        {"_id": sub["_id"]}, {"$set": {"status": "in_progress"}}
    )
    await publish_status(submission_id, "in_progress")
    logger.info(f"status_transition submission_id={submission_id} status=pending->in_progress")

    try:
        data = review_code_sync(sub["language"], sub["code"])
        doc = {
            "submission_id": sub["_id"],
            **data,
            "created_at": datetime.utcnow().isoformat(),
        }
        ins = await dbmod.reviews.insert_one(doc)

        code_hash = sub.get("code_hash")
        cache_hit = False
        if code_hash:
            await cache_set_review_id(code_hash, str(ins.inserted_id))
            cache_hit = True

        await dbmod.submissions.update_one(
            {"_id": sub["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "review_id": ins.inserted_id,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )
        duration_ms = int((time.time() - start_time) * 1000)
        await publish_status(submission_id, "completed", {"review_id": str(ins.inserted_id), "duration_ms": duration_ms})
        logger.info(f"status_transition submission_id={submission_id} status=in_progress->completed duration_ms={duration_ms} cache_hit={cache_hit} review_id={str(ins.inserted_id)}")
    except Exception as e:
        error_msg = str(e)
        duration_ms = int((time.time() - start_time) * 1000)
        await dbmod.submissions.update_one(
            {"_id": sub["_id"]},
            {
                "$set": {
                    "status": "failed",
                    "error": error_msg,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )
        await publish_status(submission_id, "failed", {"error": error_msg})
        logger.error(f"status_transition submission_id={submission_id} status=in_progress->failed duration_ms={duration_ms} error={error_msg}")
    return True
