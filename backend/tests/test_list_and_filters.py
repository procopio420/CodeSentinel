import pytest
from datetime import datetime
from bson import ObjectId
from app import db as dbmod


@pytest.mark.asyncio
async def test_list_filters(client):
    now = datetime.utcnow().isoformat()
    r1 = await dbmod.reviews.insert_one(
        {"submission_id": ObjectId(), "score": 9, "issues": [], "created_at": now}
    )
    r2 = await dbmod.reviews.insert_one(
        {"submission_id": ObjectId(), "score": 4, "issues": [], "created_at": now}
    )
    await dbmod.submissions.insert_one(
        {
            "code": "print('ok')",
            "language": "python",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "ip": "1.1.1.1",
            "review_id": r1.inserted_id,
            "error": None,
        }
    )
    await dbmod.submissions.insert_one(
        {
            "code": "console.log('ok')",
            "language": "javascript",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "ip": "1.1.1.1",
            "review_id": r2.inserted_id,
            "error": None,
        }
    )

    resp_all = await client.get("/api/reviews?page=1&page_size=10")
    assert resp_all.status_code == 200
    data = resp_all.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    items = data["items"]
    assert len(items) >= 2

    resp = await client.get("/api/reviews?language=python&min_score=5")
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert all(it["language"] == "python" for it in items)
    assert all((it["score"] or 0) >= 5 for it in items)
