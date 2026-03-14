# Performance Benchmarking Plan

**Author:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Status:** Ready for implementation

---

## 1. Performance Budgets

Budgets derived from actual code paths in the Calloway codebase. Every console route hits `console_queries.py` (synchronous DB via `get_db_connection()`), renders a Jinja2 template, and returns HTML. The message pipeline runs synchronously in `asyncio.to_thread()` after the webhook returns 200.

### 1.1 Console Pages

| Route | Key Queries | Budget (p95) | Notes |
|-------|-------------|-------------|-------|
| `GET /console/dashboard` | `get_system_pulse` (5 queries), `get_recent_activity` (1 JOIN), `get_agents_needing_attention` (2 queries) | **400ms** | 8 DB round-trips in sequence; biggest risk |
| `GET /console/tenants` (10 agents) | `get_all_agents` (1 query with 4 correlated subqueries) | **200ms** | Subqueries scale per-agent |
| `GET /console/tenants` (100 agents) | Same | **500ms** | Correlated subqueries become expensive |
| `GET /console/tenants` (1000 agents) | Same | **2000ms** | Likely needs pagination/materialization |
| `GET /console/tenants/{id}` | `get_agent_detail` (7 queries in one connection) | **300ms** | Serial queries; contacts list unbounded |
| `GET /console/tenants/{id}/tab/messages` | `get_conversations_by_contact` (paginated) | **200ms** | Already paginated (25/page) |
| `GET /console/tenants/{id}/tab/messages/{cid}` | `get_conversation_thread` (paginated 50) | **150ms** | Single query with LIMIT |
| `GET /console/tenants/{id}/tab/knowledge-base` | `get_knowledge_base_items` + `get_kb_settings` | **250ms** | Aggregation over embeddings table |
| `GET /console/conversations` | `get_recent_conversations` (JOIN + 2 subqueries per row, LIMIT 100) + `get_all_agents` | **500ms** | Per-row subqueries are the bottleneck |
| `GET /console/conversations/{id}` | `get_conversation_detail` (4 queries) | **200ms** | Bounded by message count per conversation |
| `GET /console/triggers` | `get_trigger_queue` (1 JOIN) + `get_all_agents` | **200ms** | Simple query |
| `GET /console/health` | `get_health_overview` (DB ping, Redis ping, 3 queries) + `get_recent_errors` (1 JOIN) + `get_all_agents` | **600ms** | Redis ping + PERCENTILE_CONT on `tool_executions` |
| `GET /console/billing` | `get_billing_summary` + `get_cost_summary` (2 queries) + `get_cost_by_agent` (1 aggregation) + `get_model_tier_breakdown` (1 aggregation) | **500ms** | 4 separate DB calls + billing service |

### 1.2 Message Pipeline

| Stage | Code Path | Budget (p95) | Notes |
|-------|-----------|-------------|-------|
| Webhook receipt to 200 | `twilio_inbound`: parse form, validate Twilio signature, lookup agent by number, enqueue `BackgroundTasks` | **50ms** | Must be fast; Twilio times out at 15s |
| Normalize | `normalize_twilio_event` | **5ms** | Pure Python dict mapping |
| Resolve contact | `resolve_contact` — DB lookup by phone | **20ms** | Single indexed query |
| TCPA check | `check_tcpa_keywords` — keyword match + DB update | **15ms** | Regex + conditional write |
| Rate limiting | `check_rate_limits` — Redis check | **10ms** | Redis GET/INCR |
| Classify intent | `classify_intent` — may call Haiku for ambiguous | **800ms** (with LLM) / **5ms** (rule-based) | LLM call dominates when triggered |
| Context assembly | `assemble_context` — history + listings + triggers + summary lookup | **100ms** | 3-5 DB queries depending on intent |
| RAG search | `rag_service.search` — embedding + pgvector cosine similarity | **150ms** | Embedding API call (~80ms) + vector search (~50ms) |
| LLM call (Haiku) | `AnthropicClient` with retry | **1500ms** | Network-bound; Haiku is fast |
| LLM call (Sonnet) | `AnthropicClient` with retry | **4000ms** | Sonnet is slower, used for complex reasoning |
| Dispatch | `dispatch` — send SMS/email + log + update metrics | **200ms** | Twilio API call + 3 DB writes |
| **End-to-end (Haiku path)** | Webhook background task complete | **2500ms** | |
| **End-to-end (Sonnet path)** | Webhook background task complete | **5500ms** | |

