# Calloway Product Balance Evaluation

**Author:** Mara, Product Manager
**Date:** 2026-03-11
**Version:** 2.0

---

## Executive Summary

Calloway is a remarkably well-architected product for its stage. The core AI pipeline, tenant isolation, and compliance infrastructure are production-grade. The primary imbalances are: (1) no client-facing surface exists -- clients only interact via SMS/voice/email, never through a web or app experience; (2) the integration layer covers communication essentials but lacks the real estate-specific data feeds (MLS, DocuSign) that agents depend on daily; and (3) observability tooling is strong for operators but thin for agents themselves.

**Overall Score: 7.1 / 10**

---

## Dimension Scores

### 1. Feature Completeness — 7 / 10

**Justification:**

Calloway covers the core jobs-to-be-done well for a solo agent's daily operations:

- **Communication automation** -- Full SMS, voice (Vapi), and email pipeline with AI-driven responses. Multi-channel coverage with delivery tracking and cost accounting per channel.
- **Showing management** -- Calendar-integrated scheduling with hold-and-confirm workflow (30-minute hold expiry), lockbox/access instructions, occupied home coordination, and feedback capture.
- **Lead management** -- Contact lifecycle tracking (new_lead through past_client), lead preferences with property criteria, lead scoring using rule-based signals across 15 factors, and proactive gap analysis via the daily scanner.
- **Follow-up automation** -- Trigger system with 60-second polling, drip campaigns with multi-step sequences, recurring triggers (daily/weekly/monthly/annually), cascade triggers for transaction deadlines and open houses, and timezone-aware morning briefings.
- **Transaction tracking** -- Full offer-to-close lifecycle with 6 statuses, milestone tracking (inspection, appraisal, financing, closing), commission tracking, and auto-sync of contact lifecycle stage on status changes.
- **Agent commands** -- 14 distinct command types via SMS (listing updates, broadcasts, status changes, contact/schedule/gap/listing queries, triggers, cascades, offers, handoff returns, notes, and connect). The natural language command parsing is a genuine differentiator.
- **Seller operations** -- Listing management with natural language ingestion, DOM alerts at 5 thresholds with actionable recommendations, open house scheduling with cascade triggers, buyer-matching broadcasts, listing activity tracking, and seller weekly reports.
- **RAG system** -- pgvector embeddings for semantic search across conversations, contacts, and listings with context injection into LLM prompts.

What is present but thin:

- **Drip campaigns** -- Steps stored as JSONB with 3 default templates, but no campaign builder UI or template library in the agent portal.
- **Lead scoring** -- Rule-based only across 15 signals. No ML-based scoring, conversion prediction, or automatic campaign enrollment based on score tier.
- **Reporting** -- Usage metrics exist in the DB (messages, tokens, costs, showings, triggers) but agent-facing analytics (conversion rates, response times, pipeline velocity) are absent.

**#1 Gap: No client-facing portal.** Clients interact exclusively through SMS, voice, and email. There is no web-based client portal where buyers/sellers can view listings, check showing schedules, see transaction milestone progress, or upload documents. For solo agents managing 20-50+ active clients, this creates a bottleneck where every interaction must flow through the AI or the agent directly.

---

### 2. Architecture Maturity — 8 / 10

**Justification:**

The technical foundation is strong and reflects production-minded engineering:

