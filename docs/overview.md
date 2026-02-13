# Design Notes & Challenges

## Architecture Decisions

We chose FastAPI + Motor for a fully async API that scales under concurrent I/O with Mongo, Redis, and OpenAI. Celery isolates slow/variable LLM calls, keeping API latency low and enabling horizontal scaling. Redis plays three roles: Celery broker/results, precise rate limiting, and a cache that deduplicates repeated submissions by `(language + code)` SHA-256, reducing cost and turnaround.

Reviews follow a schema-driven prompt with a rubric, producing consistent scores and structured issues (`title`, `detail`, `severity`, `category`). We request JSON-only outputs and normalize values before persisting. Data is stored in Mongo to power history and analytics; we denormalize minimal fields (e.g., `language`) for efficient filtering. Aggregations compute averages and common issues using `$unwind`/`$group`/`$sort`, backed by indexes.

SSE provides event-driven live status updates without polling. The worker publishes status changes to Redis Pub/Sub, and the SSE endpoint subscribes and forwards events to clients. We ship anti-buffering headers and periodic `ping` to keep connections healthy through proxies; the client treats "incomplete chunk" closes after `done` as normal. The frontend uses Vite + TS with shadcn/ui for accessible components (Progress, Cards) and next-themes for dark mode. A small status→progress map clarifies task state, and a live list surfaces active submissions; clicking opens details and hides the editor.

## Scalability

API and worker scale independently; Redis/Mongo can be managed services. With higher volume, we would add idempotent enqueue locks, bulk updates, structured logging, alerts, and per-user auth/quotas. We'd also ship richer diffs, more granular analytics per language and pre-warmed cache for common snippets.

## Challenges & Solutions

### CORS Configuration
Strict CORS (credentials vs wildcard) required explicit origin list (not wildcard) with `allow_credentials=False`.

### SSE Connection Lifecycle
SSE lifecycle quirks in browsers required anti-buffering headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`) and periodic ping events (15s default) to keep connections healthy through proxies.

### Event Loop Management
Event loop management in tests/workers was complex. In tests we hit "Event loop is closed" from Motor during teardown; we fixed this by:
- Running the app under a lifespan manager
- Using httpx AsyncClient with ASGI transport
- Avoiding truthiness checks on Motor Database (use `db is not None`)
- Passing a per-test DB into `init_db(_db)`
- Dropping it before the loop closes

In the Celery worker we saw loop errors after forking; we isolated each task with `asyncio.run(...)`, initialized Mongo inside the worker process (instead of reusing API globals), and switched to `redis.asyncio` to avoid aioredis import conflicts.

### Async Mongo Initialization
For dev startup we moved DB init and index creation into FastAPI's lifespan, which removed race conditions at boot.

### Pydantic Validation
We normalized Pydantic payloads and categories to satisfy strict validators, handling varied JSON structures from OpenAI with custom validators in `ReviewOut` schema.

## Trade-offs

Trade-offs prioritized core functionality and clear extension points. Tests cover rate limiting, stats, SSE, cache hits, and end-to-end flow.

