from fastapi import APIRouter, Request, Query, Response, status
from datetime import datetime
from bson import ObjectId
from typing import Optional
import asyncio
import json
import logging

from sse_starlette.sse import EventSourceResponse

from ..schemas import ReviewCreate, ReviewOut, ReviewAccepted, PaginatedReviewsOut
from ..rate_limit import limit_check, extract_client_ip
from ..queue import celery
from ..cache import code_hash as compute_hash, cache_get_review_id
from ..events import subscribe_status
from .. import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


async def get_reviews_for_submission(id: str) -> ReviewOut:
    submission = await db.submissions.find_one({"_id": ObjectId(id)})
    if not submission:
        raise ValueError("Not found")

    score = issues = security = performance = suggestions = None

    if submission.get("review_id"):
        review = await db.reviews.find_one({"_id": submission["review_id"]})
        if review:
            score = review.get("score")
            issues = review.get("issues", [])
            security = review.get("security", [])
            performance = review.get("performance", [])
            suggestions = review.get("suggestions", [])

    return ReviewOut(
        id=str(submission["_id"]),
        status=submission["status"],
        created_at=submission["created_at"],
        updated_at=submission["updated_at"],
        language=submission["language"],
        score=score,
        issues=issues,
        security=security,
        performance=performance,
        suggestions=suggestions,
        error=submission.get("error"),
    )


