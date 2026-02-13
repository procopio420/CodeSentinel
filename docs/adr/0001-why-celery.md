# ADR 0001: Why Celery

## Status
Accepted

## Context
The AI Code Reviewer needs to process code reviews using OpenAI's API, which involves:
- Variable latency (typically 2-10 seconds per request)
- Potential rate limiting and retries
- Cost considerations (each API call costs money)
- Need to keep API response times low (< 200ms)

The API must remain responsive while reviews are being processed in the background.

## Decision
We use Celery with Redis as the broker to handle code review processing asynchronously.

## Alternatives Considered

### 1. Async FastAPI endpoints with direct OpenAI calls
- **Pros**: Simpler architecture, no separate worker process
- **Cons**: API latency would be tied to OpenAI response time (2-10s), blocking request handlers, poor user experience

### 2. Background tasks in FastAPI (BackgroundTasks)
- **Pros**: Built into FastAPI, no external dependencies
- **Cons**: Tasks run in the same process, can't scale independently, lost on server restart, no retry mechanism

### 3. Direct synchronous processing
- **Pros**: Simplest implementation
- **Cons**: Unacceptable latency (2-10s per request), poor user experience, no scalability

## Consequences

### Positive
- API remains fast and responsive (< 200ms)
- Workers can scale independently from API servers
- Built-in retry and error handling via Celery
- Can use cheaper instances for workers
- Horizontal scaling of workers based on queue depth
- Task persistence (survives restarts)

### Negative
- Additional complexity (separate worker process)
- Requires Redis for broker/result backend
- Need to manage worker lifecycle separately
- Event loop management complexity (Motor + Celery)

### Mitigations
- Use Docker Compose for local dev (simplifies running both API and worker)
- Clear separation of concerns (API vs worker)
- Comprehensive tests cover end-to-end flow