### 1.3 Database Query Targets

| Scale | `get_all_agents` | `get_recent_conversations` | `get_system_pulse` | `messages` table scan |
|-------|-----------------|---------------------------|-------------------|-----------------------|
| 10 agents | <50ms | <100ms | <80ms | <50ms |
| 100 agents | <200ms | <300ms | <150ms | <200ms |
| 1,000 agents | <1000ms | <800ms | <400ms | <500ms |
| 10,000 agents | Needs pagination | Needs pagination | <800ms | Needs partitioning |

### 1.4 Connection Pool

| Metric | Target |
|--------|--------|
| Pool utilization (avg) | <60% |
| Pool utilization (peak) | <85% |
| Connection wait time (p95) | <50ms |
| Idle connections | 2-5 |

---

## 2. Timing Middleware

Drop-in FastAPI middleware that records per-route latency and exposes p50/p95/p99. Uses an in-memory ring buffer to avoid external dependencies.

### File: `app/middleware/timing.py`

```python
"""Request timing middleware — records per-route p50/p95/p99 latency."""
import time
import logging
from collections import defaultdict, deque
from statistics import quantiles

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Ring buffer per route: stores last N request durations in ms
_BUFFER_SIZE = 500
_timings: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_BUFFER_SIZE))


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Use the route path template, not the actual URL (avoids cardinality explosion)
        route = request.scope.get("path", request.url.path)
        if request.scope.get("route"):
            route = request.scope["route"].path

        _timings[route].append(elapsed_ms)
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        # Log slow requests
        if elapsed_ms > 1000:
            logger.warning(
                "Slow request: %s %s took %.0fms",
                request.method, route, elapsed_ms,
            )

        return response


def get_route_stats() -> dict[str, dict]:
    """Return p50/p95/p99 for each route. Call from health/debug endpoint."""
    stats = {}
    for route, times in _timings.items():
        if len(times) < 2:
            continue
        sorted_times = sorted(times)
        n = len(sorted_times)
        stats[route] = {
            "count": n,
            "p50": round(sorted_times[n // 2], 1),
            "p95": round(sorted_times[int(n * 0.95)], 1),
            "p99": round(sorted_times[int(n * 0.99)], 1),
            "max": round(sorted_times[-1], 1),
        }
    return stats
```

### Wiring into `app/main.py`

```python
from app.middleware.timing import TimingMiddleware
app.add_middleware(TimingMiddleware)
```

### Debug endpoint (add to console or health router)

```python
from app.middleware.timing import get_route_stats

@router.get("/debug/perf")
async def perf_stats(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    from fastapi.responses import JSONResponse
    return JSONResponse(get_route_stats())
```

---

## 3. Database Query Profiling

### 3.1 Slow Query Identification

Run these against the Supabase/PostgreSQL instance to find actual bottlenecks.

```sql
-- Enable pg_stat_statements (already on in Supabase)
-- Find the 20 slowest queries by total time
SELECT
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    round(max_exec_time::numeric, 1) AS max_ms,
    rows,
    left(query, 120) AS query_preview
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;
```

```sql
-- Queries with the most total execution time (cumulative cost)
SELECT
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    rows,
    left(query, 120) AS query_preview
FROM pg_stat_statements
WHERE calls > 5
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 3.2 EXPLAIN ANALYZE for Critical Queries

Run each of these and verify the planner uses indexes, not sequential scans.

**Dashboard — system pulse (messages count, 24h window)**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT COUNT(*) FROM messages
WHERE created_at > now() - interval '24 hours';
-- Expected: Index Scan on idx_messages_agent_created
-- Watch for: Seq Scan if index isn't covering the filter
```

**Dashboard — errors count**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT COUNT(*) FROM tool_executions
WHERE error_message IS NOT NULL
AND created_at > now() - interval '24 hours';
-- Expected: Index Scan on idx_tool_executions_errors + filter on created_at
```

**Tenant list — correlated subqueries (the most expensive console query)**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT a.*,
    (SELECT COUNT(*) FROM contacts WHERE agent_id = a.id) as contact_count,
    (SELECT COALESCE(SUM(messages_sent), 0) FROM usage_metrics
     WHERE agent_id = a.id AND date = CURRENT_DATE) as messages_today,
    (SELECT MAX(date) FROM usage_metrics WHERE agent_id = a.id) as last_active,
    (SELECT COUNT(*) FROM tool_executions
     WHERE agent_id = a.id AND error_message IS NOT NULL
     AND created_at > now() - interval '24 hours') as errors_24h
FROM agents a ORDER BY a.name;
-- Watch for: Nested Loop with Seq Scan on contacts/tool_executions at scale
-- Fix: Add composite indexes or rewrite as LEFT JOIN with GROUP BY
```