- **Clean pipeline architecture** -- Normalize, Classify, Assemble Context, Route, Handle, Dispatch. Each stage is a discrete module with clear boundaries (`normalizer.py`, `classifier.py`, `assembler.py`, `router.py`, `handlers.py`, `dispatcher.py`). The intent-based context loading in `assembler.py` is efficient -- it only loads what the route needs against a TOKEN_BUDGET of 8000.
- **Model tiering** -- Haiku for classification and simple Q&A, Sonnet for full reasoning with tool use. Cost tracking per-agent per-day with model-specific pricing. This is smart unit economics.
- **Database design** -- 15 well-indexed tables with RLS policies on every single table. UUID primary keys, TIMESTAMPTZ throughout, proper foreign key constraints. Unique indexes prevent duplicate enrollments and contacts. The schema handles the domain comprehensively.
- **Command decomposition** -- 14 command handlers in `app/pipeline/commands/` with a clean dispatch table in `handlers.py`. Each command type is an isolated module.
- **Background workers** -- Trigger worker (60s poll) and daily scanner are simple, reliable patterns. The trigger worker also handles hold expiry and status reversion in each cycle.
- **Rate limiting** -- Redis-backed per-contact rate limiting (30/hour, 100/day), per-agent cost cap ($15/day), and unknown number throttling (10/day). Fail-open on Redis unavailability -- the right trade-off.
- **Structured logging** -- JSON logging with correlation IDs via `contextvars`, request-scoped context, and structured fields for agent_id, tool_name, latency_ms. Configured at startup to replace default handlers.
- **Security** -- CSRF protection on all POST routes, secure cookies (httponly, samesite=lax, secure in production), Twilio signature validation, production secret validation that calls `sys.exit(1)` on default credentials.
- **Retry logic** -- Anthropic API calls have exponential backoff retry on rate limit errors.

What could be stronger:

- **No migration framework** -- Migrations are raw SQL files (005 through 009 visible) with no tooling (Alembic, Flyway). Manual migration management does not scale beyond a small team.
- **Synchronous DB calls** -- `get_db_connection()` returns synchronous connections within async FastAPI handlers. This blocks the event loop under concurrent load.
- **In-memory state** -- Agent portal login codes stored in `_login_codes: dict` in process memory. Comment in code acknowledges "in production, use Redis." This breaks with multiple workers or restarts.
- **No task queue** -- Background processing uses a polling loop rather than Celery/Dramatiq/ARQ. Adequate for current scale but limits throughput and observability of background tasks.
- **Schema duplication** -- The transactions table appears twice in `schema.sql` (lines 216-240 and 441-464) with slightly different column definitions, suggesting incremental development without cleanup.

**#1 Gap: Synchronous database calls in async handlers.** The use of synchronous connections within FastAPI's async endpoints means every DB query blocks the event loop thread. Under concurrent load (multiple agents receiving messages simultaneously), this will cause request queuing and latency spikes. Migration to `asyncpg` or `psycopg` async mode is the highest-priority architectural improvement for production readiness.

---

### 3. User Experience Balance — 7 / 10

**Justification:**

Three user surfaces exist, each at a different maturity level, plus an SMS command interface that is surprisingly capable:

**Agent Portal (6/10):**
- 11 template pages: dashboard, conversations, conversation detail, contacts, schedule, triggers, campaigns, transactions, scores, and login.
- Phone-based OTP authentication (6-digit codes via SMS).
- Mobile-first design (appropriate for agents in the field).
- **Critically, the portal is read-only.** There are no POST routes beyond login. Agents cannot approve triggers, send messages, edit contacts, confirm showings, or create transactions from the UI. Every action must go through SMS commands.
- Missing: notification center, analytics/reporting, campaign builder, settings/preferences editing, document management, contact detail view.

**SMS Command Interface (8/10):**
- 14 command types covering the full operational surface.
- Natural language parsing with AI classification -- agents do not need to memorize syntax.
- Handoff/return workflow (silent mode) is genuinely thoughtful UX.
- Gap/schedule/contact queries provide instant intelligence.
- This is the product's strongest interaction model today.

**Operator Console (8/10):**
- 17+ template pages including dashboard, tenants (list/detail/edit/new), conversations, triggers, costs, errors, health, billing, manual, onboarding wizard, and HTMX partials for live updates.
- System pulse metrics, agent attention alerts, and activity feeds.
- Full CRUD on tenants. Trigger queue management (retry, cancel, fire-now). Cost dashboards. Health monitoring.
- Test SMS capability from console.
- This is genuinely strong for a v1 admin surface -- ready for an operator managing 50+ agents.

**AI Autonomy (8/10):**
- Three-tier autonomy model (Supervised, Autonomous, Manual) with per-agent JSONB configuration.
- TCPA compliance baked into the pipeline with pre-processing keyword detection (STOP/HELP/START plus affirmative consent).
- Agent notification system via Firebase push for critical events -- though **push is currently stubbed** (logs only, no actual Firebase send). This is a significant operational gap.
- Cost caps prevent runaway autonomous behavior.
- Consent gating ensures the AI never messages without permission.

