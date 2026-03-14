# Calloway

**AI operational assistant for solo real estate agents.**

![Build](https://img.shields.io/badge/build-passing-brightgreen) ![Tests](https://img.shields.io/badge/tests-26_files-blue) ![Deploy](https://img.shields.io/badge/deploy-Railway-purple)

---

## What is Calloway?

Calloway is a SaaS platform that gives solo real estate agents an AI-powered operational assistant. It automates client communication across SMS, voice, and email, manages leads and contacts, handles scheduling and follow-ups, and delivers daily business intelligence briefings. Agents interact through a web-based admin console and a mobile portal, while their clients communicate naturally via text and phone — with Calloway handling the conversation, intent classification, and response generation behind the scenes.

## Architecture Overview

Calloway follows an inbound-webhook architecture: messages arrive via Twilio (SMS/voice) or SendGrid (email), flow through a multi-stage processing pipeline (normalize, classify intent, assemble context, LLM reasoning, tool execution), and produce outbound responses. Background workers handle scheduled triggers and daily scanning. An HTMX-powered admin console provides full operational control.

See [docs/architecture-diagram.md](docs/architecture-diagram.md) for detailed component diagrams.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **AI** | Anthropic Claude (Haiku + Sonnet), Voyage AI (embeddings) |
| **Database** | PostgreSQL 16 + pgvector (hosted on Supabase) |
| **Cache** | Redis |
| **Integrations** | Twilio (SMS/RCS/voice), Vapi (voice AI), Google (Calendar, Business Profile), Firebase (push notifications), Stripe (billing) |
| **Frontend** | Jinja2 templates + HTMX (server-rendered) |
| **Deployment** | Docker + Railway |

## Project Structure

```
app/
├── api/          # FastAPI route handlers (webhooks, console, portal, billing)
├── pipeline/     # Message processing pipeline (normalize → classify → context → LLM → tools → respond)
├── services/     # External service integrations (Anthropic, Twilio, Redis, Supabase)
├── tools/        # AI agent tool definitions (contacts, listings, showings, triggers, seller ops)
├── worker/       # Background workers (trigger_worker, daily_scanner)
├── db/           # Database schema and migrations
├── models/       # Pydantic schemas
├── templates/    # Jinja2 HTML templates (console + agent portal)
└── static/       # CSS, JS, images
docs/             # Documentation (architecture, audits, PRDs, API spec)
agency/           # AI agent team personas & deliverables
tests/            # Test suite (26 files, pytest + pytest-asyncio)
scripts/          # Utility scripts (seed data)
alembic/          # Database migration history
```

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16 with pgvector extension
- Redis
- Twilio account (for SMS/voice)
- Anthropic API key

### Setup

```bash
# Clone the repository
git clone <repo-url> && cd Calloway

# Create virtual environment
python -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for testing

# Configure environment
cp .env.example .env
# Edit .env with your API keys and database credentials

# Run database migrations
alembic upgrade head

# Seed sample data (optional)
python scripts/seed.py

# Start the server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. The admin console is at `/console`.

## Key Documentation

| Document | Description |
|----------|-------------|
| [Architecture Diagram](docs/architecture-diagram.md) | System architecture with Mermaid diagrams |
| [Architecture Audit](docs/architecture-audit.md) | Full codebase audit findings |
| [Audit (2026-03-11)](docs/audit-2026-03-11.md) | Detailed audit from March 2026 |
| [PRD: Customer Detail Redesign](docs/prd-customer-detail-redesign.md) | Product requirements for customer detail page |
| [OpenAPI Spec](docs/openapi.yaml) | Full API specification |
| [User Manual](docs/user-manual.md) | Admin console user manual |
| [Research](docs/research/) | Competitive landscape, tech references, design research |

## Development

### Running Tests

```bash
pytest                    # Run all tests
pytest tests/ -v          # Verbose output
pytest tests/ -x          # Stop on first failure
pytest tests/ -k "test_name"  # Run specific test
```

### Code Conventions

- **Type hints** on all function signatures
- **Pydantic models** for request/response validation
- **Tenant isolation** via PostgreSQL Row-Level Security (RLS)
- **Structured JSON logging** with correlation IDs
- **Model tiering** — Haiku for fast/cheap tasks, Sonnet for complex reasoning
- **TCPA compliance** — consent tracking, revocation blocks automated messages

## API Documentation

Once the server is running:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

The full OpenAPI specification is also available at [docs/openapi.yaml](docs/openapi.yaml).

## Admin Console

The admin console at `/console` provides full operational control: tenant management, conversation monitoring, trigger/automation configuration, cost tracking, and system health dashboards. It is built with server-rendered Jinja2 templates and HTMX for dynamic interactions.

See the [User Manual](docs/user-manual.md) for detailed documentation.

## License

Proprietary. All rights reserved.
