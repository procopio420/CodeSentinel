# CodeSentinel

Automated code review system built with FastAPI, MongoDB, Celery, and Redis, with a React/Vite frontend. Processes code reviews asynchronously via OpenAI, provides real-time status updates through event-driven SSE, and caches results by normalized code hash for efficiency.

---

## What it does

- Submit code for review and receive structured feedback (scores, issues, security checks, performance suggestions)
- Asynchronous processing: FastAPI API handles requests, Celery worker processes reviews in background
- Live status updates via event-driven SSE over Redis Pub/Sub (no polling)
- Caching by normalized code hash: identical submissions reuse cached reviews
- IP-based rate limiting with Redis counters (configurable, supports trusted proxies)
- Review history and analytics with server-side filtering and pagination

---

## Quickstart

### Environment

**`backend/.env`**

```dotenv
OPENAI_API_KEY=your_openai_key
MONGODB_URI=mongodb://mongo:27017
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173

CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
RATE_LIMIT_REDIS_URL=redis://redis:6379/1
RATE_LIMIT_PER_HOUR=10
CACHE_REDIS_URL=redis://redis:6379/2
CACHE_TTL_SECONDS=2592000
CACHE_PREFIX=acrev:
```

**Optional:**

```dotenv
TRUSTED_PROXY_HEADERS=false  # Enable if behind reverse proxy
```

**`frontend/.env`**

```dotenv
VITE_BACKEND_URL=http://localhost:8000
```

### Run

```bash
# Services (MongoDB, Redis, API, Worker)
docker compose up -d --build

# Frontend (dev)
cd frontend && npm i && npm run dev

# Tests
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt && pytest -q
```

---

## Architecture

API + background worker pattern. FastAPI handles HTTP requests and returns immediately; Celery worker processes reviews asynchronously. Redis serves four roles: Celery broker/results backend, rate limiting counters, code hash cache, and Pub/Sub event bus. MongoDB is the source of truth for submissions and reviews.

```
Client → FastAPI → MongoDB
              ↓
         Celery Queue (Redis)
              ↓
         Worker → OpenAI
              ↓
         Redis Pub/Sub → SSE → Client
```

**Flow**: `POST /api/reviews` creates submission, enqueues task, returns 202. Worker processes review, publishes status events to Redis Pub/Sub. SSE endpoint subscribes and streams updates to clients.

---

## API

OpenAPI docs: `GET /docs` • Redoc: `GET /redoc`

**Submit**
```
POST /api/reviews
Body: { "language": "python", "code": "..." }
202 → { "id": "...", "status": "pending" | "completed" }
```
Cache hit returns `completed` immediately. Rate limit: 429 if exceeded.

**Stream** (SSE)
```
GET /api/reviews/{id}/stream?ping=15000
Events: status (pending|in_progress|completed|failed), done (final payload)
```
Event-driven via Redis Pub/Sub. Worker publishes, SSE subscribes and forwards.

**Get**
```
GET /api/reviews/{id}
200 → { "id": "...", "status": "...", "score": 1..10, "issues": [...], ... }
```

**List**
```
GET /api/reviews?language=python&status=completed&page=1&page_size=20&min_score=6&max_score=10
200 → { "items": [...], "total": N, "page": 1, "page_size": 20 }
```
Server-side filtering: `language`, `status`, `min_score`, `max_score`, `start_date`, `end_date`.

**Stats**
```
GET /api/stats?language=python
200 → { "total": 123, "avg_score": 7.4, "common_issues": [...] }
```

---

## Caching and privacy

Identical code submissions (same language + normalized code) share the same cached review. If you submit code that was previously reviewed, you receive the cached result immediately. The cached review may have been generated for a different user; this is intentional for cost efficiency and performance.

Cache keys are scoped (default: `"public"`) to allow future per-user/org scoping without breaking existing behavior.

---

## Rate limiting and proxies

IP-based rate limiting using Redis counters (default: 10 requests/hour per IP).

If behind a reverse proxy (nginx, Cloudflare, etc.), set `TRUSTED_PROXY_HEADERS=true` to extract client IP from `X-Forwarded-For` (takes first public IP). **Security**: Only enable if you trust your proxy; otherwise clients could spoof IPs.

---

## Development

**Local setup:**
```bash
docker compose up -d  # MongoDB, Redis
cd backend && uvicorn app.main:app --reload
celery -A app.queue.celery worker -l info  # Separate terminal
cd frontend && npm run dev
```

**Tests:**
```bash
cd backend && pytest -q
```

**Reset (dev only):**
```bash
docker compose exec mongo mongosh --eval 'db.getSiblingDB("ai_code_review").dropDatabase()'
docker compose exec redis redis-cli FLUSHALL
```

Design decisions and challenges: [docs/overview.md](docs/overview.md)

**ADRs:**
- [ADR 0001: Why Celery](docs/adr/0001-why-celery.md) - Background task processing
- [ADR 0002: Why SSE](docs/adr/0002-why-sse.md) - Real-time status updates

---

## Deployed URLs

- **Frontend:** [https://ai-code-reviewer-nine-topaz.vercel.app/](https://ai-code-reviewer-nine-topaz.vercel.app/)
- **Backend API:** [https://ai-code-reviewer-a771.onrender.com/api/](https://ai-code-reviewer-a771.onrender.com/api/)
- **API Docs:** [https://ai-code-reviewer-a771.onrender.com/docs](https://ai-code-reviewer-a771.onrender.com/docs)