**#1 Gap: Agent portal is read-only.** The product's most powerful features are only accessible via SMS commands or the operator console. A solo agent -- the target user -- needs to either memorize SMS command patterns or ask the operator to act on their behalf. Adding POST routes for the top 5 agent actions (approve trigger, send message, edit contact, confirm showing, reply to conversation) would transform the portal from a display screen into a work tool.

---

### 4. AI Capability Depth — 8 / 10

**Justification:**

The AI pipeline is one of Calloway's strongest dimensions:

- **Multi-stage pipeline** -- Normalize, Classify (Haiku), Assemble Context, Route, Handle (Sonnet with tools or Haiku for simple QA), Dispatch. Each stage has clear responsibilities and fallbacks. The pipeline processes SMS, voice transcripts, and email through a single unified flow.
- **Intent classification** -- 9 intent types (scheduling, listing_qa, lead_qualification, agent_command, transaction, personal, escalation, noise, feedback) with confidence scores, language detection, and keyword fallback when the LLM call fails. The `needs_full_context` flag controls whether to load heavy context.
- **Tool use** -- 11 tool modules with real actions: contacts, listings, showings, triggers, transactions, drip_campaigns, lead_scoring, calendar_tools, messaging, seller_tools, activity. The AI can book showings, create triggers, update contacts, enroll in drip campaigns, and execute offer workflows.
- **Agent command parsing** -- 14 command types parsed from natural language SMS with a well-structured classification prompt. The dispatch table pattern in `handlers.py` is clean and extensible.
- **Context assembly** -- Intent-aware context loading with a token budget of 8000. Only loads conversation history, relevant listings, calendar slots, and triggers based on what the intent requires. This controls cost and latency effectively.
- **RAG system** -- pgvector embeddings for semantic search across conversations, contacts, and listings. Context injection into LLM prompts for contextual memory.
- **Model tiering** -- Haiku for classification and listing Q&A (fast, cheap), Sonnet for full reasoning with tool use (slower, smarter). Cost tracking per model enables per-agent optimization.
- **Daily intelligence** -- Morning briefings with gap analysis, DOM alerts at 5 thresholds, and proactive follow-up identification. Seller weekly activity reports.
- **Consent-aware AI** -- The pipeline checks TCPA keywords before any processing, gates on consent status, and never messages revoked contacts.

What is not yet present:

- **No conversation summarization** -- Long threads are loaded as raw messages with a rough token estimate (TOKENS_PER_MESSAGE = 50). No summarization layer to compress older history. With the 8000 token budget, roughly 160 messages of history can be loaded before critical context is lost.
- **No learning/adaptation** -- The AI does not learn from agent corrections, feedback scores (the schema captures `feedback_score` on messages), or outcome data (which approaches convert?). No fine-tuning loop or preference learning.
- **No multi-turn planning** -- The AI responds to individual messages reactively. It does not maintain goals or plans across a conversation (e.g., "guide this lead through qualification over the next 3 interactions").
- **No A/B testing** -- Message templates and AI responses are not tested against alternatives for conversion optimization.

**#1 Gap: No conversation summarization.** With a token budget of 8000 and ~50 tokens per message, the system can load roughly 160 messages of history. For active leads with months of interaction, critical context will be lost. A summarization layer that compresses older conversation history into a running summary would preserve context while controlling costs. This is a prerequisite for long-term relationship management, which is the core of real estate.

---

### 5. Integration Breadth — 6 / 10

**Justification:**

Current integrations cover the communication layer well but leave significant real estate-specific gaps:

