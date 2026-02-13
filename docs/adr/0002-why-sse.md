# ADR 0002: Why SSE (Server-Sent Events)

## Status
Accepted

## Context
Users submit code for review and need to see real-time status updates as the review progresses:
- `pending` → `in_progress` → `completed` (or `failed`)

The frontend needs to display live progress without constant polling that wastes bandwidth and server resources.

## Decision
We use Server-Sent Events (SSE) for one-way real-time updates from server to client, with an event-driven architecture using Redis Pub/Sub.

## Alternatives Considered

### 1. Polling (HTTP GET every N seconds)
- **Pros**: Simple to implement, works everywhere
- **Cons**: Wastes bandwidth, adds latency (up to N seconds), increases server load, inefficient

### 2. WebSockets
- **Pros**: Full bidirectional communication, lower overhead per message
- **Cons**: More complex (connection management, reconnection logic), requires library, overkill for one-way updates, harder to debug

### 3. Long polling
- **Pros**: Works through most proxies
- **Cons**: More complex than SSE, still requires connection management, less efficient than SSE

## Consequences

### Positive
- Simple HTTP-based protocol (no special libraries needed)
- Browser native support (EventSource API)
- Automatic reconnection built into browsers
- Works through proxies and firewalls
- Event-driven: no polling overhead (after initial implementation)
- One-way communication matches our use case perfectly

### Negative
- One-way only (but we don't need bidirectional)
- Requires keepalive pings to prevent proxy timeouts
- Connection management needed (cleanup on client disconnect)

### Implementation Notes
- Use Redis Pub/Sub for event bus (worker publishes, SSE endpoint subscribes)
- Emit current status immediately, then stream updates
- Send `event: done` with final payload when status is terminal
- Keep 15s ping interval to avoid proxy timeouts
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`

