# Load / Stress Test Harness

Locust-based load tests for Calloway webhook endpoints.

## Prerequisites

```bash
pip install locust
```

## Setup

### 1. Seed test data

The seed script creates a test agent and 100 test contacts in the database.
It is idempotent — safe to run multiple times.

```bash
# Ensure DATABASE_URL is set (or present in .env)
python -m tests.load.seed_data
```

### 2. Start the app in dry-run mode

The server **must** be started with `DRY_RUN=true` so that inbound messages
are processed through the pipeline but no real SMS/voice calls are sent.

```bash
DRY_RUN=true ENVIRONMENT=development uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
DRY_RUN=true docker compose up
```

## Running load tests

### Interactive UI (recommended)

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
```

Then open http://localhost:8089 and configure users + spawn rate.

### Headless mode

```bash
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --headless \
  --users 50 \
  --spawn-rate 5 \
  --run-time 2m
```

### Makefile shortcut

```bash
make load-test          # 50 users, 5/s spawn, 2 min run
```

## Traffic mix

| User class        | Endpoint                       | Weight | Share |
|-------------------|--------------------------------|--------|-------|
| SimulatedSMSUser  | POST /webhooks/twilio/inbound  | 7      | 70%   |
| SimulatedVapiUser | POST /webhooks/vapi/post-call  | 2      | 20%   |
| HealthCheckUser   | GET /health                    | 1      | 10%   |

## Safety

- All tests target a dedicated test agent (`+15550000001`) created by `seed_data.py`
- The server must run with `DRY_RUN=true` to prevent real SMS sends
- Twilio signature validation is skipped in `development` environment
- Vapi webhook secret validation is skipped in `development` environment
- No production data is modified

## Interpreting results

Key metrics to watch in the Locust UI:

- **Median response time** — should stay under 200ms for health, under 2s for webhooks
- **p95 / p99 response time** — look for tail latency spikes
- **Failure rate** — non-zero failures indicate capacity limits or bugs
- **Requests/sec** — throughput at the current concurrency level