| Integration | Status | Quality |
|------------|--------|---------|
| Twilio (SMS/voice) | Implemented | Strong -- signature validation, delivery tracking, cost tracking, daily voice cap |
| Vapi (AI voice) | Implemented | Service layer exists, voice daily cap, assistant mapping, transcript processing |
| Google Calendar | Implemented | OAuth-based, event creation for showings, availability checking |
| Google Business Profile | Config exists | Review link stored in agents table but no active API integration |
| Firebase (push) | **Stubbed** | Notification tier system designed but `send_push_notification` only logs -- no actual FCM delivery |
| Stripe (billing) | Implemented | Subscription lifecycle, webhook handling, 3 plan tiers, 14-day trial, proration |
| SendGrid (email) | Implemented | Inbound parsing + outbound sending, API key + inbound secret |
| Redis | Implemented | Rate limiting, caching via shared connection pool, fail-open on unavailability |
| Anthropic Claude | Implemented | Model tiering, exponential backoff retry, per-agent token tracking |
| RAG (Voyage AI + pgvector) | Implemented | Embedding generation, HNSW indexing, cosine similarity search |

Missing integrations that solo agents rely on daily:

- **MLS/IDX feeds** -- No property data integration. Listings are manually entered via natural language parsing. Agents spend significant time maintaining listing data that could be auto-synced.
- **DocuSign/Dotloop** -- No document signing integration. Transaction management tracks dates but cannot generate or route documents. The offer command requests documents from clients but has nowhere to store them.
- **CRM import/export** -- No connection to existing CRMs (Follow Up Boss, kvCORE, Sierra). Agents switching to Calloway cannot import their contact database.
- **Zillow/Realtor.com** -- No lead capture from major portals. These are the #1 lead source for most solo agents.
- **Social media** -- No Facebook/Instagram integration for lead generation or listing promotion.
- **Zapier/webhooks** -- No outbound webhook or Zapier integration for connecting to third-party tools agents already use.

**#1 Gap: No MLS/IDX integration.** The listing table requires manual entry of every property. For solo agents managing 5-20 active listings plus showing properties from the broader MLS, this is a significant friction point. An MLS feed would auto-populate listings, keep prices and statuses current, and enable property matching against lead preferences without manual data entry.

---

### 6. Compliance & Security — 8 / 10

**Justification:**

This is a strong area, especially for a v1 product:

- **TCPA compliance** -- Full keyword handling (STOP/HELP/START plus affirmative consent words), consent lifecycle tracking (pending/granted/revoked), consent logging with audit trail (`consent_log` table), consent expiry detection (48-hour check for pending contacts), and hard gating via `check_consent_before_send` that blocks messages to revoked contacts. The function is documented as "CRITICAL: Hard check -- NEVER send a message to a contact with consent_status != 'granted'."
- **Row-Level Security** -- Every single data table (all 15) has RLS enabled with `agent_isolation` policies using `current_setting('app.current_agent_id')::uuid`. Tenant data is isolated at the database level, not just the application level. This is the correct approach for multi-tenant SaaS.
- **Authentication** -- Operator console uses password auth with CSRF protection on all POST routes. Agent portal uses phone-based OTP (6-digit codes with 10-minute expiry). Both use signed session cookies with `httponly`, `samesite=lax`, and `secure` flags (secure only in non-development environments).
- **Production safeguards** -- `validate_production_secrets()` refuses to start the app in production with default credentials (`CONSOLE_PASSWORD=changeme` or default session secret). Calls `sys.exit(1)` -- there is no bypass.
- **Twilio signature validation** -- `RequestValidator` enforced in production; skipped in development only when credentials are absent.
- **Rate limiting** -- Per-contact (30/hour, 100/day), per-agent cost cap ($15/day), and unknown number throttling (10/day). Prevents abuse and runaway costs.
- **CORS** -- Explicit origin allowlist in production, permissive only in development.
- **Session security** -- `itsdangerous.URLSafeTimedSerializer` for session tokens with max age enforcement.

Gaps:

- **No encryption at rest** -- Messages and contact data are stored in plaintext in PostgreSQL. For a product handling PII (names, phone numbers, emails) and financial information (offer prices, commission), at-rest encryption or column-level encryption for sensitive fields would strengthen compliance posture.
- **No audit logging** -- Beyond `consent_log`, there is no general audit trail for data access, configuration changes, or administrative actions. The `error_log` table captures errors but not normal operations.
- **No SOC 2 or data retention policies** -- No automated data purging, retention schedules, or compliance certifications.
- **Single-factor auth** -- Both portals use single-factor authentication (password or OTP). No MFA option for operator console access.
- **Session secret sharing** -- Agent portal derives its serializer from `CONSOLE_SESSION_SECRET + "-agent"`. A compromise of the console secret affects agent sessions.

