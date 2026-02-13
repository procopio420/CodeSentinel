import asyncio
import json
from datetime import datetime
from bson import ObjectId
import pytest
from app import db as dbmod


@pytest.mark.asyncio
async def test_post_returns_202_and_location(client):
    payload = {"language": "python", "code": "print('ok')"}
    r = await client.post("/api/reviews", json=payload)
    assert r.status_code == 202
    body = r.json()
    assert "id" in body and isinstance(body["id"], str)
    assert r.headers.get("Location") == f"/api/reviews/{body['id']}"


@pytest.mark.asyncio
async def test_sse_immediate_done(client):
    now = datetime.utcnow().isoformat()
    review_doc = {
        "submission_id": ObjectId(),
        "score": 8,
        "issues": [{"title": "X", "detail": "Y", "severity": "med", "category": "bug"}],
        "security": [],
        "performance": [],
        "suggestions": [],
        "created_at": now,
    }
    r_ins = await dbmod.reviews.insert_one(review_doc)
    sub_id = ObjectId()
    await dbmod.submissions.insert_one(
        {
            "_id": sub_id,
            "code": "print('ok')",
            "language": "python",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "ip": "127.0.0.1",
            "review_id": r_ins.inserted_id,
            "error": None,
        }
    )

    statuses = []
    async with client.stream(
        "GET",
        f"/api/reviews/{sub_id}/stream?interval_ms=50&ping=0",
        timeout=2.0,
    ) as s:
        event = None
        data_lines = []
        async for line in s.aiter_lines():
            line = line.strip()
            if not line:
                if event == "status":
                    statuses.append("".join(data_lines))
                elif event == "done":
                    payload = json.loads("".join(data_lines))
                    assert payload["status"] == "completed"
                    assert "review" in payload and isinstance(payload["review"], dict)
                    break
                event, data_lines = None, []
                continue
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

    assert any(s in ("completed",) for s in statuses)


@pytest.mark.asyncio
async def test_sse_transition_to_done(client):
    now = datetime.utcnow().isoformat()
    sub_id = ObjectId()
    await dbmod.submissions.insert_one(
        {
            "_id": sub_id,
            "code": "print('sse')",
            "language": "python",
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "ip": "127.0.0.1",
            "review_id": None,
            "error": None,
        }
    )

    async def finisher():
        await asyncio.sleep(0.1)
        # Publish in_progress event
        from app.events import publish_status
        await publish_status(str(sub_id), "in_progress")
        await asyncio.sleep(0.05)
        
        r_ins = await dbmod.reviews.insert_one(
            {
                "submission_id": sub_id,
                "score": 7,
                "issues": [
                    {
                        "title": "late",
                        "detail": "arrived",
                        "severity": "low",
                        "category": "test",
                    }
                ],
                "security": [],
                "performance": [],
                "suggestions": [],
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        await dbmod.submissions.update_one(
            {"_id": sub_id},
            {
                "$set": {
                    "status": "completed",
                    "review_id": r_ins.inserted_id,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )
        # Publish completed event
        await publish_status(str(sub_id), "completed", {"review_id": str(r_ins.inserted_id)})

    fin_task = asyncio.create_task(finisher())

    statuses = []
    async with client.stream(
        "GET",
        f"/api/reviews/{sub_id}/stream?interval_ms=50&ping=0",
        timeout=3.0,
    ) as s:
        event = None
        data_lines = []
        async for line in s.aiter_lines():
            line = line.strip()
            if not line:
                if event == "status":
                    statuses.append("".join(data_lines))
                elif event == "done":
                    payload = json.loads("".join(data_lines))
                    assert payload["status"] == "completed"
                    break
                event, data_lines = None, []
                continue
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

    await fin_task
    assert any(s in ("pending", "in_progress", "completed") for s in statuses)


@pytest.mark.asyncio
async def test_sse_invalid_id_errors_immediately(client):
    async with client.stream(
        "GET", "/api/reviews/not-a-valid-id/stream?ping=0", timeout=2.0
    ) as s:
        lines = []
        async for line in s.aiter_lines():
            lines.append(line)
            if line.strip() == "":
                break
        frame = "\n".join(lines)
        assert "event: error" in frame and "data: invalid_id" in frame