**Conversation list — per-row subqueries**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT cv.id, cv.channel, cv.last_message_at,
    a.name as agent_name, c.name as contact_name,
    (SELECT COUNT(*) FROM messages WHERE conversation_id = cv.id) as msg_count,
    (SELECT body FROM messages WHERE conversation_id = cv.id
     ORDER BY created_at DESC LIMIT 1) as last_message
FROM conversations cv
JOIN agents a ON cv.agent_id = a.id
LEFT JOIN contacts c ON cv.contact_id = c.id
ORDER BY cv.last_message_at DESC NULLS LAST
LIMIT 100;
-- Watch for: 200 subquery executions (2 per row x 100 rows)
-- Fix: Lateral join or window function
```

**Health page — PERCENTILE_CONT (expensive aggregate)**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    AVG(latency_ms) as avg_latency,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
FROM tool_executions
WHERE created_at > now() - interval '24 hours'
AND latency_ms IS NOT NULL;
-- Watch for: Sort cost on large tool_executions table
```

**Pipeline — conversation history lookup**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT m.* FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.agent_id = 'AGENT_UUID_HERE' AND c.contact_id = 'CONTACT_UUID_HERE'
ORDER BY m.created_at DESC LIMIT 20;
-- Expected: Index Scan on idx_conversations_agent_contact, then idx_messages_conversation_created
```

**RAG — pgvector cosine similarity**
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT id, content, source_type,
    1 - (embedding <=> '[0.1,0.2,...]'::vector) as similarity
FROM embeddings
WHERE agent_id = 'AGENT_UUID_HERE'
ORDER BY embedding <=> '[0.1,0.2,...]'::vector
LIMIT 5;
-- Expected: Index Scan using idx_embeddings_vector (HNSW)
-- Watch for: If HNSW index not used, check ef_search parameter
```

### 3.3 Missing Index Check

```sql
-- Tables with sequential scans that should have indexes
SELECT
    schemaname, relname,
    seq_scan, seq_tup_read,
    idx_scan, idx_tup_fetch,
    n_live_tup
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
AND n_live_tup > 1000
ORDER BY seq_tup_read DESC;
```

### 3.4 Connection Pool Monitoring

```sql
-- Current connection count and state
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;

-- Long-running queries (>5s)
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 seconds'
AND state != 'idle';
```

---

## 4. Load Testing

### 4.1 Locust Configuration

Locust is the right tool here: Python-native, easy to script, works locally and in CI.

### File: `benchmarks/locustfile.py`

```python
"""Load test for Calloway console and webhook endpoints."""
import os
from locust import HttpUser, task, between, tag


CONSOLE_PASSWORD = os.getenv("CONSOLE_PASSWORD", "test-password")


class ConsoleUser(HttpUser):
    """Simulates an operator browsing the console."""
    wait_time = between(1, 3)
    host = os.getenv("TARGET_HOST", "http://localhost:8000")

    def on_start(self):
        """Login to get session cookie."""
        self.client.post("/console/login", data={"password": CONSOLE_PASSWORD})

    @tag("console", "dashboard")
    @task(5)
    def dashboard(self):
        self.client.get("/console/dashboard", name="/console/dashboard")

    @tag("console", "tenants")
    @task(3)
    def tenant_list(self):
        self.client.get("/console/tenants", name="/console/tenants")

    @tag("console", "tenants")
    @task(2)
    def tenant_detail(self):
        # Uses a known agent ID; set via env or discover dynamically
        agent_id = os.getenv("TEST_AGENT_ID", "")
        if agent_id:
            self.client.get(
                f"/console/tenants/{agent_id}",
                name="/console/tenants/[id]",
            )

    @tag("console", "conversations")
    @task(3)
    def conversation_list(self):
        self.client.get("/console/conversations", name="/console/conversations")

    @tag("console", "health")
    @task(2)
    def health_page(self):
        self.client.get("/console/health", name="/console/health")

    @tag("console", "billing")
    @task(1)
    def billing_page(self):
        self.client.get("/console/billing", name="/console/billing")

    @tag("console", "triggers")
    @task(2)
    def triggers_page(self):
        self.client.get("/console/triggers", name="/console/triggers")


class WebhookUser(HttpUser):
    """Simulates inbound SMS traffic hitting the webhook."""
    wait_time = between(0.5, 2)
    host = os.getenv("TARGET_HOST", "http://localhost:8000")

    @tag("webhook")
    @task
    def inbound_sms(self):
        """Send a simulated Twilio webhook (signature validation must be
        disabled in dev or the test must supply a valid signature)."""
        self.client.post(
            "/webhooks/twilio/inbound",
            data={
                "From": "+15551234567",
                "To": os.getenv("TEST_TWILIO_NUMBER", "+15559876543"),
                "Body": "What showings are available this weekend?",
                "MessageSid": "SM_loadtest_0001",
            },
            name="/webhooks/twilio/inbound",
        )

    @tag("webhook")
    @task
    def status_callback(self):
        self.client.post(
            "/webhooks/twilio/status",
            data={
                "MessageSid": "SM_loadtest_0001",
                "MessageStatus": "delivered",
            },
            name="/webhooks/twilio/status",
        )
```