**#1 Gap: No audit logging beyond consent.** Real estate transactions involve fiduciary duties and regulatory oversight. A general audit log capturing data access, configuration changes, and administrative actions would strengthen compliance posture and provide accountability. This becomes increasingly important as the platform scales and handles more sensitive transaction data.

---

### 7. Observability — 7 / 10

**Justification:**

Operator-facing observability is solid; agent-facing and proactive observability are thin:

**What exists:**
- **Structured JSON logging** -- Every log line includes timestamp, level, correlation_id, logger name, and contextual fields (agent_id, contact_id, channel, command_type, model_used, tokens_used, latency_ms, tool_name, event_type, conversation_id). This is production-grade logging.
- **Correlation IDs** -- Request-scoped correlation IDs generated in `CorrelationMiddleware`, propagated via `contextvars`, and returned in response headers (`x-correlation-id`). Enables end-to-end request tracing.
- **Error tracking** -- `error_log` table with module, severity, message, stack_trace, and context_json. Operator console has a dedicated Errors page.
- **Cost tracking** -- `usage_metrics` table tracks daily per-agent metrics across 14 dimensions: messages sent/received, LLM calls, tokens, LLM cost cents, voice minutes, SMS segments sent/received, SMS cost cents, voice cost cents, showings booked, and triggers fired. Operator console has a Costs page.
- **Health endpoints** -- Basic (`/health`), detailed (`/health/detailed` testing DB, Redis, Anthropic), and metrics (`/health/metrics` returning agent count, contact count, messages today, pending triggers).
- **Tool execution logging** -- `tool_executions` table records every tool call with input/output JSON, status, error messages, and latency in milliseconds.
- **Harness tracing** -- `harness_traces` table captures full pipeline traces for the testing harness, including intent detected, model used, and total duration.
- **Token monitoring** -- In-memory per-agent per-day token usage tracking in `AnthropicClient` with cost calculation per model.

**What is missing:**
- **No external APM or alerting** -- No Datadog, New Relic, Sentry, PagerDuty, or similar. Errors are logged to the database and stdout but there are no alerting rules, dashboards, or anomaly detection. If the trigger worker crashes at 2 AM, nobody is notified.
- **No agent-facing analytics** -- Agents cannot see their own response times, lead conversion rates, cost trends, AI accuracy, or pipeline velocity. The scores page shows lead scores but not operational metrics.
- **No SLA monitoring** -- No tracking of message response latency (time from inbound to outbound), showing booking success rates, or trigger execution reliability.
- **No log aggregation** -- Logs go to stdout as structured JSON. No mention of ELK, Loki, CloudWatch, or any aggregation service.
- **No uptime monitoring** -- Health endpoints exist but there is no external service pinging them.

**#1 Gap: No external alerting or APM.** The observability infrastructure (structured logs, correlation IDs, error table, tool execution logging) is well-designed for debugging after the fact, but there is no proactive alerting when things go wrong. If the trigger worker crashes, if Anthropic rate-limits spike, if message delivery failures increase, or if an agent's costs spike anomalously, nobody is notified until they manually check the console.

---

### 8. Business Model Readiness — 7 / 10

**Justification:**

The billing and multi-tenancy infrastructure is functional:

- **Stripe integration** -- Full subscription lifecycle: customer creation, subscription management, plan changes with proration, cancellation (at period end or immediate), webhook handling for subscription.updated, invoice.paid, and invoice.payment_failed events.
- **Three-tier pricing** -- Starter ($49/mo: 200 msgs, 50 contacts, SMS, templates), Professional ($99/mo: 600 msgs, 200 contacts, SMS+voice, AI reasoning, daily briefings), Enterprise ($199/mo: 1500 msgs, unlimited contacts, all channels, full autonomy, seller ops, priority support). Tiers are well-differentiated with clear upgrade incentives.
- **14-day trial** -- Built into the subscription creation flow with `TRIAL_DAYS = 14`.
- **Usage tracking** -- Per-agent daily metrics across 14 dimensions. Granular enough for usage-based billing if needed.
- **Multi-tenancy** -- Database-level tenant isolation via RLS on all 15 tables. Operator console manages tenants with full CRUD. Onboarding wizard exists.
- **Cost visibility** -- Operator console has a dedicated Costs page with 30-day summaries, per-agent breakdowns, and model tier analysis.
- **Message quota** -- `check_message_quota` function exists in billing_service.py (lines 361-395) for plan limit enforcement.