@router.post("", response_model=ReviewAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_review(payload: ReviewCreate, request: Request, response: Response):
    ip = extract_client_ip(request)
    await limit_check(ip)

    now = datetime.utcnow().isoformat()
    code_hash = compute_hash(payload.language, payload.code)

    cached_review_id = await cache_get_review_id(code_hash)
    if cached_review_id:
        doc = {
            "code": payload.code,
            "language": payload.language,
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "ip": ip,
            "review_id": ObjectId(cached_review_id),
            "error": None,
            "code_hash": code_hash,
        }
        res = await db.submissions.insert_one(doc)
        submission_id = str(res.inserted_id)
        logger.info(f"submission_created submission_id={submission_id} language={payload.language} code_length={len(payload.code)} code_hash={code_hash[:16]}... cache_hit=true ip={ip}")
        return ReviewAccepted(id=submission_id, status="completed")

    submission = {
        "code": payload.code,
        "language": payload.language,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "ip": ip,
        "review_id": None,
        "error": None,
        "code_hash": code_hash,
    }
    result = await db.submissions.insert_one(submission)
    submission_id = str(result.inserted_id)

    celery.send_task("process_review", args=[submission_id])
    logger.info(f"submission_created submission_id={submission_id} language={payload.language} code_length={len(payload.code)} code_hash={code_hash[:16]}... cache_hit=false ip={ip}")

    response.headers["Location"] = f"/api/reviews/{submission_id}"

    return ReviewAccepted(id=submission_id, status="pending")


@router.get("/{id}", response_model=ReviewOut)
async def get_review(id: str):
    return await get_reviews_for_submission(id)


@router.get("", response_model=PaginatedReviewsOut)
async def list_reviews(
    language: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[int] = Query(None, ge=1, le=10),
    max_score: Optional[int] = Query(None, ge=1, le=10),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    # Build match stage for submissions
    match_stage = {}
    if language:
        match_stage["language"] = language
    if status:
        match_stage["status"] = status
    if start_date or end_date:
        created = {}
        if start_date:
            created["$gte"] = start_date
        if end_date:
            created["$lte"] = end_date
        match_stage["created_at"] = created

    # Build aggregation pipeline with lookup
    pipeline = [
        {"$match": match_stage},
        {
            "$lookup": {
                "from": "reviews",
                "localField": "review_id",
                "foreignField": "_id",
                "as": "review"
            }
        },
        {"$unwind": {"path": "$review", "preserveNullAndEmptyArrays": True}},
    ]

    # Filter by score if specified (in DB, not memory)
    if min_score is not None or max_score is not None:
        score_match = {}
        if min_score is not None:
            score_match["$gte"] = min_score
        if max_score is not None:
            score_match["$lte"] = max_score
        # Only match submissions that have reviews with scores in range
        pipeline.append({
            "$match": {
                "review.score": score_match
            }
        })

    # Count total before pagination
    count_pipeline = pipeline + [{"$count": "total"}]
    count_result = await db.submissions.aggregate(count_pipeline).to_list(length=1)
    total = count_result[0]["total"] if count_result else 0

    # Add sort and pagination
    pipeline.extend([
        {"$sort": {"created_at": -1}},
        {"$skip": (page - 1) * page_size},
        {"$limit": page_size},
    ])

    # Execute aggregation
    submissions = await db.submissions.aggregate(pipeline).to_list(length=page_size)

    # Convert to ReviewOut format
    reviews = [
        await get_reviews_for_submission(str(sub["_id"]))
        for sub in submissions
    ]

    return PaginatedReviewsOut(
        items=reviews,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}/stream")
async def stream_review(
    id: str,
    interval_ms: int = Query(1000, ge=10, le=60000),
    ping: int = Query(15000, ge=0, le=60000),
):
    async def event_gen():
        try:
            oid = ObjectId(id)
        except Exception:
            yield {"event": "error", "data": "invalid_id"}
            return

        # Emit current status immediately
        sub = await db.submissions.find_one({"_id": oid})
        if not sub:
            yield {"event": "error", "data": "not_found"}
            return

        status_val = sub.get("status", "pending")
        yield {"event": "status", "data": status_val}

        # If already terminal, send done and exit
        if status_val in ("completed", "failed"):
            payload = {"status": status_val}
            if sub.get("review_id"):
                review = await db.reviews.find_one({"_id": sub["review_id"]})
                if review:
                    review["_id"] = str(review["_id"])
                    if "submission_id" in review:
                        review["submission_id"] = str(review["submission_id"])
                payload["review"] = review
            yield {"event": "done", "data": json.dumps(payload)}
            return

        # Subscribe to events and stream updates
        try:
            async for event_data in subscribe_status(id):
                event_status = event_data.get("status")
                if event_status:
                    yield {"event": "status", "data": event_status}

                # If terminal status, fetch full review and send done
                if event_status in ("completed", "failed"):
                    # Re-fetch submission to get latest review_id
                    sub = await db.submissions.find_one({"_id": oid})
                    if sub:
                        payload = {"status": event_status}
                        if sub.get("review_id"):
                            review = await db.reviews.find_one({"_id": sub["review_id"]})
                            if review:
                                review["_id"] = str(review["_id"])
                                if "submission_id" in review:
                                    review["submission_id"] = str(review["submission_id"])
                            payload["review"] = review
                        yield {"event": "done", "data": json.dumps(payload)}
                    return
        except Exception as e:
            logger.error(f"sse_subscribe_error submission_id={id} error={str(e)}")
            # Fallback to polling if Pub/Sub fails
            while True:
                await asyncio.sleep(interval_ms / 1000.0)
                sub = await db.submissions.find_one({"_id": oid})
                if not sub:
                    yield {"event": "error", "data": "not_found"}
                    return

                status_val = sub.get("status", "pending")
                yield {"event": "status", "data": status_val}

                if status_val in ("completed", "failed"):
                    payload = {"status": status_val}
                    if sub.get("review_id"):
                        review = await db.reviews.find_one({"_id": sub["review_id"]})
                        if review:
                            review["_id"] = str(review["_id"])
                            if "submission_id" in review:
                                review["submission_id"] = str(review["submission_id"])
                        payload["review"] = review
                    yield {"event": "done", "data": json.dumps(payload)}
                    return

    return EventSourceResponse(
        event_gen(),
        ping=None if ping == 0 else ping,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