### Running

```bash
# Local — 10 users, ramp up over 30s
locust -f benchmarks/locustfile.py --headless \
    -u 10 -r 2 --run-time 2m \
    --csv benchmarks/results/run

# Console routes only
locust -f benchmarks/locustfile.py --headless \
    -u 5 -r 1 --run-time 2m --tags console \
    --csv benchmarks/results/console

# Webhook stress test — 50 concurrent
locust -f benchmarks/locustfile.py --headless \
    -u 50 -r 10 --run-time 1m --tags webhook \
    --csv benchmarks/results/webhook
```

### 4.2 Quick Benchmark Script

For everyday use without Locust.

### File: `benchmarks/quick_bench.py`

```python
"""Quick HTTP benchmark — hit key endpoints and report latency."""
import os
import sys
import time
import statistics
import requests

BASE = os.getenv("TARGET_HOST", "http://localhost:8000")
PASSWORD = os.getenv("CONSOLE_PASSWORD", "test-password")
ITERATIONS = int(os.getenv("BENCH_ITERATIONS", "20"))

ENDPOINTS = [
    ("GET", "/console/dashboard", "Dashboard"),
    ("GET", "/console/tenants", "Tenant List"),
    ("GET", "/console/conversations", "Conversations"),
    ("GET", "/console/triggers", "Triggers"),
    ("GET", "/console/health", "System Health"),
    ("GET", "/console/billing", "Billing"),
]


def main():
    session = requests.Session()
    # Login
    resp = session.post(f"{BASE}/console/login", data={"password": PASSWORD}, allow_redirects=False)
    if resp.status_code not in (302, 303):
        print(f"Login failed: {resp.status_code}")
        sys.exit(1)

    agent_id = os.getenv("TEST_AGENT_ID")
    if agent_id:
        ENDPOINTS.append(("GET", f"/console/tenants/{agent_id}", "Tenant Detail"))

    print(f"\nBenchmarking {BASE} — {ITERATIONS} iterations per endpoint\n")
    print(f"{'Endpoint':<25} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'avg':>8}")
    print("-" * 73)

    for method, path, label in ENDPOINTS:
        times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            if method == "GET":
                r = session.get(f"{BASE}{path}", allow_redirects=True)
            else:
                r = session.post(f"{BASE}{path}", allow_redirects=True)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

            if r.status_code >= 400:
                print(f"  WARN: {path} returned {r.status_code}")
                break

        if not times:
            continue

        times.sort()
        n = len(times)
        p50 = times[n // 2]
        p95 = times[int(n * 0.95)]
        p99 = times[int(n * 0.99)]
        mx = times[-1]
        avg = statistics.mean(times)

        print(f"{label:<25} {p50:>7.0f}ms {p95:>7.0f}ms {p99:>7.0f}ms {mx:>7.0f}ms {avg:>7.0f}ms")

    print()


if __name__ == "__main__":
    main()
```

---

## 5. Python Profiling

### 5.1 Profile a Specific Console Query