Gaps:

- **Enforcement completeness unclear** -- While `check_message_quota` exists, its integration into the pipeline at every message processing point needs verification. Contact limits defined in tiers may not be enforced at contact creation time.
- **No self-service plan management** -- Agents cannot view their plan, upgrade/downgrade, update payment methods, or view invoices from the agent portal. All billing management is operator-driven via the console.
- **No revenue analytics** -- No MRR tracking, churn analysis, LTV calculations, or cohort analysis in the operator console. The operator can see costs but not revenue health.
- **No metered billing** -- Current plans are flat-rate with limits. No pay-per-message or pay-per-AI-call overage model. Agents who exceed limits are presumably blocked rather than being able to pay for more.
- **No usage alerts** -- No notification to agents when they approach 80% or 100% of their tier limits.

**#1 Gap: No self-service billing for agents.** Agents cannot manage their own subscription from the portal. Viewing their plan, upgrading, downgrading, updating payment methods, or accessing invoices all require operator intervention. For a self-serve SaaS product targeting solo agents, this creates unnecessary support burden and friction.

---

## Score Summary

| # | Dimension | Score | #1 Gap |
|---|-----------|-------|--------|
| 1 | Feature Completeness | 7 | No client-facing portal |
| 2 | Architecture Maturity | 8 | Synchronous DB in async handlers |
| 3 | User Experience Balance | 7 | Agent portal is read-only |
| 4 | AI Capability Depth | 8 | No conversation summarization |
| 5 | Integration Breadth | 6 | No MLS/IDX integration |
| 6 | Compliance & Security | 8 | No audit logging |
| 7 | Observability | 7 | No external alerting/APM |
| 8 | Business Model Readiness | 7 | No self-service billing for agents |
| **Overall** | | **7.1** | |

---

## Top 5 Gaps to Address Next (Prioritized)

### 1. Agent Portal Write Actions + Firebase Push Notifications

**Impact:** Critical -- the portal is currently a display screen, and notifications never reach agents
**Effort:** Medium (2-3 weeks combined)

These two gaps are listed together because they are interdependent: enabling portal actions without notifications means agents do not know when there is something to act on.

**Portal actions needed:**
- Approve/reject pending triggers from the dashboard
- Send a quick message or reply to a conversation
- Create, edit, and view contact details (including preferences, scores, linked transactions)
- Confirm or cancel showings from the schedule view
- Enroll contacts in drip campaigns

**Firebase implementation:**
- Replace the TODO stub in `firebase_service.py` with actual FCM delivery
- Add FCM token storage to the agents table (or a new table)
- Ensure morning briefings, trigger approvals, delivery failures, and escalations actually reach agents

Without these, the product requires agents to live in their SMS app to use Calloway. That is acceptable as a supplement but insufficient as a primary operational tool.

### 2. MLS/IDX Integration

**Impact:** High -- eliminates manual listing entry, enables automated property matching
**Effort:** High (4-6 weeks)

Integrate with RESO Web API or a data provider (Spark, Bridge, Trestle) to:
- Auto-import agent listings from MLS and keep prices, statuses, and photos current
- Enable automated buyer-listing matching against `lead_preferences` (areas, price range, beds, baths, property type)
- Surface "new on market" alerts to relevant leads via the existing trigger system
- Feed listing data into the RAG system for richer AI responses

Solo agents cannot maintain accurate listing data manually across their active and showing inventory. This integration converts Calloway from a communication tool into a true operational platform. It also enables the AI to proactively match leads to new listings -- a high-value automation that justifies the subscription cost.

### 3. Async Database Layer

**Impact:** High -- production reliability under concurrent load
**Effort:** Medium (2-3 weeks)

Migrate from synchronous `psycopg2`/`get_db_connection()` to `asyncpg` or `psycopg` async mode:
- Eliminates event loop blocking in FastAPI handlers
- Enables true concurrent request handling for multiple simultaneous inbound messages
- Critical before scaling beyond approximately 20 concurrent agents

This is a prerequisite for production scalability. The current architecture will hit performance walls as tenant count grows and multiple agents receive messages simultaneously. The migration is mechanical but touches every file that calls `get_db_connection()`.

### 4. Client-Facing Portal (Read-Only)

**Impact:** High -- reduces agent workload, improves client experience, differentiates from competitors
**Effort:** Medium (3-4 weeks)

Build a lightweight web portal accessible via shareable links (no login required, token-based access) where clients can:
- View their upcoming showing details (address, time, access instructions)
- See transaction milestone progress (offer submitted -> inspection -> appraisal -> closing)
- Browse active listings matching their saved preferences
- Confirm, reschedule, or cancel showings without texting

This is the product's largest user experience gap. Every client interaction currently requires an SMS round-trip. A self-service portal for routine status checks would reduce message volume (improving unit economics on lower-tier plans) while making clients feel more informed and engaged. It also provides a surface to display the agent's brand, which matters in real estate.

### 5. Self-Service Billing + Plan Limit Enforcement

**Impact:** Medium -- protects unit economics, reduces operator burden, enables scale
**Effort:** Medium (2-3 weeks)

- Build agent portal billing page: current plan, usage vs. limits (with progress bars), upgrade/downgrade buttons, payment method management, invoice history
- Ensure plan limits are enforced at the pipeline level: message counts checked per billing cycle, contact limits checked at creation time, graceful degradation with template-only responses when over limit plus upgrade prompt
- Add usage alerts at 80% and 100% of tier limits via push notification
- Add overage options for agents who want to pay for more rather than being blocked

Without enforcement and self-service, the pricing model is aspirational. Agents on Starter can potentially consume Professional-tier resources, and every plan change requires operator intervention. Neither is acceptable for a self-serve SaaS product at scale.

---

## Honorable Mentions (Gaps 6-10)

6. **Conversation summarization** -- Compress older message history into running summaries to preserve context within the 8000 token budget. Critical for long-term client relationships which are the norm in real estate (buyers search for months).

7. **External alerting/APM** -- Integrate Sentry for error tracking and PagerDuty/Opsgenie for on-call alerting. Configure alerts for trigger worker health, message delivery failure rate, API error rate, and cost anomalies. Low effort, high operational value.

8. **CRM import/export** -- Enable agents to migrate from Follow Up Boss, kvCORE, or CSV with a one-time import. Without this, adoption requires agents to manually re-enter their entire contact database, which is a dealbreaker for anyone with 100+ contacts.

9. **Agent analytics dashboard** -- Response time trends, lead conversion funnel, AI accuracy metrics (using the existing `feedback_score` field), cost breakdown by channel, commission pipeline value. Solo agents are deeply metrics-driven.

10. **Audit logging** -- General-purpose audit trail beyond consent events for data access, configuration changes, and administrative actions. Increasingly important as the platform handles sensitive transaction data and scales to more agents.

---

## Conclusion

Calloway is a 7.1/10 product with 8/10 foundations. The AI pipeline, tenant isolation, compliance infrastructure, trigger/automation system, and operator tooling are genuinely production-grade. The SMS command interface is surprisingly complete and represents the product's strongest interaction model.

The primary imbalance is that the product has depth without breadth on the user experience surface. The backend can do far more than the frontend exposes. The agent portal is a read-only dashboard when it needs to be a work tool. Push notifications are designed but not delivered. Clients have no self-service surface at all.

The integration layer covers communication channels well but misses real estate-specific data sources (MLS, DocuSign) that would make the difference between "useful supplement" and "indispensable operating system."

Addressing the top 5 gaps in order would advance the overall score to approximately 8.5/10 and position Calloway for meaningful market traction with solo agents. The architectural foundation is strong enough to support this growth -- the investment is primarily in surface area and integrations, not in rearchitecting.