```python
"""Profile console_queries functions. Run with: python -m benchmarks.profile_queries"""
import cProfile
import pstats
import io

from app.db.connection import init_pool


def profile_dashboard():
    """Profile the dashboard data loading."""
    from app.services.console_queries import (
        get_system_pulse, get_recent_activity, get_agents_needing_attention,
    )

    pr = cProfile.Profile()
    pr.enable()

    for _ in range(10):
        get_system_pulse()
        get_recent_activity(limit=20)
        get_agents_needing_attention()

    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(30)
    print(s.getvalue())


def profile_agent_detail():
    """Profile tenant detail page loading."""
    import os
    from app.services.console_queries import get_agent_detail

    agent_id = os.getenv("TEST_AGENT_ID")
    if not agent_id:
        print("Set TEST_AGENT_ID to profile agent detail")
        return

    pr = cProfile.Profile()
    pr.enable()

    for _ in range(10):
        get_agent_detail(agent_id)

    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(30)
    print(s.getvalue())


if __name__ == "__main__":
    init_pool()
    print("=" * 60)
    print("DASHBOARD PROFILE")
    print("=" * 60)
    profile_dashboard()
    print()
    print("=" * 60)
    print("AGENT DETAIL PROFILE")
    print("=" * 60)
    profile_agent_detail()
```

### 5.2 DB Query Timer Wrapper

Add to `app/db/connection.py` or a utilities module for ad-hoc measurement.

```python
import time
import logging
import functools

logger = logging.getLogger("db.timing")

def timed_query(func):
    """Decorator that logs execution time for DB query functions."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info("%s: %.1fms", func.__name__, elapsed)
        if elapsed > 200:
            logger.warning("SLOW QUERY: %s took %.0fms", func.__name__, elapsed)
        return result
    return wrapper
```

Apply to any function in `console_queries.py`:

```python
@timed_query
def get_system_pulse() -> dict:
    ...
```

---

## 6. Makefile Commands

No Makefile exists yet. Create one or add to existing scripts.

### File: `Makefile`

```makefile
.PHONY: benchmark bench-console bench-webhook bench-profile bench-queries

# Quick HTTP benchmark (all console endpoints)
benchmark:
	python benchmarks/quick_bench.py

# Locust — console routes, 10 users, 2 minutes
bench-console:
	locust -f benchmarks/locustfile.py --headless \
		-u 10 -r 2 --run-time 2m --tags console \
		--csv benchmarks/results/console

# Locust — webhook stress, 50 users, 1 minute
bench-webhook:
	locust -f benchmarks/locustfile.py --headless \
		-u 50 -r 10 --run-time 1m --tags webhook \
		--csv benchmarks/results/webhook

# Python cProfile of DB query functions
bench-profile:
	python -m benchmarks.profile_queries

# Print current route timing stats (requires running server with TimingMiddleware)
bench-stats:
	curl -s http://localhost:8000/console/debug/perf | python -m json.tool
```

---

## 7. Performance Dashboard — Surfacing in the Console

### 7.1 Extend the Existing System Health Page

The `/console/health` page already queries `PERCENTILE_CONT` on `tool_executions.latency_ms`. Extend it with data from `TimingMiddleware`.

**Add to `get_health_overview()` in `console_queries.py`:**

```python
# Import at top of health_overview route
from app.middleware.timing import get_route_stats

# Add to the template context
route_perf = get_route_stats()
```

**Display in `health.html` template — new "Response Times" tab:**

- Table of routes with p50 / p95 / p99 columns
- Color-code: green if under budget, yellow if 80-100% of budget, red if over
- Sparkline or bar chart using inline SVG (no JS dependency needed)

### 7.2 LLM Latency Distribution

Already tracked in `usage_metrics.llm_calls` and `tool_executions.latency_ms`. Add a query:

```sql
-- LLM call latency distribution (last 24h)
SELECT
    model_used,
    COUNT(*) as calls,
    round(AVG(tokens_used)) as avg_tokens,
    round(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tokens_used)) as p50_tokens
FROM messages
WHERE ai_generated = true
AND created_at > now() - interval '24 hours'
AND model_used IS NOT NULL
GROUP BY model_used;
```

### 7.3 DB Query Timing Panel

Surface `pg_stat_statements` data (if accessible from the app's DB role):

```sql
SELECT
    calls,
    round(mean_exec_time::numeric, 1) as avg_ms,
    round(max_exec_time::numeric, 1) as max_ms,
    left(query, 80) as query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY mean_exec_time DESC
LIMIT 10;
```

If `pg_stat_statements` is not accessible (Supabase restrictions), fall back to the `@timed_query` decorator approach and store results in Redis:

```python
# In timed_query decorator, after logging:
from app.services.redis_pool import get_redis_pool
pool = get_redis_pool()
pool.lpush(f"perf:{func.__name__}", f"{elapsed:.1f}")
pool.ltrim(f"perf:{func.__name__}", 0, 499)  # Keep last 500
```

---

## 8. Monitoring Recommendations

### 8.1 What to Alert On

| Metric | Warning | Critical | Source |
|--------|---------|----------|--------|
| Dashboard p95 | >500ms | >1000ms | TimingMiddleware |
| Webhook p95 | >100ms | >500ms | TimingMiddleware |
| Pipeline e2e (Haiku) | >3000ms | >5000ms | `harness_traces.total_duration_ms` |
| Pipeline e2e (Sonnet) | >6000ms | >10000ms | `harness_traces.total_duration_ms` |
| DB connection pool usage | >80% | >95% | `pg_stat_activity` |
| Error rate (24h) | >5 | >20 | `tool_executions` |
| LLM error rate | >2% | >10% | `tool_executions` WHERE tool_name LIKE 'llm%' |

### 8.2 Lightweight Implementation (No External APM)

1. **TimingMiddleware** (Section 2) gives per-route percentiles in-process
2. **Structured logs** (already in place via `structured_logging.py`) can be parsed by Railway's log viewer
3. **`/console/debug/perf`** endpoint for on-demand checks
4. **Weekly cron** that runs `quick_bench.py` against staging and posts results to a Slack webhook or logs them

### 8.3 Railway-Specific

- Railway exposes container metrics (CPU, memory, network). Set memory alert at 80% of container limit.
- Use Railway's log search to find `Slow request:` warnings from TimingMiddleware.
- PostgreSQL metrics available through Supabase dashboard (active connections, query performance).

---

## 9. Known Risks and Optimization Targets

Based on code review, these are the queries most likely to degrade at scale:

### Priority 1 — Fix Before 100 Agents

1. **`get_all_agents()` correlated subqueries** (`console_queries.py:127-137`): Each subquery runs once per agent row. At 100 agents, that is 400 subquery executions. Rewrite as LEFT JOINs with GROUP BY.

2. **`get_recent_conversations()` per-row subqueries** (`console_queries.py:246-258`): `msg_count` and `last_message` are computed per row with correlated subqueries. Use `LATERAL` or pre-aggregate in a CTE.

3. **Dashboard `get_system_pulse()` — 5 serial queries** (`console_queries.py:20-55`): Combine into a single query with CTEs or use `asyncio.gather()` with the async connection.

### Priority 2 — Fix Before 1,000 Agents

4. **`get_agent_detail()` — unbounded contacts list** (`console_queries.py:154-159`): No LIMIT on contacts query. Add pagination.

5. **`messages` table growth**: No partition strategy. At 1,000 agents with 50 messages/day each, that is 50K rows/day = 18M rows/year. Consider range partitioning by `created_at`.

6. **`tool_executions` PERCENTILE_CONT** on health page: Expensive on large tables. Pre-aggregate into a materialized view refreshed every 5 minutes.

### Priority 3 — Monitor

7. **pgvector HNSW index** performance as embeddings grow. HNSW is good to ~1M rows; beyond that, consider `ef_search` tuning or IVFFlat.

8. **Connection pool sizing**: Currently using psycopg pool defaults. Tune `min_size`/`max_size` based on observed concurrency.

---

## 10. Directory Structure

```
benchmarks/
  locustfile.py          # Locust load test configuration
  quick_bench.py         # Quick HTTP benchmark script
  profile_queries.py     # cProfile wrapper for DB queries
  results/               # CSV output from Locust runs (gitignored)
app/middleware/
  timing.py              # Request timing middleware
Makefile                 # benchmark commands
```

---

## 11. Implementation Order

| Step | Task | Effort |
|------|------|--------|
| 1 | Add `TimingMiddleware` + wire into `main.py` | 30 min |
| 2 | Add `/console/debug/perf` endpoint | 15 min |
| 3 | Create `benchmarks/quick_bench.py` | 20 min |
| 4 | Run EXPLAIN ANALYZE on the 7 critical queries (Section 3.2) | 1 hour |
| 5 | Create `benchmarks/locustfile.py` | 30 min |
| 6 | Create `Makefile` with benchmark commands | 10 min |
| 7 | Run first baseline benchmark, record results | 30 min |
| 8 | Fix Priority 1 query issues | 2-3 hours |
| 9 | Add performance tab to System Health page | 1-2 hours |
| 10 | Set up weekly benchmark run on staging | 30 min |

**Total estimated effort: 1-2 days of focused work.**
